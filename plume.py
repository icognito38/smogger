import math
import os

import pandas as pd
import requests

FIRE = (49.0, -73.0)  # assumed fire location (same as the model)
HERE = os.path.dirname(os.path.abspath(__file__))
WIND_CSV = os.path.join(HERE, "fire_wind.csv")
_cache = {}


def fetch_fire_wind(start="2023-05-15", end="2023-07-15"):
    """Hourly wind at the fire from Open-Meteo. Saved to fire_wind.csv after the first call."""
    if "wind" in _cache:
        return _cache["wind"]
    if os.path.exists(WIND_CSV):
        w = pd.read_csv(WIND_CSV, parse_dates=["Time"])
    else:
        url = (f"https://archive-api.open-meteo.com/v1/archive?latitude={FIRE[0]}&longitude={FIRE[1]}"
               f"&start_date={start}&end_date={end}&hourly=wind_speed_10m,wind_direction_10m")
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        h = r.json()["hourly"]
        w = pd.DataFrame({"Time": pd.to_datetime(h["time"]), "Speed_kmh": h["wind_speed_10m"],
                          "Dir_from_deg": h["wind_direction_10m"]})
        w.to_csv(WIND_CSV, index=False)
    w = w.dropna().sort_values("Time").reset_index(drop=True)
    _cache["wind"] = w
    return w


def plume_path(wind_df, start_time, hours=6):
    """Follow the wind hour by hour from the fire. Returns [(lat, lon), ...]."""
    lat, lon = FIRE
    path = [(lat, lon)]
    rows = wind_df[wind_df["Time"] >= pd.Timestamp(start_time)].head(hours)
    for w in rows.itertuples():
        # Open-Meteo gives the direction the wind comes FROM, so smoke goes the opposite way
        to = math.radians((w.Dir_from_deg + 180) % 360)
        north_km = w.Speed_kmh * math.cos(to)  # one hour of wind = speed in km
        east_km = w.Speed_kmh * math.sin(to)
        lon += east_km / (111.0 * math.cos(math.radians(lat)))
        lat += north_km / 111.0
        path.append((lat, lon))
    return path


def plume_polygon(path, base_km=5, grow_km=6):
    """Turn the path into a fan that gets wider downwind. Returns [] if the path is too short."""
    if len(path) < 2:
        return []
    left, right = [], []
    for i, (la, lo) in enumerate(path):
        a, b = path[max(i - 1, 0)], path[min(i + 1, len(path) - 1)]
        cos_lat = math.cos(math.radians(la))
        dn = (b[0] - a[0]) * 111.0               # north-south step in km
        de = (b[1] - a[1]) * 111.0 * cos_lat     # east-west step in km
        n = math.hypot(dn, de) or 1.0
        pn, pe = -de / n, dn / n                 # sideways direction (km)
        half = base_km + grow_km * i             # fan half-width in km
        left.append((la + pn * half / 111.0, lo + pe * half / (111.0 * cos_lat)))
        right.append((la - pn * half / 111.0, lo - pe * half / (111.0 * cos_lat)))
    return left + right[::-1]


def plume_for(start_time, hours=6):
    """One call for the frontend: returns (path, polygon)."""
    path = plume_path(fetch_fire_wind(), start_time, hours)
    return path, plume_polygon(path)


if __name__ == "__main__":
    p, poly = plume_for("2023-06-26 00:00", hours=24)
    print(f"{len(p)} path points, {len(poly)} polygon points. End of plume: {p[-1]}")
