"""SmokeShield model: 6-hour-ahead PM2.5 forecast. Importable by any frontend.

Quick test with no frontend:  python smokeshield.py
Uses IBM Snap ML when installed (LinuxONE), scikit-learn otherwise.
"""
import math
import os

import joblib
import numpy as np
import pandas as pd
import requests
import plume

FIRE = (49.0, -73.0)  # Quebec epicentre (assumed)
CITIES = {
    "Quebec_City": {"lat": 46.8138, "lon": -71.2079},
    "Montreal": {"lat": 45.5016, "lon": -73.5672},
    "Ottawa": {"lat": 45.4215, "lon": -75.6971},
    "Toronto": {"lat": 43.6510, "lon": -79.3470},
    "Albany": {"lat": 42.6526, "lon": -73.7562},
    "New_York": {"lat": 40.7128, "lon": -74.0060},
    "Philadelphia": {"lat": 39.9526, "lon": -75.1652},
    "Washington_DC": {"lat": 38.9072, "lon": -77.0369},
}
START, END = "2023-05-15", "2023-07-15"
H = 6  # forecast horizon, hours
SPLIT = pd.Timestamp("2023-06-25")  # everything from here on is held-out test data
ALERT = 35.0  # ug/m3
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
    """Hourly wind + modeled PM2.5 from Open-Meteo, cached to CSV after the first call."""
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
    pf = plume.city_features(plume.simulate(raw, CITIES, plume.fetch_fire_wind()))
    df = df.merge(pf, on=["City", "Time"], how="left")
    df["Distance_Miles"] = df["City"].map(lambda c: haversine(*FIRE, CITIES[c]["lat"], CITIES[c]["lon"]))
    brg = df["City"].map(lambda c: bearing(*FIRE, CITIES[c]["lat"], CITIES[c]["lon"]))
    rad = np.radians((df["Wind_Dir_deg"] + 180) % 360 - brg)  # smoke travels toward wind_dir + 180
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
    for lag in (3, 6):  # PM2.5 at the next-closest city to the fire: early warning
        col = f"Upstream_PM25_Lag{lag}"
        df[col] = np.nan
        for c in order:
            m = df["City"] == c
            df.loc[m, col] = wide[up[c]].shift(lag).reindex(df.loc[m, "Time"]).values
    df["Target"] = g["PM2_5"].shift(-H)  # real PM2.5 six hours later (only for scoring)
    return df


def _new_model():
    try:
        from snapml import RandomForestRegressor
        backend = "snapml"
    except ImportError:
        from sklearn.ensemble import RandomForestRegressor
        backend = "sklearn"
    return RandomForestRegressor(n_estimators=100, max_depth=12, random_state=42, n_jobs=os.cpu_count() or 4), backend


def train(df):
    """Learn the 6h CHANGE in PM2.5 from training-period rows only (ends 6h before SPLIT)."""
    d = df.dropna(subset=FEATURES + ["Target"])
    tr = d[d["Time"] < SPLIT - pd.Timedelta(hours=H)]
    model, backend = _new_model()
    model.fit(tr[FEATURES].values, (tr["Target"] - tr["PM2_5"]).values)
    return {"model": model, "backend": backend, "train_rows": len(tr)}


def load_or_train(df):
    """Load the saved model if it works on this machine, else train (seconds) and save it."""
    if os.path.exists(MODEL_PKL):
        try:
            b = joblib.load(MODEL_PKL)
            b["model"].predict(df.dropna(subset=FEATURES)[FEATURES].values[:1])
            return b
        except Exception as e:
            print(f"Saved model unusable here ({e}); retraining.")
    b = train(df)
    try:
        joblib.dump(b, MODEL_PKL)
    except Exception as e:
        print(f"Could not save model: {e}")
    return b


def score(df, bundle):
    """Add a Forecast column: PM2.5 six hours after each row's Time."""
    df = df.copy()
    ok = df[FEATURES].notna().all(axis=1)
    delta = bundle["model"].predict(df.loc[ok, FEATURES].values)
    df["Forecast"] = np.nan
    df.loc[ok, "Forecast"] = np.clip(df.loc[ok, "PM2_5"].values + delta, 0, None)
    return df


def metrics(df):
    t = df[df["Time"] >= SPLIT].dropna(subset=["Forecast", "Target"])
    return {
        "mae": float((t["Forecast"] - t["Target"]).abs().mean()),
        "base_mae": float((t["PM2_5"] - t["Target"]).abs().mean()),  # "no change" guess
        "rows": len(t),
    }


if __name__ == "__main__":
    data = build_features(fetch_raw())
    d = data.dropna(subset=FEATURES + ["Target"])
    tr = d[d["Time"] < SPLIT - pd.Timedelta(hours=H)]
    te = d[d["Time"] >= SPLIT]
    for name, feats in (("WITHOUT plume", [f for f in FEATURES if not f.startswith("Plume")]),
                        ("WITH plume", FEATURES)):
        model, backend = _new_model()
        model.fit(tr[feats].values, (tr["Target"] - tr["PM2_5"]).values)
        p = np.clip(te["PM2_5"].values + model.predict(te[feats].values), 0, None)
        print(f"{name:14s} MAE {np.abs(p - te['Target'].values).mean():.2f}  ({backend})")
        if name == "WITH plume" and hasattr(model, "feature_importances_"):
            imp = dict(zip(feats, model.feature_importances_))
            print("plume feature importance:", {k: round(float(v), 3) for k, v in imp.items() if k.startswith("Plume")})
    print(f"no-change baseline MAE {np.abs(te['PM2_5'].values - te['Target'].values).mean():.2f}")
