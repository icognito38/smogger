"""
plume.py - smoke plume geometry that is driven by the model's output.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

# ------------------------------------------------------------------ config
IGNITION = (49.0, -73.0)  
FIRE_LAT, FIRE_LON = IGNITION
ALERT_UGM3 = 35.0  
HORIZON_H = 6
CONE_DEG = 25.0  
MIN_REACH_KM = 10.0
CAP_START = 0.82  
R_KM = 6371.0088

LAYERS = (("outer", 1.00, 1.00), ("l2", 0.82, 0.93), ("l3", 0.64, 0.82), ("l4", 0.46, 0.68), ("core", 0.28, 0.52))
LAYER_STYLE = {  
    "outer": dict(fill="#c2410c", opacity=0.14, weight=1.2),
    "l2": dict(fill="#c2410c", opacity=0.14, weight=0),
    "l3": dict(fill="#c2410c", opacity=0.14, weight=0),
    "l4": dict(fill="#b3340d", opacity=0.16, weight=0),
    "core": dict(fill="#7a0f12", opacity=0.22, weight=0),
}
HEAT_GRADIENT = {0.2: "#4a6fa5", 0.5: "#c98a0b", 0.8: "#c2410c", 1.0: "#7a0f12"}
_COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]

# ------------------------------------------------------------------ geo helpers
def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R_KM * math.asin(math.sqrt(a))

def bearing_deg(lat1, lon1, lat2, lon2):
    dlon = math.radians(lon2 - lon1)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    x = math.sin(dlon) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360

def destination(lat, lon, bearing, dist_km):
    d, b = dist_km / R_KM, math.radians(bearing)
    p1, l1 = math.radians(lat), math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
    l2 = l1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(p1), math.cos(d) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), (math.degrees(l2) + 540) % 360 - 180

def to_xy(lat, lon):
    d = haversine_km(FIRE_LAT, FIRE_LON, lat, lon)
    b = math.radians(bearing_deg(FIRE_LAT, FIRE_LON, lat, lon))
    return d * math.sin(b), d * math.cos(b)

def to_latlon(x, y):
    d = math.hypot(x, y)
    if d < 1e-9:
        return FIRE_LAT, FIRE_LON
    return destination(FIRE_LAT, FIRE_LON, math.degrees(math.atan2(x, y)) % 360, d)

def _angdiff(a, b):
    return (a - b + 180) % 360 - 180

def compass(deg):
    return _COMPASS[int((deg % 360) / 22.5 + 0.5) % 16]

def _in_poly(pt, poly):
    x, y = pt
    inside, j = False, len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside

# ------------------------------------------------------------------ plume shape
def _arclen(pts):
    d = np.diff(pts, axis=0)
    return np.concatenate([[0.0], np.cumsum(np.hypot(d[:, 0], d[:, 1]))])

def _wind_centerline(bearings, speeds, reach, n=40):
    pts = [(0.0, 0.0)]
    for b, s in zip(bearings, speeds):
        x, y = pts[-1]
        pts.append((x + s * math.sin(math.radians(b)), y + s * math.cos(math.radians(b))))
    traj = np.array(pts)
    cum = _arclen(traj)
    if cum[-1] < 1e-6:
        b = math.radians(bearings[0])
        traj = np.array([[0.0, 0.0], [math.sin(b), math.cos(b)]])
        cum = _arclen(traj)
    u = np.linspace(0, cum[-1], n)
    c = np.column_stack([np.interp(u, cum, traj[:, 0]), np.interp(u, cum, traj[:, 1])])
    for _ in range(4):
        c[1:-1] = 0.25 * c[:-2] + 0.5 * c[1:-1] + 0.25 * c[2:]
    return c * (reach / _arclen(c)[-1])

def _straight_centerline(bearing, reach, bow=0.04, n=40):
    s = np.linspace(0, 1, n)
    b = math.radians(bearing)
    ux, uy = math.sin(b), math.cos(b)
    off = bow * reach * np.sin(math.pi * s)
    return np.column_stack([ux * reach * s - uy * off, uy * reach * s + ux * off])

def _truncate(center, frac):
    cum = _arclen(center)
    u = np.linspace(0, frac * cum[-1], len(center))
    return np.column_stack([np.interp(u, cum, center[:, 0]), np.interp(u, cum, center[:, 1])])

def _half_width(s, hw, phase=0.0, side=0):
    s = np.asarray(s, dtype=float)
    ph = phase + 2.1 * side
    cap = np.where(s > CAP_START, np.sqrt(np.clip(1 - ((s - CAP_START) / (1 - CAP_START)) ** 2, 0, 1)), 1.0)
    wob = 1 + 0.10 * np.sin(7 * s + ph) + 0.05 * np.sin(17 * s + 1.3 * ph) + 0.03 * np.sin(31 * s + 2 * ph)
    return hw * (0.02 + 0.98 * s ** 0.85) * cap * wob

def _plume_polygon(center, hw, phase=0.0):
    d = np.diff(center, axis=0)
    s = _arclen(center)
    s = s / s[-1]
    tang = np.vstack([d, d[-1]])
    tang = tang / np.maximum(np.hypot(tang[:, 0], tang[:, 1])[:, None], 1e-9)
    nrm = np.column_stack([-tang[:, 1], tang[:, 0]])
    left = center + nrm * _half_width(s, hw, phase, 0)[:, None]
    right = center - nrm * _half_width(s, hw, phase, 1)[:, None]
    return np.vstack([left, right[::-1]])

def _rotate(pts, deg):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return np.column_stack([pts[:, 0] * c + pts[:, 1] * s, -pts[:, 0] * s + pts[:, 1] * c])

# ------------------------------------------------------------------ data discovery
_CITY_COORDS = {
    "Quebec_City": (46.8138, -71.2079), "Montreal": (45.5016, -73.5672), "Ottawa": (45.4215, -75.6971),
    "Toronto": (43.6510, -79.3470), "Albany": (42.6526, -73.7562), "New_York": (40.7128, -74.0060),
    "Philadelphia": (39.9526, -75.1652), "Washington_DC": (38.9072, -77.0369),
}

def _find_data_dir(explicit=None):
    here = Path(__file__).resolve().parent
    cands = [explicit, os.environ.get("SMOKE_DATA_DIR"), "./data", ".", here / "data", here, "/home/ibm-user/shared"]
    for c in cands:
        if c and (Path(c) / "test_predictions.csv").exists() and (Path(c) / "fire_wind.csv").exists():
            return str(c)
    return None

def _demo_data():
    n, hrs = 96, np.arange(102)
    times = pd.date_range("2023-06-07", periods=n, freq="h")
    rng = np.random.default_rng(7)
    wind = pd.DataFrame({"Time": times, "Speed_kmh": 24 + 4 * np.sin(np.arange(n) / 9),
                         "Dir_from_deg": (20 + 10 * np.sin(np.arange(n) / 20)) % 360})
    rows = []
    for city, (la, lo) in _CITY_COORDS.items():
        d = haversine_km(FIRE_LAT, FIRE_LON, la, lo)
        amp, arr = 170 * math.exp(-d / 700), d / 20
        s = np.clip(6 + amp * np.exp(-((hrs - arr) / 9.0) ** 2) + rng.normal(0, 1.5, len(hrs)), 0, None)
        for i in range(n):
            fc = max(0.0, 0.92 * s[i + 6] + rng.normal(0, 3))
            rows.append(dict(City=city, Time=times[i], Current=s[i], Actual_6h_Later=s[i + 6],
                             Forecast_6h_Later=fc, NoChange_Baseline=s[i], Lat=la, Lon=lo))
    return pd.DataFrame(rows), wind

# ------------------------------------------------------------------ engine
class PlumeEngine:
    def __init__(self, data_dir=None, threshold=ALERT_UGM3):
        self.threshold = threshold
        self.data_dir = _find_data_dir(data_dir)
        self.demo = self.data_dir is None
        if self.demo:
            self.preds, w = _demo_data()
        else:
            d = Path(self.data_dir)
            self.preds = pd.read_csv(d / "test_predictions.csv", parse_dates=["Time"])
            w = pd.read_csv(d / "fire_wind.csv", parse_dates=["Time"])
        self.wind = w.drop_duplicates("Time").sort_values("Time").set_index("Time")
        self._by_time = {pd.Timestamp(t): g.set_index("City") for t, g in self.preds.groupby("Time")}
        self.times = sorted(self._by_time)
        self._cache = {}

    def default_t0(self):
        best, best_key = self.times[0], (-1, -1, -1)
        for t, g in self._by_time.items():
            n0 = int((g["Current"] >= self.threshold).sum())
            n6 = int((g["Forecast_6h_Later"] >= self.threshold).sum())
            key = (n6 - n0, n6, float(g["Forecast_6h_Later"].sum()))
            if key > best_key:
                best, best_key = t, key
        return best

    def wind_at(self, t):
        i = self.wind.index.get_indexer([pd.Timestamp(t)], method="nearest")[0]
        r = self.wind.iloc[i]
        return float(r["Dir_from_deg"]), float(r["Speed_kmh"])

    def city_states(self, t0, h):
        t0, frac = pd.Timestamp(t0), min(max(int(h), 0), HORIZON_H) / HORIZON_H
        out = []
        for city, r in self._by_time[t0].iterrows():
            now, fc = float(r["Current"]), float(r["Forecast_6h_Later"])
            pm_h = now + (fc - now) * frac
            out.append(dict(
                city=city, lat=float(r["Lat"]), lon=float(r["Lon"]),
                dist_km=haversine_km(FIRE_LAT, FIRE_LON, r["Lat"], r["Lon"]),
                bearing=bearing_deg(FIRE_LAT, FIRE_LON, r["Lat"], r["Lon"]),
                pm_now=now, pm_6h=fc, pm_h=pm_h, actual_6h=float(r["Actual_6h_Later"]),
                flagged=pm_h >= self.threshold,
            ))
        return out

    def build(self, t0, h):
        t0, h = pd.Timestamp(t0), int(h)
        if (t0, h) in self._cache:
            return self._cache[(t0, h)]

        cities = self.city_states(t0, h)
        steps = max(h, 1)
        bearings, speeds = [], []
        for k in range(steps):
            wd, ws = self.wind_at(t0 + pd.Timedelta(hours=k))
            bearings.append((wd + 180) % 360)
            speeds.append(ws)

        px = sum(s * math.sin(math.radians(b)) for b, s in zip(bearings, speeds))
        py = sum(s * math.cos(math.radians(b)) for b, s in zip(bearings, speeds))
        chord = (math.degrees(math.atan2(px, py)) % 360) if math.hypot(px, py) > 1e-6 else bearings[0]
        adv_km = max(sum(speeds), 25.0)

        flagged = [c for c in cities if c["flagged"]]
        axis, half_angle, reach = chord, 15.0, adv_km
        if flagged:
            tot = sum(c["pm_h"] for c in flagged)
            vx, vy = math.sin(math.radians(chord)), math.cos(math.radians(chord))
            for c in flagged:
                w = 2.0 * c["pm_h"] / tot
                vx += w * math.sin(math.radians(c["bearing"]))
                vy += w * math.cos(math.radians(c["bearing"]))
            axis = math.degrees(math.atan2(vx, vy)) % 360
            need = max(abs(_angdiff(c["bearing"], axis)) for c in flagged)
            half_angle = float(np.clip(need + 6, 16, 50))
            reach = max(adv_km, 1.12 * max(c["dist_km"] for c in flagged))

        center = _rotate(_wind_centerline(bearings, speeds, reach), _angdiff(axis, chord))
        hw = reach * math.tan(math.radians(half_angle))
        for _ in range(30):
            outer = _plume_polygon(center, hw)
            if all(_in_poly(to_xy(c["lat"], c["lon"]), outer) for c in flagged):
                break
            hw *= 1.08

        wd0, ws0 = self.wind_at(t0)
        tip = (f"Smoke plume | reach {reach:.0f} km toward {compass(axis)} | wind {ws0:.0f} km/h from {compass(wd0)} | "
               f"{len(flagged)} cities above {self.threshold:.0f} ug/m3")
        polys, outers = [], []
        for name, ws_, lf in LAYERS:
            c = center if lf == 1 else _truncate(center, lf)
            poly = _plume_polygon(c, hw * ws_, 0.0)
            polys.append(dict(kind="main", layer=name, city=None, tooltip=tip,
                              coords=[to_latlon(x, y) for x, y in poly]))
            if name == "outer":
                outers.append(poly)

        out = dict(polygons=polys, outers=outers, centerlines=[dict(xy=center, hw=hw, strength=1.0)],
                   cities=cities, reach_km=reach, axis_bearing=axis, wind_from=wd0, wind_kmh=ws0)
        self._cache[(t0, h)] = out
        return out

    def in_plume(self, lat, lon, t0, h):
        p = to_xy(lat, lon)
        return any(_in_poly(p, o) for o in self.build(t0, h)["outers"])

    def eta_hour(self, lat, lon, t0, h):
        return next((i for i in range(int(h) + 1, HORIZON_H + 1) if self.in_plume(lat, lon, t0, i)), None)

    def summary(self, t0, h):
        P = self.build(t0, h)
        fl = [c for c in P["cities"] if c["flagged"]]
        peak = max(P["cities"], key=lambda c: c["pm_h"])
        names = ", ".join(c["city"].replace("_", " ") for c in fl) or "none"
        return dict(
            flagged=[c["city"] for c in fl], n_flagged=len(fl),
            peak_pm=round(peak["pm_h"], 1), peak_city=peak["city"],
            reach_km=round(P["reach_km"], 1), wind_kmh=round(P["wind_kmh"]),
            wind_from=compass(P["wind_from"]), travel_to=compass(P["axis_bearing"]),
            zone_text=(f"Plume reach {P['reach_km']:.0f} km toward {compass(P['axis_bearing'])}. "
                       f"Cities above {self.threshold:.0f} ug/m3: {names}."),
        )

    def sync_report(self, t0, h):
        P = self.build(t0, h)
        return [dict(city=c["city"], pm_h=round(c["pm_h"], 1), flagged=c["flagged"],
                     in_plume=self.in_plume(c["lat"], c["lon"], t0, h),
                     ok=(not c["flagged"]) or self.in_plume(c["lat"], c["lon"], t0, h))
                for c in P["cities"]]

    def heat_points(self, t0, h):
        P = self.build(t0, h)
        peak = float(np.clip(max(c["pm_h"] for c in P["cities"]) / 150.0, 0.2, 1.0))
        pts = []
        for cl in P["centerlines"]:
            xy, n = cl["xy"], len(cl["xy"])
            tan = np.gradient(xy, axis=0)
            tan /= np.maximum(np.hypot(tan[:, 0], tan[:, 1])[:, None], 1e-9)
            for i in range(0, n, 3):
                t = i / (n - 1)
                w = peak * cl["strength"] * (1 - 0.6 * t)
                spread = float(_half_width(t, cl["hw"])) * 0.8
                nx, ny = -tan[i, 1], tan[i, 0]
                for c in (-1.0, -0.5, 0.0, 0.5, 1.0):
                    lat, lon = to_latlon(xy[i, 0] + nx * spread * c, xy[i, 1] + ny * spread * c)
                    pts.append([lat, lon, w * (1 - 0.5 * abs(c))])
        for c in P["cities"]:
            if c["pm_h"] >= 10:
                pts.append([c["lat"], c["lon"], min(c["pm_h"] / 150.0, 1.0) * 0.9])
        return pts

    def add_to_map(self, m, t0, h, show_cities=True):
        import folium
        P = self.build(t0, h)
        for p in P["polygons"]:
            st = LAYER_STYLE[p["layer"]]
            folium.Polygon(p["coords"], color="#7a0f12", weight=st["weight"], fill=True,
                           fill_color=st["fill"], fill_opacity=st["opacity"], tooltip=p["tooltip"]).add_to(m)
        if show_cities:
            for c in P["cities"]:
                # INCLUDES FIX: Visually enforce red styling if physically enveloped in the plume!
                is_inside = self.in_plume(c["lat"], c["lon"], t0, h)
                is_danger = c["flagged"] or is_inside
                col = "#e03131" if is_danger else "#37b26c"
                status = "FLAGGED" if c["flagged"] else ("IN PLUME" if is_inside else "below threshold")
                tip = (f"{c['city'].replace('_', ' ')} | {status} | "
                       f"PM2.5 now {c['pm_now']:.0f} -> +6h forecast {c['pm_6h']:.0f} ug/m3 | at Hour {int(h)}: {c['pm_h']:.0f}")
                folium.CircleMarker((c["lat"], c["lon"]), radius=7, color="#14181d", weight=2, fill=True,
                                    fill_color=col, fill_opacity=0.95, tooltip=tip).add_to(m)
        return m

if __name__ == "__main__":
    import argparse
    import folium
    from folium.plugins import HeatMap

    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=None)
    ap.add_argument("--hour", type=int, default=6)
    ap.add_argument("--time", default=None, help="forecast issue time, e.g. '2023-06-28 12:00'")
    ap.add_argument("--heat", action="store_true", help="AQI heat map instead of plume polygons")
    a = ap.parse_args()

    eng = PlumeEngine(a.dir)
    t0 = pd.Timestamp(a.time) if a.time else eng.default_t0()
    m = folium.Map(location=(45.0, -74.5), zoom_start=5, tiles="OpenStreetMap")
    folium.Marker(IGNITION, tooltip="Fire origin", icon=folium.Icon(color="red", icon="fire", prefix="fa")).add_to(m)
    if a.heat:
        HeatMap(eng.heat_points(t0, a.hour), radius=38, blur=28, min_opacity=0.25, max_val=1.0,
                gradient=HEAT_GRADIENT).add_to(m)
    else:
        eng.add_to_map(m, t0, a.hour)
    m.save("plume_demo.html")
    print("Forecast issued:", t0, "| hour", a.hour)
    print(eng.summary(t0, a.hour))
    for r in eng.sync_report(t0, a.hour):
        print(r)
    print("Saved plume_demo.html")
