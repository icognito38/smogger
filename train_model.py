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

# Each fire "name" must match the "name" in the FIRES list in the Streamlit app EXACTLY,
# and (lat, lon) must match that fire's "origin" there.
FIRES = [
    dict(name="Quebec Fire Complex", lat=49.0, lon=-73.0, cities={
        "Quebec_City": (46.8138, -71.2079), "Montreal": (45.5016, -73.5672),
        "Ottawa": (45.4215, -75.6971), "Toronto": (43.6510, -79.3470),
        "Albany": (42.6526, -73.7562), "New_York": (40.7128, -74.0060),
        "Philadelphia": (39.9526, -75.1652), "Washington_DC": (38.9072, -77.0369)}),
    dict(name="Sector 4 - North Hills", lat=37.8044, lon=-122.4500, cities={
        "San_Francisco": (37.7749, -122.4194), "Oakland": (37.8044, -122.2712),
        "Berkeley": (37.8715, -122.2730), "Daly_City": (37.6879, -122.4702),
        "San_Mateo": (37.5630, -122.3255), "San_Jose": (37.3382, -121.8863),
        "Richmond": (37.9358, -122.3478), "Sausalito": (37.8591, -122.4853)}),
    dict(name="East Bay Ridge Corridor", lat=37.8350, lon=-122.2100, cities={
        "Oakland": (37.8044, -122.2712), "Berkeley": (37.8715, -122.2730),
        "Alameda": (37.7652, -122.2416), "Walnut_Creek": (37.9101, -122.0652),
        "San_Leandro": (37.7249, -122.1561), "Hayward": (37.6688, -122.0808),
        "San_Francisco": (37.7749, -122.4194), "Richmond": (37.9358, -122.3478)}),
    dict(name="Skyline Boulevard", lat=37.6800, lon=-122.4900, cities={
        "Pacifica": (37.6138, -122.4869), "Daly_City": (37.6879, -122.4702),
        "San_Francisco": (37.7749, -122.4194), "San_Mateo": (37.5630, -122.3255),
        "Half_Moon_Bay": (37.4636, -122.4286), "South_San_Francisco": (37.6547, -122.4077),
        "Burlingame": (37.5841, -122.3661), "Redwood_City": (37.4852, -122.2364)}),
    dict(name="North Shore Mountains", lat=49.3900, lon=-123.0900, cities={
        "Vancouver": (49.2827, -123.1207), "North_Vancouver": (49.3200, -123.0724),
        "Burnaby": (49.2488, -122.9805), "West_Vancouver": (49.3277, -123.1600),
        "Richmond_BC": (49.1666, -123.1336), "Surrey": (49.1913, -122.8490),
        "Squamish": (49.7016, -123.1558), "Coquitlam": (49.2838, -122.7932)}),
    dict(name="Blue Mountains Escarpment", lat=-33.7100, lon=150.3000, cities={
        "Penrith": (-33.7510, 150.6942), "Parramatta": (-33.8150, 151.0011),
        "Sydney": (-33.8688, 151.2093), "Richmond_NSW": (-33.5983, 150.7510),
        "Lithgow": (-33.4833, 150.1500), "Windsor": (-33.6094, 150.8155),
        "Blacktown": (-33.7710, 150.9060), "Springwood": (-33.6997, 150.5640)}),
    dict(name="Twin Peaks Brush Fire", lat=37.7544, lon=-122.4477, cities={
        "San_Francisco": (37.7749, -122.4194), "Daly_City": (37.6879, -122.4702),
        "Oakland": (37.8044, -122.2712), "Berkeley": (37.8715, -122.2730),
        "South_San_Francisco": (37.6547, -122.4077), "San_Mateo": (37.5630, -122.3255),
        "Sausalito": (37.8591, -122.4853), "Pacifica": (37.6138, -122.4869)}),
    dict(name="Tilden Park Interface", lat=37.8950, lon=-122.2450, cities={
        "Berkeley": (37.8715, -122.2730), "Oakland": (37.8044, -122.2712),
        "Richmond": (37.9358, -122.3478), "El_Cerrito": (37.9161, -122.3108),
        "Orinda": (37.8771, -122.1797), "Walnut_Creek": (37.9101, -122.0652),
        "Albany_CA": (37.8869, -122.2978), "San_Rafael": (37.9735, -122.5311)}),
]

start_date, end_date = "2023-05-15", "2023-07-15"
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
split_time = pd.Timestamp("2023-06-25")
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
