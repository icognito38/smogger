"""SmokeShield model: 6-hour-ahead PM2.5 forecast for cities downwind of a wildfire."""
import argparse
import json
import math
import os
import platform
import sys
import time
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
import requests

# ==========================================
# CONFIGURATION
# ==========================================
FIRE = (49.0, -73.0)  # Assumed epicentre
CITIES = {
    "Quebec_City": {"lat": 46.8138, "lon": -71.2079, "country": "Canada", "region": "Quebec"},
    "Montreal": {"lat": 45.5016, "lon": -73.5672, "country": "Canada", "region": "Quebec"},
    "Ottawa": {"lat": 45.4215, "lon": -75.6971, "country": "Canada", "region": "Ontario"},
    "Toronto": {"lat": 43.6510, "lon": -79.3470, "country": "Canada", "region": "Ontario"},
    "Albany": {"lat": 42.6526, "lon": -73.7562, "country": "United States", "region": "New York"},
    "New_York": {"lat": 40.7128, "lon": -74.0060, "country": "United States", "region": "New York"},
    "Philadelphia": {"lat": 39.9526, "lon": -75.1652, "country": "United States", "region": "Pennsylvania"},
    "Washington_DC": {"lat": 38.9072, "lon": -77.0369, "country": "United States", "region": "District of Columbia"},
    "San_Francisco": {"lat": 37.7749, "lon": -122.4194, "country": "United States", "region": "California"},
    "Los_Angeles": {"lat": 34.0522, "lon": -118.2437, "country": "United States", "region": "California"},
    "Seattle": {"lat": 47.6062, "lon": -122.3321, "country": "United States", "region": "Washington"},
    "Vancouver": {"lat": 49.2827, "lon": -123.1207, "country": "Canada", "region": "British Columbia"},
    "Sydney": {"lat": -33.8688, "lon": 151.2093, "country": "Australia", "region": "New South Wales"},
    "Melbourne": {"lat": -37.8136, "lon": 144.9631, "country": "Australia", "region": "Victoria"},
}

START, END = "2023-05-15", "2023-07-15"
H = 6  
SPLIT = pd.Timestamp("2023-06-25")
TEST_END = pd.Timestamp("2100-01-01")
LAG_H = 12
ALERT = 35.0
FEATURES = [
    "Distance_Miles", "Wind_Speed_kmh", "Along_Wind_kmh", "Cross_Wind_kmh",
    "Along_Wind_Roll12", "PM2_5", "PM2_5_Roll6",
    "PM2_5_Lag1", "PM2_5_Lag3", "PM2_5_Lag6", "PM2_5_Lag12", "PM2_5_Trend3",
    "Hour", "Upstream_PM25_Lag3", "Upstream_PM25_Lag6",
    "Plume_Now", "Plume_6h",
]
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_CSV = os.path.join(HERE, "smokeshield_data.csv")
MODEL_PKL = os.path.join(HERE, "smokeshield_model.pkl")

# ==========================================
# EMBEDDED PHYSICS SIMULATION (No imports needed!)
# ==========================================
MAX_AGE_H = 72
SIGMA0_KM = 10.0
SPREAD_KM_PER_H = 6.0
DECAY_TAU_H = 48.0
R_KM = 6371.0088

def fetch_fire_wind(start=START, end=END, lat=FIRE[0], lon=FIRE[1]):
    url = (f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}"
           f"&start_date={start}&end_date={end}&hourly=wind_speed_10m,wind_direction_10m")
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    h = r.json()["hourly"]
    return pd.DataFrame({"Time": pd.to_datetime(h["time"]), "Speed_kmh": h["wind_speed_10m"], "Dir_from_deg": h["wind_direction_10m"]})

def _xy_km(lat, lon):
    p1, p2 = math.radians(FIRE[0]), math.radians(lat)
    dlon = math.radians(lon - FIRE[1])
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    d = 2 * R_KM * math.asin(math.sqrt(a))
    b = math.atan2(math.sin(dlon) * math.cos(p2), math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon))
    return d * math.sin(b), d * math.cos(b)

def simulate_plume(raw, cities, fire_wind):
    w = fire_wind.drop_duplicates("Time").sort_values("Time").reset_index(drop=True)
    spd = w["Speed_kmh"].astype(float).ffill().bfill().fillna(0).to_numpy()
    frm = w["Dir_from_deg"].astype(float).ffill().bfill().fillna(0).to_numpy()
    toward = np.radians((frm + 180) % 360)
    steps = np.column_stack([spd * np.sin(toward), spd * np.cos(toward)])
    C = np.vstack([[0.0, 0.0], np.cumsum(steps, axis=0)])

    names = list(cities)
    cxy = np.array([_xy_km(cities[c]["lat"], cities[c]["lon"]) for c in names])
    ages = np.arange(MAX_AGE_H + 1)
    sig = SIGMA0_KM + SPREAD_KM_PER_H * ages
    amp = (SIGMA0_KM / sig) ** 2 * np.exp(-ages / DECAY_TAU_H)

    T = len(w)
    out = np.zeros((len(names), T))
    for t in range(T):
        a = ages[: min(MAX_AGE_H, t) + 1]
        pos = C[t] - C[t - a]
        d2 = ((pos[None, :, :] - cxy[:, None, :]) ** 2).sum(-1)
        out[:, t] = (amp[a] * np.exp(-d2 / (2 * sig[a] ** 2))).sum(-1)

    sim = pd.DataFrame({"City": np.repeat(names, T), "Time": np.tile(w["Time"].to_numpy(), len(names)), "Plume_Now": out.ravel()})
    return sim[sim["Time"].isin(pd.to_datetime(raw["Time"].unique()))].reset_index(drop=True)

def city_features(sim):
    sim = sim.sort_values(["City", "Time"]).reset_index(drop=True)
    sim["Plume_6h"] = sim.groupby("City")["Plume_Now"].shift(-H)
    return sim[["City", "Time", "Plume_Now", "Plume_6h"]]

# ==========================================
# MACHINE LEARNING ENGINE
# ==========================================
def haversine(lat1, lon1, lat2, lon2):
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 3958.8 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def bearing(lat1, lon1, lat2, lon2):
    dlon = math.radians(lon2 - lon1)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    x = math.sin(dlon) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360

def fetch_raw():
    if os.path.exists(DATA_CSV):
        return pd.read_csv(DATA_CSV, parse_dates=["Time"])
    parts = []
    for city, p in CITIES.items():
        q = f"latitude={p['lat']}&longitude={p['lon']}&start_date={START}&end_date={END}"
        w = requests.get(f"https://archive-api.open-meteo.com/v1/archive?{q}&hourly=wind_speed_10m,wind_direction_10m", timeout=30)
        a = requests.get(f"https://air-quality-api.open-meteo.com/v1/air-quality?{q}&hourly=pm2_5", timeout=30)
        w.raise_for_status()
        a.raise_for_status()
        w, a = w.json()["hourly"], a.json()["hourly"]
        parts.append(pd.DataFrame({
            "City": city, "Time": pd.to_datetime(w["time"]),
            "Wind_Speed_kmh": w["wind_speed_10m"], "Wind_Dir_deg": w["wind_direction_10m"], "PM2_5": a["pm2_5"],
        }))
    df = pd.concat(parts, ignore_index=True)
    df.to_csv(DATA_CSV, index=False)
    return df

def build_features(raw):
    df = raw.sort_values(["City", "Time"]).reset_index(drop=True)
    
    # Uses the internal embedded physics functions!
    pf = city_features(simulate_plume(raw, CITIES, fetch_fire_wind()))
    df = df.merge(pf, on=["City", "Time"], how="left")
    
    df["Distance_Miles"] = df["City"].map(lambda c: haversine(*FIRE, CITIES[c]["lat"], CITIES[c]["lon"]))
    brg = df["City"].map(lambda c: bearing(*FIRE, CITIES[c]["lat"], CITIES[c]["lon"]))
    rad = np.radians((df["Wind_Dir_deg"] + 180) % 360 - brg) 
    df["Along_Wind_kmh"] = df["Wind_Speed_kmh"] * np.cos(rad)
    df["Cross_Wind_kmh"] = df["Wind_Speed_kmh"] * np.abs(np.sin(rad))
    g = df.groupby("City")
    df["Along_Wind_Roll12"] = g["Along_Wind_kmh"].transform(lambda x: x.rolling(12, min_periods=1).mean())
    df["PM2_5_Roll6"] = g["PM2_5"].transform(lambda x: x.rolling(6, min_periods=1).mean())
    for lag in (1, 3, 6, 12):
        df[f"PM2_5_Lag{lag}"] = g["PM2_5"].shift(lag)
    df["PM2_5_Trend3"] = df["PM2_5"] - df["PM2_5_Lag3"]
    df["Hour"] = df["Time"].dt.hour
    wide = df.pivot(index="Time", columns="City", values="PM2_5")
    order = sorted(CITIES, key=lambda c: haversine(*FIRE, CITIES[c]["lat"], CITIES[c]["lon"]))
    up = {order[i]: order[i - 1] for i in range(1, len(order))}
    up[order[0]] = order[0]
    for lag in (3, 6): 
        col = f"Upstream_PM25_Lag{lag}"
        df[col] = np.nan
        for c in order:
            m = df["City"] == c
            df.loc[m, col] = wide[up[c]].shift(lag).reindex(df.loc[m, "Time"]).values
    df["Target"] = g["PM2_5"].shift(-H)
    return df

def in_test(t): return (t >= SPLIT) & (t < TEST_END)
def in_train(t): return (t < SPLIT - pd.Timedelta(hours=H)) | (t >= TEST_END + pd.Timedelta(hours=LAG_H))
def _split_key(): return f"{SPLIT}|{TEST_END}"

def _new_model():
    try:
        from snapml import RandomForestRegressor
        backend = "snapml"
    except ImportError:
        from sklearn.ensemble import RandomForestRegressor
        backend = "sklearn"
    return RandomForestRegressor(n_estimators=100, max_depth=12, random_state=42, n_jobs=os.cpu_count() or 4), backend

def _backend_label(backend):
    try:
        from importlib.metadata import version
        return f"{backend}_{version('snapml' if backend == 'snapml' else 'scikit-learn')}"
    except Exception:
        return backend

def train(df):
    d = df.dropna(subset=FEATURES + ["Target"])
    tr = d[in_train(d["Time"])]
    model, backend = _new_model()
    model.fit(tr[FEATURES].values, (tr["Target"] - tr["PM2_5"]).values)
    return {"model": model, "backend": backend, "train_rows": len(tr), "features": list(FEATURES), "split": _split_key()}

def load_or_train(df):
    if os.path.exists(MODEL_PKL):
        try:
            b = joblib.load(MODEL_PKL)
            if b.get("features") != FEATURES or b.get("split") != _split_key():
                raise ValueError("features or split changed")
            b["model"].predict(df.dropna(subset=FEATURES)[FEATURES].values[:1])
            return b
        except Exception as e:
            print(f"Saved model not reusable ({e}); retraining.")
    b = train(df)
    try:
        joblib.dump(b, MODEL_PKL)
    except Exception as e:
        print(f"Could not save model: {e}")
    return b

def score(df, bundle):
    df = df.copy()
    ok = df[FEATURES].notna().all(axis=1)
    delta = bundle["model"].predict(df.loc[ok, FEATURES].values)
    df["Forecast"] = np.nan
    df.loc[ok, "Forecast"] = np.clip(df.loc[ok, "PM2_5"].values + delta, 0, None)
    return df

def metrics(df):
    t = df[in_test(df["Time"])].dropna(subset=["Forecast", "Target"])
    if len(t) == 0:
        return {"mae": 0.0, "base_mae": 0.0, "rows": 0, "improvement_pct": 0.0, "r2": 0.0, "alert": {}}
    y, p, b = t["Target"].to_numpy(), t["Forecast"].to_numpy(), t["PM2_5"].to_numpy()
    mae, base = float(np.abs(p - y).mean()), float(np.abs(b - y).mean())
    sst = float(((y - y.mean()) ** 2).sum())
    return {
        "mae": mae, "base_mae": base, "rows": len(t),
        "improvement_pct": 100 * (base - mae) / base if base > 0 else 0.0,
        "r2": 1 - float(((p - y) ** 2).sum()) / sst if sst > 0 else float("nan"),
        "alert": {"threshold_ugm3": ALERT, "test_hours_above_threshold": int((y >= ALERT).sum())}
    }

def time_inference(bundle, df, reps=30):
    X = df.dropna(subset=FEATURES)[FEATURES].values[: len(CITIES)]
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter()
        bundle["model"].predict(X)
        ts.append((time.perf_counter() - t0) * 1000)
    return round(float(np.median(ts)), 2)

def print_metrics(m, ms=None):
    if not m.get("alert"): return
    a = m["alert"]
    print(f"Test rows {m['rows']} | hours >= {ALERT:.0f} ug/m3: {a['test_hours_above_threshold']}")
    print(f"MAE {m['mae']:.2f} vs no-change {m['base_mae']:.2f}  ({m['improvement_pct']:+.1f}%)  R2 {m['r2']:.2f}")
    if ms is not None:
        print(f"Inference for one tick: {ms} ms")

def export_for_frontend(df, bundle, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    t = df[in_test(df["Time"])].dropna(subset=["Forecast", "Target"])
    pd.DataFrame({
        "City": t["City"], "Time": t["Time"], "Current": t["PM2_5"], "Actual_6h_Later": t["Target"],
        "Forecast_6h_Later": t["Forecast"], "NoChange_Baseline": t["PM2_5"],
        "Lat": t["City"].map(lambda c: CITIES[c]["lat"]), "Lon": t["City"].map(lambda c: CITIES[c]["lon"]),
    }).to_csv(os.path.join(out_dir, "test_predictions.csv"), index=False)
    fetch_fire_wind().to_csv(os.path.join(out_dir, "fire_wind.csv"), index=False)
    
    with open(os.path.join(out_dir, "model_metadata.json"), "w") as f:
        json.dump({"features": FEATURES}, f)
    print(f"Exported to {out_dir}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", nargs="?", const="./data", metavar="DIR")
    args = ap.parse_args()
    
    data = build_features(fetch_raw())
    if args.export:
        bundle = load_or_train(data)
        scored = score(data, bundle)
        print_metrics(metrics(scored), time_inference(bundle, scored))
        export_for_frontend(scored, bundle, args.export)
