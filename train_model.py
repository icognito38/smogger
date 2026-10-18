# Notebook setup cells (run once in Jupyter):
#   !pip install snapml
#   !pip install --upgrade pip
#   !pip install folium
import os
import sys
import time
import platform
import json
import math
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
import requests

# ==========================================
# 1. SETUP & CONFIGURATION
# ==========================================
print("Step 1: Configuring Fires, Cities & Data Limits...")

# Fires come from the NASA FIRMS hotspot file (backend/data/firms_global_latest.json, written by the
# backend ingestion). The densest hotspot clusters become the fires; the cities around each one are looked up
# by API (OpenStreetMap Overpass), and each fire is labelled with its nearest place (OpenStreetMap Nominatim).
# Fire names come from firms_live.live_fires, the same function app.py uses, so the app matches them by name
# when it reads the same hotspot file.
from pathlib import Path

_HERE = Path.cwd()
REPO_ROOT = next((p for p in (_HERE, *_HERE.parents) if (p / "firms_live.py").exists()), _HERE)
sys.path.insert(0, str(REPO_ROOT))
from firms_live import live_fires  # noqa: E402

FIRMS_JSON = Path(os.environ.get("FIRMS_JSON", REPO_ROOT / "backend" / "data" / "firms_global_latest.json"))
MAX_FIRES = int(os.environ.get("MAX_FIRES", 8))
CITIES_PER_FIRE = 8
MIN_CITIES = 3
CITY_RADIUS_KM = 150
TRAIN_DAYS = 60   # weather / PM2.5 history fetched before the hotspot date
TEST_DAYS = 14    # last part of that window is the chronological test set
USER_AGENT = "smogger-datathon/1.0 (wildfire smoke research prototype)"  # required by OSM API usage policy
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"

HORIZON_H = 6  # forecast horizon in hours

# Wind direction at four heights. Smoke lofted by the fire rides the upper levels, ground smoke the 10 m wind.
WIND_LEVELS = (10, 80, 120, 180)
WEATHER_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"  # same parameters; for live (non-historical) runs
HOURLY_WEATHER = "wind_speed_10m," + ",".join(f"wind_direction_{m}m" for m in WIND_LEVELS)

# ==========================================
# 2. GEOSPATIAL MATH
# ==========================================
def haversine(lat1, lon1, lat2, lon2):
    R = 3958.8
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def calculate_bearing(lat1, lon1, lat2, lon2):
    dlon = math.radians(lon2 - lon1)
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1) * math.cos(lat2) * math.cos(dlon))
    return (math.degrees(math.atan2(x, y)) + 360) % 360


# ==========================================
# 3. FETCH DATA (NO API KEYS NEEDED)
# ==========================================
def get_json(url, tries=4):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last


_weather_cache, _pm_cache = {}, {}


def nearby_cities(lat, lon, n=CITIES_PER_FIRE, radius_km=CITY_RADIUS_KM):
    """Cities/towns around a point from OpenStreetMap (Overpass): largest population first, then nearest."""
    query = (f'[out:json][timeout:60];node(around:{radius_km * 1000},{lat},{lon})'
             f'[place~"^(city|town)$"][name];out;')
    for i in range(4):
        try:
            r = requests.post(OVERPASS_URL, data={"data": query}, headers={"User-Agent": USER_AGENT}, timeout=90)
            r.raise_for_status()
            elements = r.json()["elements"]
            break
        except Exception as e:
            last = e
            time.sleep(5 * (i + 1))
    else:
        raise last
    seen, rows = set(), []
    for e in elements:
        name = e["tags"].get("name:en") or e["tags"]["name"]
        key = name.replace(" ", "_")
        if key in seen:
            continue
        seen.add(key)
        try:
            pop = int(str(e["tags"].get("population", "0")).replace(",", "").split()[0])
        except ValueError:
            pop = 0
        rows.append((key, e["lat"], e["lon"], pop, haversine(lat, lon, e["lat"], e["lon"])))
    rows.sort(key=lambda r: (-r[3], r[4]))
    time.sleep(1)
    return {k: (la, lo) for k, la, lo, _, _ in rows[:n]}


def place_name(lat, lon):
    """Nearest named place for a fire (OpenStreetMap Nominatim reverse geocoding, max 1 request/second)."""
    try:
        r = requests.get(NOMINATIM_URL, params={"lat": lat, "lon": lon, "format": "json", "zoom": 10},
                         headers={"User-Agent": USER_AGENT}, timeout=30)
        r.raise_for_status()
        a = r.json().get("address", {})
        town = a.get("city") or a.get("town") or a.get("village") or a.get("county") or a.get("state")
        return ", ".join(x for x in (town, a.get("state"), a.get("country")) if x) or "unknown"
    except Exception:
        return "unknown"
    finally:
        time.sleep(1.1)


def fires_from_firms(path=FIRMS_JSON, max_fires=MAX_FIRES):
    """(FIRES list for the training loop, hotspot date) from the FIRMS JSON."""
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    hotspots = data["hotspots"]
    # both ingestion schemas: v1 has acquired_at_utc, v2 has date
    dates = [h.get("date") or h.get("acquired_at_utc", "")[:10] for h in hotspots]
    fire_date = data.get("date") or max(d for d in dates if d)
    clusters, _ = live_fires(hotspots, fire_date, clusters=max_fires)
    fires = []
    for c in clusters:
        lat, lon = c["origin"]
        try:
            cities = nearby_cities(lat, lon)
        except Exception as e:
            print(f"  {c['name']}: city lookup failed ({e}); skipped")
            continue
        if len(cities) < MIN_CITIES:
            print(f"  {c['name']}: only {len(cities)} cities within {CITY_RADIUS_KM} km; skipped")
            continue
        place = place_name(lat, lon)
        fires.append(dict(name=c["name"], lat=lat, lon=lon, place=place, detections=c["detections"], cities=cities))
        print(f"  {c['name']} ({place}): {c['detections']} hotspots, cities: {', '.join(cities)}")
    return fires, fire_date


print(f"Reading NASA FIRMS hotspots from {FIRMS_JSON} ...")
FIRES, FIRE_DATE = fires_from_firms()
if not FIRES:
    raise RuntimeError("No FIRMS cluster had enough nearby cities. Check the JSON path and network access.")
_end = pd.Timestamp(FIRE_DATE)
start_date = (_end - pd.Timedelta(days=TRAIN_DAYS)).strftime("%Y-%m-%d")
end_date = _end.strftime("%Y-%m-%d")
print(f"{len(FIRES)} fires, hotspot date {FIRE_DATE}, weather/PM2.5 window {start_date} .. {end_date}")

def weather_url(lat, lon, base=WEATHER_ARCHIVE_URL):
    return (f"{base}?latitude={lat}&longitude={lon}"
            f"&start_date={start_date}&end_date={end_date}&hourly={HOURLY_WEATHER}")


def fetch_weather(lat, lon):
    """Hourly 10 m wind speed + wind direction at 10/80/120/180 m.

    The archive (ERA5) has no 180 m level (returned as all nulls) and fills 80/120 m from its 100 m level.
    An empty level is filled from the next level down, so a missing height never drops rows downstream.
    """
    key = (lat, lon)
    if key not in _weather_cache:
        h = get_json(weather_url(lat, lon))["hourly"]
        w = pd.DataFrame({"Time": pd.to_datetime(h["time"]), "Wind_Speed_kmh": h["wind_speed_10m"]})
        below = None
        for m in WIND_LEVELS:
            col = pd.Series(h.get(f"wind_direction_{m}m"), dtype="float64") if h.get(f"wind_direction_{m}m") else pd.Series(np.nan, index=w.index)
            if below is not None:
                col = col.fillna(below)
            w[f"Wind_Dir_{m}m_deg"] = col.values
            below = w[f"Wind_Dir_{m}m_deg"]
        w["Wind_Dir_deg"] = w["Wind_Dir_10m_deg"]  # kept: the app's fire_wind.csv and older code read this name
        _weather_cache[key] = w
        time.sleep(0.15)
    return _weather_cache[key]


def fetch_pm(lat, lon):
    key = (lat, lon)
    if key not in _pm_cache:
        url = (f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}"
               f"&start_date={start_date}&end_date={end_date}&hourly=pm2_5")
        h = get_json(url)["hourly"]
        _pm_cache[key] = pd.DataFrame({"Time": pd.to_datetime(h["time"]), "PM2_5": h["pm2_5"]})
        time.sleep(0.15)
    return _pm_cache[key]


def signed_angle(a, b):
    """b - a in degrees, wrapped to [-180, 180)."""
    return (b - a + 180) % 360 - 180


# ==========================================
# 4. PHYSICS & TIME SERIES ENGINEERING (PER FIRE)
# ==========================================
def build_fire_frame(fire):
    """Fetch + engineer features for one fire. Returns (feature_df, fire_wind_df) or (None, None)."""
    name, f_lat, f_lon = fire["name"], fire["lat"], fire["lon"]
    print(f"\n=== {name} ===")

    try:
        fw = fetch_weather(f_lat, f_lon)
    except Exception as e:
        print(f"  Skipping {name}: could not fetch wind at the fire ({e})")
        return None, None

    frames = []
    for city, (c_lat, c_lon) in fire["cities"].items():
        try:
            d = fetch_weather(c_lat, c_lon).merge(fetch_pm(c_lat, c_lon), on="Time", how="inner")
        except Exception as e:
            print(f"  Failed for {city}: {e}")
            continue
        d = d.copy()
        d["City"] = city
        d["Lat"], d["Lon"] = c_lat, c_lon
        d["Distance_Miles"] = haversine(f_lat, f_lon, c_lat, c_lon)
        d["Bearing_From_Fire"] = calculate_bearing(f_lat, f_lon, c_lat, c_lon)
        frames.append(d)
        print(f"  fetched {city}")

    if len(frames) < 3:
        print(f"  Skipping {name}: only {len(frames)} cities fetched")
        return None, None

    df = pd.concat(frames, ignore_index=True).sort_values(["City", "Time"]).reset_index(drop=True)

    # Open-Meteo wind direction = where the wind blows FROM, so smoke travels toward +180 degrees.
    # Along/cross-wind per height. Only 10 m speed is fetched, so every level uses it as the magnitude.
    for m in WIND_LEVELS:
        diff_rad = np.radians((df[f"Wind_Dir_{m}m_deg"] + 180) % 360 - df["Bearing_From_Fire"])
        df[f"Along_Wind_{m}m_kmh"] = df["Wind_Speed_kmh"] * np.cos(diff_rad)
        df[f"Cross_Wind_{m}m_kmh"] = df["Wind_Speed_kmh"] * np.abs(np.sin(diff_rad))
    df["Along_Wind_kmh"] = df["Along_Wind_10m_kmh"]  # original surface features keep their names
    df["Cross_Wind_kmh"] = df["Cross_Wind_10m_kmh"]
    # Column-mean of the profile: how much of the whole smoke column is pushed toward this city
    df["Along_Wind_Profile_kmh"] = df[[f"Along_Wind_{m}m_kmh" for m in WIND_LEVELS]].mean(axis=1)
    # Directional shear (veer): large values spread a lofted plume sideways
    df["Wind_Veer_10_180_deg"] = signed_angle(df["Wind_Dir_10m_deg"], df["Wind_Dir_180m_deg"]).abs()

    g = df.groupby("City")
    df["Along_Wind_Roll12"] = g["Along_Wind_kmh"].transform(lambda x: x.rolling(12, min_periods=1).mean())
    df["Along_Wind_Profile_Roll12"] = g["Along_Wind_Profile_kmh"].transform(lambda x: x.rolling(12, min_periods=1).mean())
    df["PM2_5_Roll6"] = g["PM2_5"].transform(lambda x: x.rolling(6, min_periods=1).mean())
    for lag in (1, 3, 6, 12):
        df[f"PM2_5_Lag{lag}"] = g["PM2_5"].shift(lag)
    df["PM2_5_Trend3"] = df["PM2_5"] - df["PM2_5_Lag3"]

    # Diurnal cycle: use local SOLAR hour (UTC hour shifted by longitude) because fires now span time zones
    df["Hour"] = (df["Time"].dt.hour + df["Lon"] / 15.0) % 24

    # Upstream signal: PM2.5 at the next-closest city to the fire, 3h and 6h ago
    pm_wide = df.pivot(index="Time", columns="City", values="PM2_5")
    order = sorted(df["City"].unique(), key=lambda c: df.loc[df["City"] == c, "Distance_Miles"].iloc[0])
    upstream_of = {order[i]: order[i - 1] for i in range(1, len(order))}
    upstream_of[order[0]] = order[0]
    for lag in (3, 6):
        col = f"Upstream_PM25_Lag{lag}"
        df[col] = np.nan
        for c in order:
            rows = df["City"] == c
            df.loc[rows, col] = pm_wide[upstream_of[c]].shift(lag).reindex(df.loc[rows, "Time"]).values

    df["Target_PM25_6h_Ahead"] = g["PM2_5"].shift(-HORIZON_H)
    df["Target_Delta"] = df["Target_PM25_6h_Ahead"] - df["PM2_5"]
    df = df.dropna().reset_index(drop=True)
    if df.empty:
        print(f"  Skipping {name}: no complete rows after cleaning")
        return None, None

    df["Fire_Name"] = name
    wind = pd.DataFrame({"Fire_Name": name, "Time": fw["Time"],
                         "Speed_kmh": fw["Wind_Speed_kmh"], "Dir_from_deg": fw["Wind_Dir_deg"],
                         **{f"Dir_from_{m}m_deg": fw[f"Wind_Dir_{m}m_deg"] for m in WIND_LEVELS}})
    print(f"  {name}: {len(df)} usable rows")
    return df, wind


print("Step 2: Fetching data & engineering features for every fire...")
frames, wind_frames = [], []
for fire in FIRES:
    d, w = build_fire_frame(fire)
    if d is not None:
        frames.append(d)
        wind_frames.append(w)

if not frames:
    raise RuntimeError("No fire data could be fetched. Check network access from the LinuxONE instance.")

df = pd.concat(frames, ignore_index=True)
fire_wind_df = pd.concat(wind_frames, ignore_index=True)

built = [f["name"] for f in FIRES if f["name"] in set(df["Fire_Name"])]
skipped = [f["name"] for f in FIRES if f["name"] not in built]
print(f"\nFires with ML data: {built}")
if skipped:
    print(f"⚠️ Fires SKIPPED (will show mock plume in the app): {skipped}")

# ==========================================
# 5. CHRONOLOGICAL TRAIN/TEST SPLIT
# ==========================================
print("Step 3: Chronological Train/Test Split...")
split_time = pd.Timestamp(end_date) - pd.Timedelta(days=TEST_DAYS)
train_mask = df["Time"] < (split_time - pd.Timedelta(hours=HORIZON_H))
test_mask = df["Time"] >= split_time

features = [
    "Distance_Miles", "Wind_Speed_kmh", "Along_Wind_kmh", "Cross_Wind_kmh",
    "Along_Wind_Roll12", "PM2_5", "PM2_5_Roll6",
    "PM2_5_Lag1", "PM2_5_Lag3", "PM2_5_Lag6", "PM2_5_Lag12", "PM2_5_Trend3",
    "Hour", "Upstream_PM25_Lag3", "Upstream_PM25_Lag6",
    # vertical wind profile
    "Along_Wind_80m_kmh", "Along_Wind_120m_kmh", "Along_Wind_180m_kmh",
    "Cross_Wind_180m_kmh", "Along_Wind_Profile_kmh", "Along_Wind_Profile_Roll12", "Wind_Veer_10_180_deg",
]
target = "Target_PM25_6h_Ahead"

X_train, y_train = df.loc[train_mask, features], df.loc[train_mask, "Target_Delta"]
X_test = df.loc[test_mask, features]
y_test = df.loc[test_mask, target]
print(f"Train rows: {len(X_train)} | Test rows: {len(X_test)}")

# ==========================================
# 6. MODEL TRAINING (IBM SNAP ML OPTIMIZED)
# ==========================================
print("Step 4: Training Mainframe-Optimized Model...")

num_cores = os.cpu_count()
if num_cores is None or num_cores < 1:
    num_cores = 4

try:
    from snapml import RandomForestRegressor
    print(f"🚀 SUCCESS: IBM Snap ML detected! Allocating {num_cores} cores.")
    model = RandomForestRegressor(n_estimators=100, max_depth=12, random_state=42, n_jobs=num_cores)
    try:
        from importlib.metadata import version
        ml_backend = f"snapml_{version('snapml')}"
    except Exception:
        ml_backend = "snapml"
except ImportError:
    from sklearn.ensemble import RandomForestRegressor
    import sklearn
    print(f"⚠️ Snap ML not found. Using standard scikit-learn on {num_cores} cores.")
    model = RandomForestRegressor(n_estimators=100, max_depth=12, random_state=42, n_jobs=num_cores)
    ml_backend = f"sklearn_{sklearn.__version__}"

model.fit(X_train.values, y_train.values)

from sklearn.metrics import mean_absolute_error, r2_score

delta_preds = model.predict(X_test.values)
preds = np.clip(X_test["PM2_5"].values + delta_preds, 0, None)
mae = mean_absolute_error(y_test, preds)
r2 = r2_score(y_test, preds)

baseline_preds = X_test["PM2_5"].values
baseline_mae = mean_absolute_error(y_test, baseline_preds)
baseline_r2 = r2_score(y_test, baseline_preds)
improvement_pct = 100 * (baseline_mae - mae) / baseline_mae if baseline_mae > 0 else 0.0

print(f"\n--- MODEL RESULTS (all fires) ---")
print(f"Validation MAE (6h Ahead): {mae:.2f} ug/m3")
print(f"Validation R2 Score:       {r2:.2f}")
print(f"Persistence baseline MAE:  {baseline_mae:.2f} ug/m3 (R2 {baseline_r2:.2f})")
print(f"Improvement over baseline: {improvement_pct:.1f}%")

per_fire = pd.DataFrame({"Fire_Name": df.loc[test_mask, "Fire_Name"].values,
                         "abs_err": np.abs(y_test.values - preds),
                         "base_err": np.abs(y_test.values - baseline_preds)}).groupby("Fire_Name").mean().round(2)
print("\nPer-fire MAE (model vs persistence):")
print(per_fire.rename(columns={"abs_err": "model", "base_err": "persistence"}))

from sklearn.metrics import precision_recall_fscore_support

ALERT_UGM3 = 35.0
y_true_alert = (y_test.values >= ALERT_UGM3)
alert_stats = {"threshold_ugm3": ALERT_UGM3, "test_hours_above_threshold": int(y_true_alert.sum())}
for name, p in (("model", preds), ("persistence", baseline_preds)):
    prec, rec, f1, _ = precision_recall_fscore_support(
        y_true_alert, (p >= ALERT_UGM3), average="binary", zero_division=0
    )
    alert_stats[name] = {"precision": round(float(prec), 2), "recall": round(float(rec), 2), "f1": round(float(f1), 2)}
print(f"\n--- ALERT CHECK (>= {ALERT_UGM3:.0f} ug/m3 in 6h) ---")
print(f"Test hours above threshold: {alert_stats['test_hours_above_threshold']}")
print(f"Model:       {alert_stats['model']}")
print(f"Persistence: {alert_stats['persistence']}")

# ==========================================
# 7. EXPORT MODEL & AUDIT TRAIL FOR JUDGES
# ==========================================
out_dir = os.environ.get("SMOKE_OUT_DIR", "/home/ibm-user/shared")
model_path = f"{out_dir}/smokeshield_master.pkl"
meta_path = f"{out_dir}/model_metadata.json"
os.makedirs(out_dir, exist_ok=True)

try:
    joblib.dump(model, model_path)
    reloaded = joblib.load(model_path)
    n_check = min(500, len(X_test))
    roundtrip_ok = bool(np.allclose(reloaded.predict(X_test.values[:n_check]), delta_preds[:n_check]))
except Exception as e:
    roundtrip_ok = False
    print(f"⚠️ Model save/reload check failed: {e}")

metadata = {
    "model_intent": "6-Hour Ahead PM2.5 Forecasting (predicts 6h change on top of current level)",
    "trained_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "fires": built,
    "features": features,
    "data": {
        "cities_per_fire": {f["name"]: list(f["cities"].keys()) for f in FIRES if f["name"] in built},
        "fire_places": {f["name"]: {"place": f["place"], "lat": round(f["lat"], 4), "lon": round(f["lon"], 4),
                                    "hotspots": f["detections"]} for f in FIRES if f["name"] in built},
        "firms_source": {"file": str(FIRMS_JSON), "hotspot_date": FIRE_DATE},
        "date_range": [start_date, end_date],
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "test_start": str(split_time),
        "weather_hourly": HOURLY_WEATHER,
    },
    "metrics": {
        "MAE": round(float(mae), 2),
        "R2": round(float(r2), 2),
        "baseline_persistence_MAE": round(float(baseline_mae), 2),
        "baseline_persistence_R2": round(float(baseline_r2), 2),
        "MAE_improvement_vs_baseline_pct": round(float(improvement_pct), 1),
    },
    "alert_check": alert_stats,
    "model_file_reload_verified": roundtrip_ok,
    "hardware_audit": {
        "architecture": platform.machine(),
        "os_platform": platform.platform(),
        "cpu_threads_used": num_cores,
        "byteorder": sys.byteorder,
        "ml_backend": ml_backend,
    },
}

importances = getattr(model, "feature_importances_", None)
if importances is not None:
    metadata["feature_importances"] = {f: round(float(v), 4) for f, v in zip(features, importances)}

with open(meta_path, "w") as f:
    json.dump(metadata, f, indent=4)

print(f"\n✅ SUCCESS! Model saved to {model_path}. Reload check: {'passed' if roundtrip_ok else 'FAILED'}")
print(f"✅ AUDIT TRAIL saved to {meta_path}. INCLUDE THIS JSON IN YOUR PRESENTATION!")

# ==========================================
# 8. EXPORT DATA FILES FOR THE FRONTEND
# ==========================================
# The frontend reads these two CSVs. It never loads or runs the .pkl model.
out = df.loc[test_mask, ["Fire_Name", "City", "Time", "PM2_5", "Target_PM25_6h_Ahead", "Lat", "Lon"]].copy()
out = out.rename(columns={"PM2_5": "Current", "Target_PM25_6h_Ahead": "Actual_6h_Later"})
out["Forecast_6h_Later"] = preds
out["NoChange_Baseline"] = baseline_preds
out.to_csv(f"{out_dir}/test_predictions.csv", index=False)

# Dir_from_deg (10 m) is what plume.py reads; the per-height columns are extra.
fire_wind_df.to_csv(f"{out_dir}/fire_wind.csv", index=False)

print(f"✅ test_predictions.csv saved ({len(out)} rows, {out['Fire_Name'].nunique()} fires)")
print(f"✅ fire_wind.csv saved ({len(fire_wind_df)} rows, {fire_wind_df['Fire_Name'].nunique()} fires)")
