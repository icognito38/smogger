"""
plume.py - smoke plume geometry that is driven by the model's output.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

ALERT_UGM3 = 35.0
HORIZON_H = 24
CAP_START = 0.82
R_KM = 6371.0088
MODEL_H = 6.0       # the model forecasts 6h ahead; beyond that we hold its last forecast
MAX_BEND_DEG = 35.0  # max local bend of the plume centreline away from its axis
MAX_DRIFT = 0.30     # max sideways drift of the centreline, as a fraction of reach

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

def to_xy(lat, lon, f_lat, f_lon):
    d = haversine_km(f_lat, f_lon, lat, lon)
    b = math.radians(bearing_deg(f_lat, f_lon, lat, lon))
    return d * math.sin(b), d * math.cos(b)

def to_latlon(x, y, f_lat, f_lon):
    d = math.hypot(x, y)
    if d < 1e-9: return f_lat, f_lon
    return destination(f_lat, f_lon, math.degrees(math.atan2(x, y)) % 360, d)

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

def _arclen(pts):
    d = np.diff(pts, axis=0)
    return np.concatenate([[0.0], np.cumsum(np.hypot(d[:, 0], d[:, 1]))])

# ---------------------------------------------------------------------------
# Plume geometry is built in an "axis frame": u runs along the plume axis (always
# increasing, so the plume can never fold back over itself) and v is the sideways
# offset (positive = left). The finished shape is rotated into map coordinates.
# ---------------------------------------------------------------------------
def _axis_centerline(bearings, speeds, axis, reach, n=40):
    """Centreline (u, v) of length `reach`. Wind direction changes bend it sideways,
    but progress along u is monotonic, so loops and reversals cannot occur."""
    sp = np.maximum(np.asarray(speeds, dtype=float), 0.0)
    u = np.linspace(0.0, reach, n)
    if sp.sum() < 1e-6:
        return np.column_stack([u, np.zeros(n)])
    cum = np.concatenate([[0.0], np.cumsum(sp)]) / sp.sum()
    mid = 0.5 * (cum[:-1] + cum[1:])
    dev = np.clip([_angdiff(b, axis) for b in bearings], -MAX_BEND_DEG, MAX_BEND_DEG)
    slope = -np.tan(np.radians(dev))  # clockwise deviation = drift to the right (negative v)
    s = np.linspace(0.0, 1.0, n)
    sl = np.interp(s, mid, slope)
    for _ in range(3):
        sl[1:-1] = 0.25 * sl[:-2] + 0.5 * sl[1:-1] + 0.25 * sl[2:]
    v = np.concatenate([[0.0], np.cumsum(0.5 * (sl[1:] + sl[:-1]) * np.diff(u))])
    lim = MAX_DRIFT * reach
    v = lim * np.tanh(v / lim)  # soft limit, no kinks
    return np.column_stack([u, v])

def _truncate(center, frac):
    u_new = np.linspace(0.0, frac * center[-1, 0], len(center))
    return np.column_stack([u_new, np.interp(u_new, center[:, 0], center[:, 1])])

def _half_width(s, hw, phase=0.0, side=0):
    s = np.asarray(s, dtype=float)
    ph = phase + 2.1 * side
    cap = np.where(s > CAP_START, np.sqrt(np.clip(1 - ((s - CAP_START) / (1 - CAP_START)) ** 2, 0, 1)), 1.0)
    wob = 1 + 0.10 * np.sin(7 * s + ph) + 0.05 * np.sin(17 * s + 1.3 * ph) + 0.03 * np.sin(31 * s + 2 * ph)
    return hw * (0.02 + 0.98 * s ** 0.85) * cap * wob

def _plume_polygon(center, hw, phase=0.0):
    """Polygon in the axis frame. Both edges are offset sideways from a centreline whose
    u is strictly increasing, so the outline cannot cross itself."""
    s = center[:, 0] / max(center[-1, 0], 1e-9)
    left = np.column_stack([center[:, 0], center[:, 1] + _half_width(s, hw, phase, 0)])
    right = np.column_stack([center[:, 0], center[:, 1] - _half_width(s, hw, phase, 1)])
    return np.vstack([left, right[::-1]])

def _to_geo(pts, axis):
    """Axis frame (u along, v left) -> map frame (x east, y north) for a bearing `axis`."""
    t = math.radians(axis)
    st, ct = math.sin(t), math.cos(t)
    u, v = pts[:, 0], pts[:, 1]
    return np.column_stack([u * st - v * ct, u * ct + v * st])

def _find_data_dir(explicit=None):
    here = Path(__file__).resolve().parent
    cands = [explicit, os.environ.get("SMOKE_DATA_DIR"), "./data", ".", here / "data", here, "/home/ibm-user/shared"]
    for c in cands:
        if c and (Path(c) / "test_predictions.csv").exists() and (Path(c) / "fire_wind.csv").exists():
            return str(c)
    return None

class PlumeEngine:
    def __init__(self, data_dir=None, threshold=ALERT_UGM3):
        self.threshold = threshold
        self.data_dir = _find_data_dir(data_dir)
        self.demo = self.data_dir is None
        if self.demo:
            raise RuntimeError("Missing ML test_predictions.csv or fire_wind.csv in ./data/")
        d = Path(self.data_dir)
        self.preds = pd.read_csv(d / "test_predictions.csv", parse_dates=["Time"])
        w = pd.read_csv(d / "fire_wind.csv", parse_dates=["Time"])

        # Fire_Name is required. Without it, every fire except one would silently
        # fall back to the mock plume, so fail loudly instead.
        missing = [n for n, df in (("test_predictions.csv", self.preds), ("fire_wind.csv", w))
                   if "Fire_Name" not in df.columns]
        if missing:
            raise RuntimeError(
                f"{', '.join(missing)} missing the 'Fire_Name' column (stale ML output?). "
                "Re-run the model/data generator so each row carries the exact fire name "
                "used as a key in the FIRES dict."
            )
        for df in (self.preds, w):
            df["Fire_Name"] = df["Fire_Name"].astype(str).str.strip()

        self.wind = w.sort_values("Time")
        self._by_time = {pd.Timestamp(t): g for t, g in self.preds.groupby("Time")}
        self.times = sorted(self._by_time)
        self._cache = {}

    def has_ml(self, fire_name):
        return fire_name in set(self.preds["Fire_Name"]) and fire_name in set(self.wind["Fire_Name"])

    def unmatched_fires(self, fire_names):
        """Fire names in the app that have no ML data (usually a spelling mismatch)."""
        known = set(self.preds["Fire_Name"]) & set(self.wind["Fire_Name"])
        return [n for n in fire_names if n not in known]

    def default_t0(self):
        best, best_key = pd.Timestamp(self.times[0]), -1
        for t, g in self.preds.groupby("Time"):
            n_jump = (g["Forecast_6h_Later"] >= self.threshold).sum() - (g["Current"] >= self.threshold).sum()
            if n_jump > best_key:
                best, best_key = t, n_jump
        return best

    def wind_at(self, fire_name, t):
        w = self.wind[self.wind["Fire_Name"] == fire_name]
        if len(w) == 0: return 0.0, 0.0
        idx = (w["Time"] - pd.Timestamp(t)).abs().idxmin()
        r = w.loc[idx]
        return float(r["Dir_from_deg"]), float(r["Speed_kmh"])

    def city_states(self, fire_name, f_lat, f_lon, t0, h):
        t0 = pd.Timestamp(t0)
        # Interpolate now -> +6h forecast, then HOLD the forecast. The old code kept extrapolating
        # past hour 6 (up to 4x the change), which pushed cities to absurd values or to zero.
        frac = min(max(h / MODEL_H, 0.0), 1.0)
        out = []
        if t0 not in self._by_time: return out

        g = self._by_time[t0]
        rows = g[g["Fire_Name"] == fire_name]
        for _, r in rows.iterrows():
            now, fc = float(r["Current"]), float(r["Forecast_6h_Later"])
            pm_h = max(0.0, now + (fc - now) * frac)
            lat, lon = float(r["Lat"]), float(r["Lon"])
            out.append(dict(
                city=r["City"], lat=lat, lon=lon,
                dist_km=haversine_km(f_lat, f_lon, lat, lon),
                bearing=bearing_deg(f_lat, f_lon, lat, lon),
                pm_now=now, pm_6h=fc, pm_h=pm_h, actual_6h=float(r["Actual_6h_Later"]),
                flagged=pm_h >= self.threshold,
            ))
        return out

    def build(self, fire_name, f_lat, f_lon, t0, h):
        cache_key = (fire_name, pd.Timestamp(t0), h)
        if cache_key in self._cache: return self._cache[cache_key]

        cities = self.city_states(fire_name, f_lat, f_lon, t0, h)
        steps = max(h, 1)
        bearings, speeds = [], []
        for k in range(steps):
            wd, ws = self.wind_at(fire_name, t0 + pd.Timedelta(hours=k))
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

        center = _axis_centerline(bearings, speeds, axis, reach)
        hw = reach * math.tan(math.radians(half_angle))

        def geo_outer(width):
            return _to_geo(_plume_polygon(center, width), axis)

        # widen until every flagged city is inside the outer shape
        max_hw = reach * 1.5
        for _ in range(15):
            if all(_in_poly(to_xy(c["lat"], c["lon"], f_lat, f_lon), geo_outer(hw)) for c in flagged):
                break
            hw = min(hw * 1.15, max_hw)
            if hw >= max_hw: break

        wd0, ws0 = self.wind_at(fire_name, t0)
        tip = (f"Smoke plume | reach {reach:.0f} km toward {compass(axis)} | wind {ws0:.0f} km/h from {compass(wd0)} | "
               f"{len(flagged)} cities above {self.threshold:.0f} ug/m3")
        polys, outers = [], []
        for name, ws_, lf in LAYERS:
            c = center if lf == 1 else _truncate(center, lf)
            poly = _to_geo(_plume_polygon(c, hw * ws_, 0.0), axis)
            polys.append(dict(kind="main", layer=name, city=None, tooltip=tip, coords=[to_latlon(x, y, f_lat, f_lon) for x, y in poly]))
            if name == "outer":
                outers.append(poly)

        out = dict(polygons=polys, outers=outers, centerlines=[dict(xy=_to_geo(center, axis), hw=hw, strength=1.0)],
                   cities=cities, reach_km=reach, axis_bearing=axis, wind_from=wd0, wind_kmh=ws0)
        self._cache[cache_key] = out
        return out

    def in_plume(self, lat, lon, fire_name, f_lat, f_lon, t0, h):
        p = to_xy(lat, lon, f_lat, f_lon)
        return any(_in_poly(p, o) for o in self.build(fire_name, f_lat, f_lon, t0, h)["outers"])

    def eta_hour(self, lat, lon, fire_name, f_lat, f_lon, t0, h):
        return next((i for i in range(int(h) + 1, HORIZON_H + 1) if self.in_plume(lat, lon, fire_name, f_lat, f_lon, t0, i)), None)

    def summary(self, fire_name, f_lat, f_lon, t0, h):
        P = self.build(fire_name, f_lat, f_lon, t0, h)
        fl = [c for c in P["cities"] if c["flagged"]]
        peak = max(P["cities"], key=lambda c: c["pm_h"]) if P["cities"] else {"pm_h": 0, "city": "N/A"}
        names = ", ".join(c["city"].replace("_", " ") for c in fl) or "none"
        return dict(
            flagged=[c["city"] for c in fl], n_flagged=len(fl),
            peak_pm=round(peak["pm_h"], 1), peak_city=peak["city"],
            reach_km=round(P["reach_km"], 1), wind_kmh=round(P["wind_kmh"]),
            wind_from=compass(P["wind_from"]), travel_to=compass(P["axis_bearing"]),
            zone_text=(f"Plume reach {P['reach_km']:.0f} km toward {compass(P['axis_bearing'])}. "
                       f"Cities above {self.threshold:.0f} ug/m3: {names}."),
        )

    def heat_points(self, fire_name, f_lat, f_lon, t0, h):
        P = self.build(fire_name, f_lat, f_lon, t0, h)
        peak = float(np.clip(max(c["pm_h"] for c in P["cities"]) / 150.0, 0.2, 1.0)) if P["cities"] else 0.5
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
                    lat, lon = to_latlon(xy[i, 0] + nx * spread * c, xy[i, 1] + ny * spread * c, f_lat, f_lon)
                    pts.append([lat, lon, w * (1 - 0.5 * abs(c))])
        for c in P["cities"]:
            if c["pm_h"] >= 10:
                pts.append([c["lat"], c["lon"], min(c["pm_h"] / 150.0, 1.0) * 0.9])
        return pts

    def add_to_map(self, m, fire_name, f_lat, f_lon, t0, h, show_cities=True):
        import folium
        P = self.build(fire_name, f_lat, f_lon, t0, h)
        for p in P["polygons"]:
            st = LAYER_STYLE[p["layer"]]
            folium.Polygon(p["coords"], color="#7a0f12", weight=st["weight"], fill=True,
                           fill_color=st["fill"], fill_opacity=st["opacity"], tooltip=p["tooltip"]).add_to(m)
        if show_cities:
            self.add_cities_to_map(m, [(fire_name, f_lat, f_lon)], t0, h)
        return m

    def add_cities_to_map(self, m, fires, t0, h):
        """Draw each city ONCE, using its worst status across every fire in `fires`
        (list of (name, lat, lon)). Cities are shared between fires (e.g. San Francisco), and
        drawing them per fire let a green marker from one fire hide a red one from another."""
        import folium
        agg = {}
        for name, f_lat, f_lon in fires:
            P = self.build(name, f_lat, f_lon, t0, h)
            for c in P["cities"]:
                key = (round(c["lat"], 3), round(c["lon"], 3))
                inside = self.in_plume(c["lat"], c["lon"], name, f_lat, f_lon, t0, h)
                e = agg.setdefault(key, dict(c=c, flagged=False, inside=False, fires=[]))
                e["flagged"] = e["flagged"] or c["flagged"]
                e["inside"] = e["inside"] or inside
                e["fires"].append(name)
                if c["pm_h"] >= e["c"]["pm_h"]:
                    e["c"] = c
        for e in agg.values():
            c = e["c"]
            is_danger = e["flagged"] or e["inside"]
            col = "#e03131" if is_danger else "#37b26c"
            status = "FLAGGED" if e["flagged"] else ("IN PLUME" if e["inside"] else "below threshold")
            tip = (f"{c['city'].replace('_', ' ')} | {status} | "
                   f"PM2.5 now {c['pm_now']:.0f} -> +6h forecast {c['pm_6h']:.0f} ug/m3 | at Hour {int(h)}: {c['pm_h']:.0f}")
            if len(e["fires"]) > 1:
                tip += f" | affected by {len(e['fires'])} fires"
            folium.CircleMarker((c["lat"], c["lon"]), radius=7, color="#14181d", weight=2, fill=True,
                                fill_color=col, fill_opacity=0.95, tooltip=tip).add_to(m)
        return m
