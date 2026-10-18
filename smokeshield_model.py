"""SmokeShield model: 6-hour-ahead PM2.5 forecast generalized across 8 global wildfires."""
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
# 1. MULTI-FIRE CONFIGURATION
# ==========================================
print("Step 1: Configuring Global Event Geometry & Data Limits...")

# Map the exact frontend fires to their origins
FIRES_MAP = {
    "Quebec Fire Complex": {"lat": 49.0, "lon": -73.0},
    "Sector 4 - North Hills": {"lat": 37.8044, "lon": -122.4500},
    "East Bay Ridge Corridor": {"lat": 37.8350, "lon": -122.2100},
    "Skyline Boulevard": {"lat": 37.6800, "lon": -122.4900},
    "North Shore Mountains": {"lat": 49.3900, "lon": -123.0900},
    "Blue Mountains Escarpment": {"lat": -33.7100, "lon": 150.3000},
    "Twin Peaks Brush Fire": {"lat": 37.7544, "lon": -122.4477},
    "Tilden Park Interface": {"lat": 37.8950, "lon": -122.2450},
}

# Link specific cities to monitor for each fire
CITIES = {
    "Montreal": {"lat": 45.5016, "lon": -73.5672, "fire": "Quebec Fire Complex"},
    "Quebec_City": {"lat": 46.8138, "lon": -71.2079, "fire": "Quebec Fire Complex"},
    "Ottawa": {"lat": 45.4215, "lon": -75.6971, "fire": "Quebec Fire Complex"},
    "Toronto": {"lat": 43.6510, "lon": -79.3470, "fire": "Quebec Fire Complex"},
    
    "San_Francisco": {"lat": 37.7749, "lon": -122.4194, "fire": "Twin Peaks Brush Fire"},
    "San_Rafael": {"lat": 37.9735, "lon": -122.5311, "fire": "Sector 4 - North Hills"},
    "Oakland": {"lat": 37.8044, "lon": -122.2712, "fire": "East Bay Ridge Corridor"},
    "San_Mateo": {"lat": 37.5630, "lon": -122.3255, "fire": "Skyline Boulevard"},
    "Berkeley": {"lat": 37.8715, "lon": -122.2730, "fire": "Tilden Park Interface"},
    
    "Vancouver": {"lat": 49.2827, "lon": -123.1207, "fire": "North Shore Mountains"},
    "Burnaby": {"lat": 49.2488, "lon": -122.9805, "fire": "North Shore Mountains"},
    
    "Sydney": {"lat": -33.8688, "lon": 151.2093, "fire": "Blue Mountains Escarpment"},
    "Penrith": {"lat": -33.7500, "lon": 150.7000, "fire": "Blue Mountains Escarpment"},
}

start_date, end_date = "2023-05-15", "2023-07-15"
HORIZON_H = 6  
R_KM = 6371.0088

# ==========================================
# 2. GEOSPATIAL MATH
# ==========================================
def haversine(lat1, lon1, lat2, lon2):
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 3958.8 * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

def calculate_bearing(lat1, lon1, lat2, lon2):
    dlon = math.radians(lon2 - lon1)
    lat1, lat2 = math.radians(lat1), math.radians(lat2)
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1) * math.cos(lat2) * math.cos(dlon))
    return (math.degrees(math.atan2(x, y)) + 360) % 360

# ==========================================
# 3. FETCH GLOBAL DATA
# ==========================================
print("Step 2: Fetching Wind Origins for All 8 Fires...")
all_fire_winds = []
for f_name, f_coords in FIRES_MAP.items():
    url = f"https://archive-api.open-meteo.com/v1/archive?latitude={f_coords['lat']}&longitude={f_coords['lon']}&start_date={start_date}&end_date={end_date}&hourly=wind_speed_10m,wind_direction_10m"
    r = requests.get(url, timeout=30).json()["hourly"]
    df_w = pd.DataFrame({"Fire_Name": f_name, "Time": pd.to_datetime(r["time"]), "Speed_kmh": r["wind_speed_10m"], "Dir_from_deg": r["wind_direction_10m"]})
    all_fire_winds.append(df_w)
df_winds = pd.concat(all_fire_winds, ignore_index=True)

all_data = []
for city, coords in CITIES.items():
    f_name = coords["fire"]
    print(f"Fetching historical open-meteo data for {city} (Linked to: {f_name})...")
    f_lat, f_lon = FIRES_MAP[f_name]["lat"], FIRES_MAP[f_name]["lon"]
    dist_miles = haversine(f_lat, f_lon, coords["lat"], coords["lon"])
    bearing_from_fire = calculate_bearing(f_lat, f_lon, coords["lat"], coords["lon"])

    weather_url = f"https://archive-api.open-meteo.com/v1/archive?latitude={coords['lat']}&longitude={coords['lon']}&start_date={start_date}&end_date={end_date}&hourly=wind_speed_10m,wind_direction_10m"
    aqi_url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={coords['lat']}&longitude={coords['lon']}&start_date={start_date}&end_date={end_date}&hourly=pm2_5"

    try:
        w_res = requests.get(weather_url, timeout=30).json()
        a_res = requests.get(aqi_url, timeout=30).json()
        df_city = pd.DataFrame({
            "City": city, "Fire_Name": f_name,
            "Time": pd.to_datetime(w_res["hourly"]["time"]),
            "Wind_Speed_kmh": w_res["hourly"]["wind_speed_10m"],
            "Wind_Dir_deg": w_res["hourly"]["wind_direction_10m"],
            "PM2_5": a_res["hourly"]["pm2_5"],
            "Distance_Miles": dist_miles,
            "Bearing_From_Fire": bearing_from_fire,
        })
        all_data.append(df_city)
    except Exception as e:
        print(f"Failed for {city}: {e}")

df = pd.concat(all_data, ignore_index=True).sort_values(by=["City", "Time"]).reset_index(drop=True)

# ==========================================
# 4. PHYSICS & TIME SERIES ENGINEERING
# ==========================================
print("Step 3: Running Physics Engine per Fire...")

def _xy_km(lat, lon, f_lat, f_lon):
    p1, p2 = math.radians(f_lat), math.radians(lat)
    dlon = math.radians(lon - f_lon)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    d = 2 * R_KM * math.asin(math.sqrt(a))
    b = math.atan2(math.sin(dlon) * math.cos(p2), math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon))
    return d * math.sin(b), d * math.cos(b)

def simulate_plume(raw, cities_dict, fire_wind, f_lat, f_lon):
    w = fire_wind.drop_duplicates("Time").sort_values("Time").reset_index(drop=True)
    if len(w) == 0: return pd.DataFrame()
    spd = w["Speed_kmh"].astype(float).ffill().bfill().fillna(0).to_numpy()
    frm = w["Dir_from_deg"].astype(float).ffill().bfill().fillna(0).to_numpy()
    toward = np.radians((frm + 180) % 360)
    steps = np.column_stack([spd * np.sin(toward), spd * np.cos(toward)])
    C = np.vstack([[0.0, 0.0], np.cumsum(steps, axis=0)])

    names = list(cities_dict)
    cxy = np.array([_xy_km(cities_dict[c]["lat"], cities_dict[c]["lon"], f_lat, f_lon) for c in names])
    ages = np.arange(73)
    sig = 10.0 + 6.0 * ages
    amp = (10.0 / sig) ** 2 * np.exp(-ages / 48.0)

    T = len(w)
    out = np.zeros((len(names), T))
    for t in range(T):
        a = ages[: min(72, t) + 1]
        pos = C[t] - C[t - a]
        d2 = ((pos[None, :, :] - cxy[:, None, :]) ** 2).sum(-1)
        out[:, t] = (amp[a] * np.exp(-d2 / (2 * sig[a] ** 2))).sum(-1)

    sim = pd.DataFrame({"City": np.repeat(names, T), "Time": np.tile(w["Time"].to_numpy(), len(names)), "Plume_Now": out.ravel()})
    return sim[sim["Time"].isin(pd.to_datetime(raw["Time"].unique()))].reset_index(drop=True)

pf_list = []
for f_name, f_info in FIRES_MAP.items():
    f_cities = {c: v for c, v in CITIES.items() if v["fire"] == f_name}
    if not f_cities: continue
    f_raw = df[df["City"].isin(f_cities)]
    f_wind = df_winds[df_winds["Fire_Name"] == f_name]
    sim = simulate_plume(f_raw, f_cities, f_wind, f_info["lat"], f_info["lon"])
    sim = sim.sort_values(["City", "Time"]).reset_index(drop=True)
    sim["Plume_6h"] = sim.groupby("City")["Plume_Now"].shift(-HORIZON_H)
    pf_list.append(sim[["City", "Time", "Plume_Now", "Plume_6h"]])

df = df.merge(pd.concat(pf_list, ignore_index=True), on=["City", "Time"], how="left")

smoke_travel_dir = (df["Wind_Dir_deg"] + 180) % 360
diff_rad = np.radians(smoke_travel_dir - df["Bearing_From_Fire"])
df["Along_Wind_kmh"] = df["Wind_Speed_kmh"] * np.cos(diff_rad)
df["Cross_Wind_kmh"] = df["Wind_Speed_kmh"] * np.abs(np.sin(diff_rad))

g = df.groupby("City")
df["Along_Wind_Roll12"] = g["Along_Wind_kmh"].transform(lambda x: x.rolling(12, min_periods=1).mean())
df["PM2_5_Roll6"] = g["PM2_5"].transform(lambda x: x.rolling(6, min_periods=1).mean())

for lag in (1, 3, 6, 12):
    df[f"PM2_5_Lag{lag}"] = g["PM2_5"].shift(lag)
df["PM2_5_Trend3"] = df["PM2_5"] - df["PM2_5_Lag3"]
df["Hour"] = df["Time"].dt.hour

pm_wide = df.pivot(index="Time", columns="City", values="PM2_5")
df["Upstream_PM25_Lag3"] = np.nan
df["Upstream_PM25_Lag6"] = np.nan

for f_name in FIRES_MAP:
    f_cities = [c for c, v in CITIES.items() if v["fire"] == f_name]
    if not f_cities: continue
    f_lat, f_lon = FIRES_MAP[f_name]["lat"], FIRES_MAP[f_name]["lon"]
    order = sorted(f_cities, key=lambda c: haversine(f_lat, f_lon, CITIES[c]["lat"], CITIES[c]["lon"]))
    up = {order[i]: order[i - 1] for i in range(1, len(order))}
    up[order[0]] = order[0]
    for lag in (3, 6):
        for c in order:
            m = df["City"] == c
            df.loc[m, f"Upstream_PM25_Lag{lag}"] = pm_wide[up[c]].shift(lag).reindex(df.loc[m, "Time"]).values

df["Target_PM25_6h_Ahead"] = g["PM2_5"].shift(-HORIZON_H)
df["Target_Delta"] = df["Target_PM25_6h_Ahead"] - df["PM2_5"]
df = df.dropna().reset_index(drop=True)

# ==========================================
# 5. CHRONOLOGICAL TRAIN/TEST SPLIT
# ==========================================
print("Step 4: Chronological Train/Test Split...")
split_time = pd.Timestamp("2023-06-25")
train_mask = df["Time"] < (split_time - pd.Timedelta(hours=HORIZON_H))
test_mask = df["Time"] >= split_time

features = [
    "Distance_Miles", "Wind_Speed_kmh", "Along_Wind_kmh", "Cross_Wind_kmh",
    "Along_Wind_Roll12", "PM2_5", "PM2_5_Roll6",
    "PM2_5_Lag1", "PM2_5_Lag3", "PM2_5_Lag6", "PM2_5_Lag12", "PM2_5_Trend3",
    "Hour", "Upstream_PM25_Lag3", "Upstream_PM25_Lag6", "Plume_Now", "Plume_6h"
]
target = "Target_PM25_6h_Ahead"

X_train, y_train = df.loc[train_mask, features], df.loc[train_mask, "Target_Delta"]
X_test = df.loc[test_mask, features]
y_test = df.loc[test_mask, target]  

# ==========================================
# 6. MODEL TRAINING (IBM SNAP ML OPTIMIZED)
# ==========================================
print("Step 5: Training Global Master Model...")
num_cores = os.cpu_count() or 4

try:
    from snapml import RandomForestRegressor
    model = RandomForestRegressor(n_estimators=100, max_depth=12, random_state=42, n_jobs=num_cores)
    try:
        from importlib.metadata import version
        ml_backend = f"snapml_{version('snapml')}"
    except Exception:
        ml_backend = "snapml"
except ImportError:
    from sklearn.ensemble import RandomForestRegressor
    import sklearn
    model = RandomForestRegressor(n_estimators=100, max_depth=12, random_state=42, n_jobs=num_cores)
    ml_backend = f"sklearn_{sklearn.__version__}"

model.fit(X_train.values, y_train.values)

# Evaluation
from sklearn.metrics import mean_absolute_error, r2_score
delta_preds = model.predict(X_test.values)  
preds = np.clip(X_test["PM2_5"].values + delta_preds, 0, None)  
mae = mean_absolute_error(y_test, preds)

baseline_preds = X_test["PM2_5"].values
baseline_mae = mean_absolute_error(y_test, baseline_preds)
improvement_pct = 100 * (baseline_mae - mae) / baseline_mae if baseline_mae > 0 else 0.0

print(f"\n--- GLOBAL MODEL RESULTS ---")
print(f"Validation MAE (6h Ahead): {mae:.2f} ug/m3")
print(f"Persistence baseline MAE:  {baseline_mae:.2f} ug/m3")
print(f"Improvement over baseline: {improvement_pct:.1f}%")

# ==========================================
# 7. EXPORT DATA FILES FOR THE FRONTEND
# ==========================================
out_dir = "/home/ibm-user/shared"
os.makedirs(out_dir, exist_ok=True)

out = df.loc[test_mask, ["City", "Time", "PM2_5", "Target_PM25_6h_Ahead", "Fire_Name"]].copy()
out = out.rename(columns={"PM2_5": "Current", "Target_PM25_6h_Ahead": "Actual_6h_Later"})
out["Forecast_6h_Later"] = preds       
out["NoChange_Baseline"] = baseline_preds  
out["Lat"] = out["City"].map(lambda c: CITIES[c]["lat"])
out["Lon"] = out["City"].map(lambda c: CITIES[c]["lon"])
out.to_csv(f"{out_dir}/test_predictions.csv", index=False)

df_winds.to_csv(f"{out_dir}/fire_wind.csv", index=False)

metadata = {
    "model_intent": "Global 8-Fire Master Engine",
    "features": features,
    "metrics": {
        "MAE": round(float(mae), 2),
        "MAE_improvement_vs_baseline_pct": round(float(improvement_pct), 1),
    },
    "hardware_audit": {"ml_backend": ml_backend, "architecture": platform.machine()}
}
with open(f"{out_dir}/model_metadata.json", "w") as f:
    json.dump(metadata, f, indent=4)

print(f"✅ Exported test_predictions.csv ({len(out)} rows) and fire_wind.csv to {out_dir}")
