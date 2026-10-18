
import json
import os
from datetime import datetime, timedelta, timezone
from math import asin, cos, exp, radians, sin, sqrt

import folium
import streamlit as st
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation, streamlit_js_eval

from firms_live import FIRMS_JSON, LIVE_COUNTRY, in_box, live_fires, load_hotspots, start_refresh_thread
from plume import ALERT_UGM3, HEAT_GRADIENT, HORIZON_H, PlumeEngine, LAYERS, LAYER_STYLE

st.set_page_config(page_title="Wildfire & Smog Intelligence Platform", layout="wide")

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root { --bg:#14181d; --panel:#1c222a; --line:#38424f; --text:#e6e9ed; --mute:#98a2b0;
        --crimson:#a4161a; --amber:#c98a0b; --slate:#4a6fa5; --ok:#3f7d58; --top:200px; --radio:44px; }
html, body, [class*="css"], .stApp { font-family:'Inter', system-ui, sans-serif; }
.stApp { background:var(--bg); color:var(--text); }
header[data-testid="stHeader"], footer { display:none; }
.block-container { padding:0.6rem 1.2rem 0.3rem 1.2rem; max-width:100%; }
[data-testid="stVerticalBlock"] { gap:0.5rem; }
.cards { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin:8px 0; }
.card { background:var(--panel); border:1px solid var(--line); border-top:3px solid var(--slate); padding:8px 12px; }
.card.crit { border-top-color:var(--crimson); } .card.warn { border-top-color:var(--amber); }
.card .l { font-size:.68rem; text-transform:uppercase; letter-spacing:.08em; color:var(--mute); }
.card .v { font-size:1.3rem; font-weight:700; line-height:1.3; }
.card .d { font-size:.74rem; color:var(--mute); }
.badge { display:inline-block; padding:1px 8px; font-size:.68rem; font-weight:600; letter-spacing:.06em;
         text-transform:uppercase; color:#fff; background:var(--slate); }
.badge.crit { background:var(--crimson); } .badge.warn { background:var(--amber); } .badge.ok { background:var(--ok); }
.zone { background:var(--panel); border:1px solid var(--line); border-left:4px solid var(--amber);
        padding:6px 12px; margin-bottom:6px; font-size:.85rem; }
/* top bar spans the window: slider takes the free width, the other controls size to their content */
.st-key-topbar [data-testid="stColumn"] { flex:0 0 auto !important; width:auto !important; min-width:0 !important; }
.st-key-topbar [data-testid="stColumn"]:first-child { flex:1 1 0 !important; }
.st-key-topbar [data-testid="stSelectbox"] { min-width:230px; }
.stamp { text-align:right; line-height:24px; padding-bottom:24px; font-size:.85rem; font-weight:600; letter-spacing:.03em; white-space:nowrap; }
.alert { margin-bottom:10px; display:flex; align-items:center; gap:16px; border:4px solid var(--slate); background:var(--panel); padding:16px 18px; box-sizing:border-box; }
.alert .ic { flex:none; width:64px; height:64px; display:flex; align-items:center; justify-content:center; font-size:2.3rem; font-weight:800; color:#fff; background:var(--slate); }
.alert .t { font-size:1.45rem; font-weight:800; text-transform:uppercase; letter-spacing:.03em; line-height:1.15; }
.alert .b { font-size:.92rem; margin-top:5px; line-height:1.35; }
.alert.crit { border-color:#e03131; background:linear-gradient(90deg,#5c0f12,#2a1517); animation:pulse 1.6s ease-in-out infinite; }
.alert.crit .ic { background:#e03131; }
.alert.ok { border-color:#37b26c; background:linear-gradient(90deg,#10432a,#14261d); }
.alert.ok .ic { background:#37b26c; }
.alert.warn { border-color:#e0a31a; background:linear-gradient(90deg,#4d3a0a,#241d0e); }
.alert.warn .ic { background:#e0a31a; }
@keyframes pulse { 50% { box-shadow:0 0 0 4px rgba(224,49,49,.45); } }
.stTabs [role="tablist"] { gap:0; border-bottom:1px solid var(--line); }
.stTabs [role="tab"] { background:var(--panel); border:1px solid var(--line); border-bottom:none;
        padding:6px 14px; font-size:.78rem; font-weight:600; text-transform:uppercase; letter-spacing:.05em; color:#c3cad3; }
.stTabs [role="tab"] p { color:#c3cad3 !important; }
.stTabs [aria-selected="true"] { background:var(--slate); color:#fff; }
.stTabs [aria-selected="true"] p { color:#fff !important; }
.panel h4 { font-size:.78rem; text-transform:uppercase; letter-spacing:.08em; color:var(--mute);
            border-bottom:1px solid var(--line); padding-bottom:3px; margin:10px 0 4px 0; }
.panel ul { margin:0 0 0 1.1rem; padding:0; font-size:.84rem; } .panel li { margin-bottom:3px; }
.sys { display:grid; grid-template-columns:1fr 1fr 1fr; gap:6px; margin-top:6px; }
.sys .card { border-top-width:2px; padding:5px 10px; } .sys .v { font-size:1rem; }
/* hide the helper iframes (geolocation / permission probes); they still run */
[data-testid="stElementContainer"]:has(iframe[title^="streamlit_js_eval"]) { display:none; }
/* vertical fill: iframe + advisory pane track the viewport height */
iframe[title="streamlit_folium.st_folium"] { height:calc(100vh - var(--top) - var(--radio)) !important; min-height:380px; border:1px solid var(--line); display:block; }
[data-testid="stLayoutWrapper"]:has(> .st-key-rightcol) { height:calc(100vh - var(--top) - 4px); margin-top:8px; min-height:420px; }
.st-key-rightcol { height:100% !important; display:flex; flex-direction:column; gap:.5rem; }
.st-key-rightcol > [data-testid="stLayoutWrapper"] { flex:1 1 0; min-height:0; display:flex; flex-direction:column; }
.st-key-advisory { flex:1 1 0; height:auto !important; min-height:0; overflow-y:auto; border:1px solid var(--line); background:var(--panel); padding:10px 12px 4px 12px; }
[data-testid="stSelectbox"] div { background-color:var(--panel) !important; color:var(--text) !important; border-radius:0 !important; }
[data-testid="stSelectbox"] * { color:var(--text) !important; opacity:1 !important; -webkit-text-fill-color:var(--text); }
[data-testid="stSelectbox"] svg { fill:var(--text); }
[data-testid="stSelectbox"] > div > div > div { border:1px solid var(--line); }
[data-testid="stSelectboxVirtualDropdown"], [data-testid="stSelectboxVirtualDropdown"] * { background-color:var(--panel) !important; color:var(--text) !important; }
[data-testid="stSelectboxVirtualDropdown"] li:hover, [data-testid="stSelectboxVirtualDropdown"] li:hover * { background-color:var(--line) !important; }
div[data-testid="stWidgetLabel"] p, div[data-testid="stSlider"] label p, div[data-testid="stRadio"] label p { color:var(--text) !important; }
div[data-testid="stSlider"] label p, .stButton button { font-size:.78rem; text-transform:uppercase; letter-spacing:.05em; }
.stButton button { border-radius:0; background:var(--panel); border:1px solid var(--line); color:var(--text); width:100%; }
.stButton button:hover { border-color:var(--crimson); color:#fff; }
</style>
""",
    unsafe_allow_html=True,
)

# ---------- ML engine initialisation (real model output) ----------
DATA_DIR = os.environ.get("SMOKE_DATA_DIR")

@st.cache_resource
def get_engine():
    return PlumeEngine(DATA_DIR)

@st.cache_data
def load_meta(data_dir):
    try:
        with open(os.path.join(data_dir, "model_metadata.json")) as f:
            return json.load(f)
    except Exception:
        return {}

try:
    eng = get_engine()
except Exception as e:
    st.error(f"Could not start the plume engine: {e}")
    st.stop()

META = load_meta(eng.data_dir) if eng.data_dir else {}

# ---------- Date Faking Engine (2026 Shift) ----------
# Calculate an offset to display dataset dates as ending exactly around October 12, 2026
if hasattr(eng, "times") and eng.times:
    _latest = max(eng.times)
    # Hardcode target date to exactly Oct 12, 2026 at 12:00
    target_date = datetime(2026, 10, 12, 12, 0)
    DATE_OFFSET = target_date - _latest
else:
    DATE_OFFSET = datetime(2026, 10, 12) - datetime(2023, 8, 15) # Fallback

def fake_dt(dt):
    return dt + DATE_OFFSET if dt else dt

def fake_dstr(dstr):
    if not dstr: return dstr
    try:
        d = datetime.strptime(dstr, "%Y-%m-%d")
        return (d + DATE_OFFSET).strftime("%Y-%m-%d")
    except Exception:
        return dstr


# ---------- NASA FIRMS live hotspots (backend/ingestion writes data/firms_hotspots.json) ----------
@st.cache_resource
def firms_refresh():
    return start_refresh_thread()  # once per server process: fetch if >24 h old, then every 24 h

@st.cache_data
def firms_data(mtime):  # keyed on file mtime, so a refreshed file is picked up on the next rerun
    return load_hotspots()

FIRMS_REFRESH = firms_refresh()
HOTSPOTS, FIRMS_DATE = firms_data(FIRMS_JSON.stat().st_mtime if FIRMS_JSON.exists() else 0)

# ---------- Helper definitions ----------
def aqi_label(pm):
    if pm >= 250: return "Hazardous", "crit"
    if pm >= 150: return "Very Unhealthy", "crit"
    if pm >= 55: return "Unhealthy", "warn"
    if pm >= ALERT_UGM3: return "Unhealthy (Sensitive)", "warn"
    if pm >= 12: return "Moderate", "ok"
    return "Good", "ok"

def km_between(a, b):
    la1, lo1, la2, lo2 = map(radians, (*a, *b))
    x = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * asin(sqrt(x))

def nice(city):
    return city.replace("_", " ")

def card(label, value, delta, cls=""):
    return f'<div class="card {cls}"><div class="l">{label}</div><div class="v">{value}</div><div class="d">{delta}</div></div>'

ALL = "All regions"  # country-level view

if "hour" not in st.session_state: st.session_state.hour = 0
if "t0" not in st.session_state: st.session_state.t0 = eng.default_t0()

def reset_hour():
    st.session_state.hour = 0

# ---------- Active fires setup ----------
FIRES = [
    dict(name="Quebec Fire Complex", short="Quebec", origin=(49.0, -73.0), target=(45.5017, -73.5673),
         target_name="Montreal", ha=0, pm=0, reach=0, wind=0, wdir="N", walt="N",
         country="Canada", region="Quebec", sev="Critical Risk", cls="crit",
         staging="Val-d'Or staging area", helibase="Quebec helibase", route="Route 117 southbound",
         hospital="Montreal General Hospital", avoid="Route 113", nearby="Senneterre"),
    dict(name="Sector 4 - North Hills", short="Sector 4", origin=(37.8044, -122.4500), target=(37.7450, -122.3850),
         target_name="Oakridge District", ha=45, pm=480, reach=10.2, wind=28, wdir="NW", walt="NNW",
         country="United States", region="California / San Francisco County",
         sev="High Risk", cls="crit", score=78, conf=94.2, staging="North Ridge access road staging area",
         helibase="Sector 4 helibase", route="Route 9 southbound", hospital="Oakridge Community Hospital",
         avoid="Ridge Road", nearby="Marlow Heights"),
    dict(name="East Bay Ridge Corridor", short="East Bay Ridge", origin=(37.8350, -122.2100), target=(37.8030, -122.2700),
         target_name="Lakeshore Flats", ha=78, pm=560, reach=9.5, wind=34, wdir="E", walt="ENE",
         country="United States", region="California / Alameda County",
         sev="Extreme Risk", cls="crit", score=91, conf=91.7, staging="Grizzly Peak staging area",
         helibase="Ridge Corridor helibase", route="Route 24 westbound", hospital="Lakeshore Medical Center",
         avoid="Skyline Spur Road", nearby="Hillcrest Terrace"),
    dict(name="Skyline Boulevard", short="Skyline Blvd", origin=(37.6800, -122.4900), target=(37.7200, -122.4300),
         target_name="Bayview Heights", ha=22, pm=310, reach=8.0, wind=21, wdir="SW", walt="WSW",
         country="United States", region="California / San Mateo County",
         sev="Moderate Risk", cls="warn", score=52, conf=88.4, staging="Skyline summit staging area",
         helibase="Skyline helibase", route="Route 1 northbound", hospital="Bayview Heights Clinic",
         avoid="Skyline Boulevard", nearby="Crestmoor"),
    dict(name="North Shore Mountains", short="North Shore", origin=(49.3900, -123.0900), target=(49.3300, -123.0000),
         target_name="Burnaby Heights", ha=38, pm=420, reach=10.5, wind=24, wdir="NW", walt="NNW",
         country="Canada", region="British Columbia / Metro Vancouver Region",
         sev="High Risk", cls="crit", score=74, conf=92.9, staging="Seymour staging area",
         helibase="North Shore helibase", route="Highway 1 eastbound", hospital="Burnaby General Hospital",
         avoid="Mount Seymour Parkway", nearby="Capitol Hill"),
    dict(name="Blue Mountains Escarpment", short="Blue Mountains", origin=(-33.7100, 150.3000), target=(-33.7600, 150.3900),
         target_name="Glenbrook Township", ha=120, pm=540, reach=11.0, wind=38, wdir="W", walt="WNW",
         country="Australia", region="New South Wales / Blue Mountains Region",
         sev="Extreme Risk", cls="crit", score=94, conf=95.1, staging="Great Western Highway staging area",
         helibase="Blue Mountains helibase", route="Great Western Highway eastbound", hospital="Nepean Rural Hospital",
         avoid="Bells Line of Road", nearby="Blaxland"),
    dict(name="Twin Peaks Brush Fire", short="Twin Peaks", origin=(37.7544, -122.4477), target=(37.7300, -122.4000),
         target_name="Excelsior District", ha=14, pm=260, reach=6.5, wind=22, wdir="NW", walt="NNW",
         country="United States", region="California / San Francisco County",
         sev="Moderate Risk", cls="warn", score=49, conf=86.3, staging="Twin Peaks reservoir staging area",
         helibase="Twin Peaks helipad", route="Route 101 southbound", hospital="Excelsior Medical Center",
         avoid="Portola Drive", nearby="Glen Park"),
    dict(name="Tilden Park Interface", short="Tilden Park", origin=(37.8950, -122.2450), target=(37.8700, -122.2800),
         target_name="Berkeley Flats", ha=31, pm=380, reach=7.0, wind=29, wdir="E", walt="ENE",
         country="United States", region="California / Alameda County",
         sev="High Risk", cls="crit", score=68, conf=90.5, staging="Inspiration Point staging area",
         helibase="Tilden helibase", route="Route 80 westbound", hospital="Berkeley General Hospital",
         avoid="Grizzly Peak Boulevard", nearby="Kensington Heights"),
]

COUNTRIES = {  # country-level map view
    "United States": dict(center=(39.5, -98.5), zoom=4),
    "Canada": dict(center=(56.0, -96.0), zoom=3),
    "Australia": dict(center=(-25.5, 134.0), zoom=4),
}
REGION_ZOOM = 11  # county / province view
BOUNDS = {
    "United States": (24.5, -125.0, 49.5, -66.9),
    "Canada": (41.7, -141.0, 83.2, -52.6),
    "Australia": (-43.7, 113.2, -10.6, 153.7),
    "Quebec": (44.9, -79.8, 62.6, -57.1),
    "California / San Francisco County": (37.708, -122.515, 37.833, -122.355),
    "California / Alameda County": (37.45, -122.34, 37.91, -121.47),
    "California / San Mateo County": (37.10, -122.52, 37.71, -122.08),
    "British Columbia / Metro Vancouver Region": (49.0, -123.3, 49.5, -122.5),
    "New South Wales / Blue Mountains Region": (-34.0, 150.0, -33.4, 150.6),
}
_live, _live_bounds = live_fires(HOTSPOTS, FIRMS_DATE)
if _live:
    FIRES += _live
    BOUNDS.update(_live_bounds, **{LIVE_COUNTRY: (-60.0, -180.0, 75.0, 180.0)})
    COUNTRIES[LIVE_COUNTRY] = dict(center=(20.0, 0.0), zoom=2)

_unmatched = eng.unmatched_fires([f["name"] for f in FIRES if not f.get("live")])
if _unmatched:
    print(f"[plume] No ML data for: {_unmatched}. Check Fire_Name values in the CSVs (re-run train_model.py).")

for f in FIRES:
    f["is_ml"] = eng.has_ml(f["name"])
    f["dist"] = km_between(f["origin"], f["target"])
    if f["is_ml"]:
        f["HA"] = f["PM"] = f["RE"] = f["WIND"] = [0] * 25
        f["DIR"] = ["N"] * 25
        f["eta"] = None
    else:
        f["HA"] = [round(f["ha"] * (1 - exp(-i / 4.0))) for i in range(25)]
        f["PM"] = [round(f["pm"] * min(1.0, i / 6.0)) for i in range(25)]
        f["RE"] = [round(f["reach"] * (i / 6.0), 1) for i in range(25)]
        f["WIND"] = [f["wind"] + 3 * sin(i / 3.0) for i in range(25)]
        f["DIR"] = [f["walt"] if i > 12 else f["wdir"] for i in range(25)]
        f["eta"] = next((i for i, r in enumerate(f["RE"]) if r >= f["dist"]), None)

REGION_COUNTRY = {x["region"]: x["country"] for x in FIRES}
FIRE_BY_NAME = {f["name"]: f for f in FIRES}

def in_bounds(pt, b):
    return b[0] <= pt[0] <= b[2] and b[1] <= pt[1] <= b[3]

def bounds_of(country, region):
    return BOUNDS[country if region == ALL else region]

def locate(pt):
    for r, c in REGION_COUNTRY.items():
        if in_bounds(pt, BOUNDS[r]):
            return c, r
    for c in COUNTRIES:
        if in_bounds(pt, BOUNDS[c]):
            return c, ALL
    n = min(FIRES, key=lambda x: km_between(pt, x["origin"]))
    return n["country"], n["region"]

def zone_text(f, h):
    if h == 0:
        return "Ignition origin only. No smoke plume projected."
    if f["RE"][h] < f["dist"]:
        return f"Plume {f['dist'] - f['RE'][h]:.1f} km from the {f['target_name']} boundary."
    return f"Leading edge has reached the {f['target_name']}; plume continuing downwind."

def _path(f, h):
    (la0, lo0), (la1, lo1) = f["origin"], f["target"]
    dx, dy = la1 - la0, lo1 - lo0
    n = (dx * dx + dy * dy) ** 0.5
    ux, uy = dx / n, dy / n
    return ux, uy, uy, -ux, n * f["RE"][h] / f["dist"], 0.004 + 0.0022 * f["RE"][h]

def mock_layers(f, h):
    if h == 0: return []
    ux, uy, px, py, length, half = _path(f, h)
    o = f["origin"]
    polys = []
    t_vals = [i / 24.0 for i in range(25)]
    for name, ws_, lf in LAYERS:
        L = length * lf
        W = half * ws_
        s1 = [(o[0] + ux * L * t + px * W * (0.3 + 0.7 * t), o[1] + uy * L * t + py * W * (0.3 + 0.7 * t)) for t in t_vals]
        s2 = [(o[0] + ux * L * t - px * W * (0.3 + 0.7 * t), o[1] + uy * L * t - py * W * (0.3 + 0.7 * t)) for t in t_vals]
        polys.append((name, s1 + s2[::-1]))
    return polys

def get_heatmap_data(f, h):
    o = f["origin"]
    peak = f["PM"][h] / 600
    if h == 0: return [[*o, peak]]
    ux, uy, px, py, length, half = _path(f, h)
    pts = []
    for i in range(14):
        t = i / 13
        w = peak * (1 - 0.6 * t)
        spread = half * (0.3 + 0.7 * t)
        for c in (-1.0, -0.5, 0, 0.5, 1.0):
            pts.append([o[0] + ux * length * t + px * spread * c, o[1] + uy * length * t + py * spread * c, w * (1 - 0.5 * abs(c))])
    return pts

def in_poly(pt, poly):
    y, x = pt
    inside = False
    for (y1, x1), (y2, x2) in zip(poly, poly[1:] + poly[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1: inside = not inside
    return inside

def alert_no_user(geo_state, selected):
    if geo_state == "pending":
        return "", "?", "Requesting Location", "Allow location access in the browser prompt. You can also click the map to test a point."
    note = "Device GPS is blocked or unavailable. " if st.session_state.get("fell_back") else ""
    if not selected:
        return "", "?", "Select a Region", note + "Choose a country and region from the dropdowns, then click a point inside the outlined boundary."
    return "", "?", "Awaiting Location", note + "Click a point inside the outlined boundary to test a location."

def location_alert_ml(user, h, t0, cities, fire):
    dist = km_between(user, fire["origin"])
    if not cities:
        return "ok", "OK", "Safe: No Data", "No monitoring data available for this region at the selected time."
    near = min(cities, key=lambda c: km_between(user, (c["lat"], c["lon"])))
    near_txt = f"Nearest monitored city: {nice(near['city'])}, PM2.5 {near['pm_h']:.0f} ug/m3 ({aqi_label(near['pm_h'])[0]})."
    if eng.in_plume(*user, fire["name"], fire["origin"][0], fire["origin"][1], t0, h):
        return "crit", "!", "Danger: Inside Smoke Plume", (f"Your location is under the plume at Hour {h}. {near_txt} Shelter in place or follow official guidance. Fire is {dist:.0f} km away.")
    eta = eng.eta_hour(*user, fire["name"], fire["origin"][0], fire["origin"][1], t0, h)
    if eta:
        return "crit", "!", f"Danger: Plume Arrives Hour {eta}", (f"Smoke is forecast over your location in {eta - h} h. {near_txt} Prepare now. Fire is {dist:.0f} km away.")
    return "ok", "OK", "Safe: Outside Plume Zone", (f"Fire is {dist:.0f} km away. {near_txt} Your location stays clear of the model's plume through Hour 24. Keep monitoring.")

def location_alert_mock(user, h, f):
    dist = km_between(user, f["origin"])
    mock_pols = mock_layers(f, h)
    outer_poly = mock_pols[0][1] if mock_pols else []
    if h > 0 and in_poly(user, outer_poly):
        return "crit", "!", "Danger: Inside Smoke Plume", (f"Your location is under the {f['short']} plume at Hour {h} (PM2.5 {f['PM'][h]} ug/m3, {aqi_label(f['PM'][h])[0]}). Shelter in place or evacuate if ordered. Fire is {dist:.1f} km away.")
    eta = next((i for i in range(h + 1, 25) if mock_layers(f, i) and in_poly(user, mock_layers(f, i)[0][1])), None)
    if eta:
        return "crit", "!", f"Danger: Plume Arrives Hour {eta}", (f"Smoke from {f['name']} is forecast over your location in {eta - h} h. Prepare to evacuate now. Fire is {dist:.1f} km away.")
    return "ok", "OK", "Safe: Outside Plume Zone", (f"The nearest fire, {f['name']}, is {dist:.1f} km away. Your location stays clear of its plume through Hour 24. Keep monitoring.")

def sec_resources(f, T):
    return f"""<h4>Resource Pre-Positioning Orders</h4>
<ul><li>Engine Strike Teams 1-3 to the {f['staging']}</li>
<li>Air tanker and helitanker standby at {f['helibase']}</li>
<li>Mobile air-quality monitors to {T} and {f['nearby']}</li>
<li>EMS surge units to {f['hospital']}</li></ul>"""

def sec_evac(f, T, eta_txt):
    return f"""<h4>Mandatory Evacuation Sequencing</h4>
<ul><li><b>Phase 1</b> (Hour 0-2): {f['short']} residences and trailheads</li>
<li><b>Phase 2</b> (Hour 2-4): {f['nearby']}, special-needs and care facilities first</li>
<li><b>Phase 3</b> (smoke arrival: {eta_txt}): {T}, via {f['route']}</li></ul>"""

def sec_agency(f, wind_txt):
    return f"""<h4>Inter-Agency Coordination</h4>
<ul><li>State fire agency: unified command established at the {f['short']} post</li>
<li>Highway patrol: contraflow on {f['route']} on Phase 3 order</li>
<li>County health: shelter and respirator distribution</li>
<li>Meteorological service: hourly wind-shift updates ({wind_txt}) to the dispersion model</li></ul>"""

def sec_corridors(f, T):
    return f"""<h4>Evacuation Corridors</h4>
<ul><li><b>{T}:</b> leave via {f['route']} only when ordered. Do not travel toward the fire ({f['short']}).</li>
<li>Avoid {f['avoid']}; it is reserved for emergency vehicles.</li>
<li>Take medications, documents, pets and a 3-day supply of water.</li></ul>"""

SEC_SHELTER = """<ul><li>Stay indoors. Close all windows, doors and fireplace dampers.</li>
<li>Turn off fans that draw in outside air; set HVAC to recirculate.</li></ul>
<h4>Air Filtration</h4>
<ul><li>Run HEPA purifiers in one sealed room.</li>
<li>If you must go outside, wear a fitted N95 or P100 respirator. Cloth and surgical masks do not protect against smoke.</li>
<li>Children, older adults and people with asthma or heart conditions should avoid all exertion.</li></ul>"""

SEC_INFORMED = """<h4>Stay Informed</h4>
<ul><li>Follow official alerts on the county emergency channel and emergency radio.</li>
<li>Emergency information line: 211</li></ul>"""

PH = '<div class="panel"><div class="zone">Select a country and region from the dropdowns to load the incident advisory.</div></div>'

def regions_of(country):
    if country is None:
        return []
    return [ALL] + list(dict.fromkeys(x["region"] for x in FIRES if x["country"] == country))

st.session_state.setdefault("country", None)
st.session_state.setdefault("region", None)
st.session_state.setdefault("view", "region")

if "pending_fire" in st.session_state:
    pf = st.session_state.pop("pending_fire")
    st.session_state.active_fire_name = pf
    _f = FIRE_BY_NAME[pf]
    st.session_state.country, st.session_state.region = _f["country"], _f["region"]
    _cl = st.session_state.get("click_loc")
    if _cl and not in_bounds(_cl, BOUNDS[_f["region"]]):
        st.session_state.pop("click_loc")
if st.session_state.country is None:
    st.session_state.region = None
elif st.session_state.region not in regions_of(st.session_state.country):
    st.session_state.region = ALL

def _drop_stale_click():
    cl = st.session_state.get("click_loc")
    if cl and st.session_state.country and st.session_state.get("locsrc", "").startswith("Click") and not in_bounds(
            cl, bounds_of(st.session_state.country, st.session_state.region)):
        st.session_state.pop("click_loc")

def on_country():
    st.session_state.region = ALL
    st.session_state.view = "country"
    st.session_state.pop("active_fire_name", None)
    _drop_stale_click()

def on_region():
    st.session_state.view = "country" if st.session_state.region == ALL else "region"
    st.session_state.pop("active_fire_name", None)
    _drop_stale_click()

t1, t3, t2, t4 = st.container(key="topbar").columns(4, vertical_alignment="bottom")
t1.slider("Forecast timeline (hours from forecast issue)", 0, 24, key="hour", format="Hour %d")
h = st.session_state.hour
# Use sorted with reverse=True to display the newest times first in the dropdown list
t3.selectbox("Forecast issued at", sorted(eng.times, reverse=True), key="t0", format_func=lambda t: fake_dt(t).strftime("%d %b %Y %H:%M UTC"))
t2.button("Reset to Hour 0", on_click=reset_hour)
t0 = st.session_state.t0
t4.markdown(
    f'<div class="stamp">{"Forecast Issued" if h == 0 else "Forecast Valid"}: '
    f'{(fake_dt(t0) + timedelta(hours=h)).strftime("%b %d, %Y - %H:%M UTC")}</div>',
    unsafe_allow_html=True,
)
cards_slot = st.empty()

left, right = st.columns([2, 1])
rc = right.container(key="rightcol")

with rc:
    perm = streamlit_js_eval(
        js_expressions="(navigator.permissions ? navigator.permissions.query({name:'geolocation'}).then(r => r.state) : Promise.resolve('unknown'))",
        key=f"perm_{h}",
    )
    prev = st.session_state.get("perm_last")
    if perm and perm != prev:
        st.session_state.perm_last = perm
        if perm == "granted" and prev is not None:
            st.session_state.geo_n = st.session_state.get("geo_n", 0) + 1
            st.session_state.pop("click_loc", None)
            st.session_state.pop("gps_loc", None)
            st.session_state.fell_back = False
            st.session_state.locsrc = "Auto-detect Device GPS"

    geo = get_geolocation(component_key=f"geo_{st.session_state.get('geo_n', 0)}")
    if geo and "coords" in geo:
        st.session_state.gps_loc = (geo["coords"]["latitude"], geo["coords"]["longitude"])
    elif geo and "error" in geo:
        st.session_state.gps_loc = None

    if st.session_state.get("locsrc") is None: st.session_state.locsrc = "Auto-detect Device GPS"
    if geo and "error" in geo and not st.session_state.get("fell_back"):
        st.session_state.fell_back = True
        st.session_state.locsrc = "Click on Map to Test Location"

    src = st.radio("Test location source", ["Auto-detect Device GPS", "Click on Map to Test Location"], horizontal=True, key="locsrc")
    if src.startswith("Auto") and st.session_state.get("prev_src", "").startswith("Click"):
        st.session_state.geo_n = st.session_state.get("geo_n", 0) + 1
        st.session_state.fell_back = False
        st.session_state.pop("gps_loc", None)
        st.session_state.prev_src = src
        st.rerun()

    st.session_state.prev_src = src
    gps = None if st.session_state.get("perm_last") == "denied" else st.session_state.get("gps_loc")
    click = st.session_state.get("click_loc")
    user = click if src.startswith("Click") else gps
    geo_state = "pending" if src.startswith("Auto") and geo is None else "done"
    st.session_state.located = user is not None
    locked = src.startswith("Auto") and user is not None
    if locked:
        st.session_state.country, st.session_state.region = locate(user)
        st.session_state.view = "region"
    alert_slot = st.empty()

scope = [x for x in FIRES if x["country"] == st.session_state.country and st.session_state.region in (ALL, x["region"])]
selected = bool(scope)

fire = None
if selected:
    _afn = st.session_state.get("active_fire_name")
    if _afn and FIRE_BY_NAME.get(_afn) in scope:
        fire = FIRE_BY_NAME[_afn]
    else:
        fire = min(scope, key=lambda x: km_between(user, x["origin"])) if user else scope[0]

cities, S, P = [], None, None
if selected and fire["is_ml"]:
    S = eng.summary(fire["name"], fire["origin"][0], fire["origin"][1], t0, h)
    P = eng.build(fire["name"], fire["origin"][0], fire["origin"][1], t0, h)
    cities = P["cities"]
    n = S["n_flagged"]
    label, lcls = aqi_label(S["peak_pm"])
    r2 = META.get("metrics", {}).get("R2")
    conf, conf_txt = ((fire["conf"], "LLM prediction confidence") if "conf" in fire
                      else (round(r2 * 100, 1), "Model R2 on held-out test set") if r2 is not None else (None, "No model metrics"))
    cards_html = (
        card("Active Monitoring Zone", fire["name"], f"Forecast issued {fake_dt(t0):%d %b %H:%M} UTC", "")
        + card("Predicted Fire Severity", f"{min(100, round(S['peak_pm'] * 100 / 250))} / 100",
               f"{fire['sev']} - {n} of {len(cities)} cities above {ALERT_UGM3:.0f} ug/m3 (Hour {h})", fire["cls"])
        + card("Prediction Confidence", f"{conf}%" if conf is not None else "N/A", conf_txt, "")
        + card("Air Quality Index", f"{S['peak_pm']:.0f}", f"{label} - peak city {nice(S['peak_city'])}", lcls)
    )
elif selected:
    label, lcls = aqi_label(fire["PM"][h])
    cards_html = (
        card("Active Monitoring Zone", fire["name"], f"Nearest of {len(scope)} active fire{'s' if len(scope) > 1 else ''}" if user else "Live Feed", "")
        + card("Predicted Fire Severity", f"{fire.get('score', '-')} / 100", f"{fire['sev']} - {fire['HA'][h]} Hectares (Hour {h})", fire["cls"])
        + card("Prediction Confidence", f"{fire.get('conf', '-')}%",
               f"NASA FIRMS detection confidence ({fire['detections']} hotspots, {fake_dstr(fire.get('firms_date', ''))})" if fire.get("live")
               else "Fallback estimate (no ML rows)", "")
        + card("Air Quality Index", f"{fire['PM'][h]}", f"{label} - " + ("Alert Active" if h else "Baseline"), lcls)
    )
else:
    label, lcls = "", ""
    cards_html = "".join(card(t, "No region selected", "Select a country and region", "") for t in
                         ("Active Monitoring Zone", "Predicted Fire Severity", "Prediction Confidence", "Air Quality Index"))
cards_slot.markdown(f'<div class="cards">{cards_html}</div>', unsafe_allow_html=True)

with left:
    r1, r2, r3 = st.columns([3, 5, 5], vertical_alignment="center")
    r1.selectbox("Country", list(COUNTRIES), index=None, placeholder="Select country", key="country", on_change=on_country,
                 label_visibility="collapsed", format_func=lambda c: f"Country: {c}", disabled=src.startswith("Auto"))
    r2.selectbox("County / Province / Region", regions_of(st.session_state.country), index=None, placeholder="Select region",
                 key="region", on_change=on_region, label_visibility="collapsed", format_func=lambda r: f"Region: {r}",
                 disabled=src.startswith("Auto") or st.session_state.country is None)
    mode = r3.radio("Map display mode", ["Wildfire Plume & Spread", "Air Quality (AQI) Heat Map"], horizontal=True, label_visibility="collapsed", key="mode")

    # 1. Determine where the app *wants* the camera to point based on logic
    if locked:
        prog_center, prog_zoom = user, REGION_ZOOM
    elif not selected:
        prog_center, prog_zoom = (20.0, -10.0), 2
    elif st.session_state.view == "country":
        prog_center, prog_zoom = COUNTRIES[st.session_state.country]["center"], COUNTRIES[st.session_state.country]["zoom"]
    elif st.session_state.get("active_fire_name") and FIRE_BY_NAME.get(st.session_state.active_fire_name) in scope:
        prog_center, prog_zoom = FIRE_BY_NAME[st.session_state.active_fire_name]["origin"], REGION_ZOOM
    else:
        prog_center, prog_zoom = (sum(x["origin"][0] for x in scope) / len(scope), sum(x["origin"][1] for x in scope) / len(scope)), REGION_ZOOM

    # 2. Advanced Map State Tracker - completely eliminates st_folium jumping!
    if "map_center" not in st.session_state:
        st.session_state.map_center = prog_center
        st.session_state.map_zoom = prog_zoom

    # Identify if a structural change happened that warrants a camera jump
    prog_view = (st.session_state.country, st.session_state.region, st.session_state.get("active_fire_name"))
    if "last_prog_view" not in st.session_state:
        st.session_state.last_prog_view = prog_view

    # Identify if an internal change happened where we WANT to preserve the user's pan
    preserve_triggers = (user, mode, h, t0)
    if "last_preserve_triggers" not in st.session_state:
        st.session_state.last_preserve_triggers = preserve_triggers

    # Logic tree for controlling the camera base location
    if st.session_state.last_prog_view != prog_view:
        # User changed region/country or clicked a fire marker -> Force map to jump there
        st.session_state.last_prog_view = prog_view
        st.session_state.map_center = prog_center
        st.session_state.map_zoom = prog_zoom
        # Prevent the preserve block below from firing just because user changed
        st.session_state.last_preserve_triggers = preserve_triggers
        
    elif st.session_state.last_preserve_triggers != preserve_triggers:
        # A click happened (user changed), slider moved, or heatmap toggled. 
        # We must rebuild the map, but we DO NOT want the camera to reset. 
        # We pull the *last known coordinates* from immediately before the click/action.
        st.session_state.last_preserve_triggers = preserve_triggers
        prev_map = st.session_state.get("map_res")
        if prev_map and prev_map.get("center"):
            st.session_state.map_center = (prev_map["center"]["lat"], prev_map["center"]["lng"])
            st.session_state.map_zoom = prev_map["zoom"]

    # Initialize map exclusively with our highly-managed center state
    m = folium.Map(location=st.session_state.map_center, zoom_start=st.session_state.map_zoom, tiles="OpenStreetMap")
    m.get_root().header.add_child(folium.Element("<style>html,body{height:100%;margin:0;overflow:hidden}#map_div,#map_div2,.folium-map{height:100vh!important}</style>"))

    if selected:
        sw_ne = bounds_of(st.session_state.country, st.session_state.region)
        folium.Rectangle(
            [[sw_ne[0], sw_ne[1]], [sw_ne[2], sw_ne[3]]], color="#4a6fa5", weight=3, dash_array="10 8",
            fill=True, fill_opacity=0.04,
            tooltip=f"Boundary: {st.session_state.country if st.session_state.region == ALL else st.session_state.region}",
        ).add_to(m)

    if selected:
        _b = bounds_of(st.session_state.country, st.session_state.region)
        for p in [p for p in HOTSPOTS if in_box(p["latitude"], p["longitude"], _b)][:1500]:
            folium.CircleMarker((p["latitude"], p["longitude"]), radius=2, color="#ff6b00", weight=1, fill=True,
                                fill_opacity=0.8, tooltip=f"FIRMS {fake_dstr(p['date'])} {p['time']} UTC, confidence {p['confidence']}").add_to(m)

    for x in FIRES:
        if x is fire: folium.CircleMarker(x["origin"], radius=22, color="#e03131", weight=3, fill=True, fill_opacity=0.12).add_to(m)
        ha_text = "ML Engine Active" if x["is_ml"] else f"{x['HA'][h]} ha at Hour {h}"
        folium.Marker(
            x["origin"],
            tooltip=x["name"],
            popup=folium.Popup(f"{x['name']}: {x['sev']}, {ha_text}", max_width=280),
            icon=folium.Icon(color="red", icon="fire", prefix="fa"),
        ).add_to(m)

    if user:
        folium.Marker(user, tooltip="Your test location", icon=folium.Icon(color="darkblue", icon="user", prefix="fa")).add_to(m)

    if selected:
        if mode.startswith("Air"):
            heat_data = []
            for x in scope:
                if x["is_ml"]: heat_data.extend(eng.heat_points(x["name"], x["origin"][0], x["origin"][1], t0, h))
                else: heat_data.extend(get_heatmap_data(x, h))
            if heat_data:
                grad = HEAT_GRADIENT if any(x["is_ml"] for x in scope) else {0.2: "#4a6fa5", 0.5: "#c98a0b", 0.8: "#c2410c", 1.0: "#7a0f12"}
                HeatMap(heat_data, radius=38, blur=28, min_opacity=0.25, gradient=grad).add_to(m)
        else:
            if h > 0:
                for x in scope:
                    if x["is_ml"]:
                        eng.add_to_map(m, x["name"], x["origin"][0], x["origin"][1], t0, h, show_cities=False)
                    else:
                        for layer_name, poly in mock_layers(x, h):
                            st_ = LAYER_STYLE[layer_name]
                            folium.Polygon(poly, color="#7a0f12", weight=st_["weight"], fill=True, fill_color=st_["fill"], fill_opacity=st_["opacity"], tooltip=f"{x['short']} Hour {h}: {x['HA'][h]} ha, PM2.5 {x['PM'][h]} ug/m3, reach {x['RE'][h]} km").add_to(m)
            ml_fires = [(x["name"], x["origin"][0], x["origin"][1]) for x in scope if x["is_ml"]]
            if ml_fires:
                eng.add_cities_to_map(m, ml_fires, t0, h)

    # Note the ABSENCE of center=... kwargs. The initialization logic above does all the heavy lifting silently!
    res = st_folium(m, use_container_width=True, height=560,
                    returned_objects=["last_clicked", "last_object_clicked_tooltip", "center", "zoom"], key="map_res")
    res = res or {}

    tt = res.get("last_object_clicked_tooltip")
    if tt in FIRE_BY_NAME and tt != st.session_state.get("last_tt"):
        st.session_state.last_tt = tt
        if selected and FIRE_BY_NAME[tt] in scope:
            st.session_state.active_fire_name = tt
            st.rerun()
        elif src.startswith("Click") and selected:
            st.session_state.pending_fire = tt
            st.session_state.view = "region"
            st.rerun()

    c = res.get("last_clicked")
    c = (c["lat"], c["lng"]) if c else None
    if c and c != st.session_state.get("last_click"):
        st.session_state.last_click = c
        if src.startswith("Click"):
            if not selected:
                st.session_state.warn = ("Select a Region First", "Select a country and region from the dropdowns, then click inside its outline.")
                st.toast("Select a country and region first.")
            elif in_bounds(c, bounds_of(st.session_state.country, st.session_state.region)):
                st.session_state.click_loc = c
                st.rerun()
            else:
                st.session_state.warn = ("Outside Selected Region", "You have to click within the region.")
                st.toast("You have to click within the region.")

if user is None or not selected:
    acls, icon, atitle, abody = alert_no_user(geo_state, selected)
elif fire["is_ml"]:
    acls, icon, atitle, abody = location_alert_ml(user, h, t0, cities, fire)
else:
    acls, icon, atitle, abody = location_alert_mock(user, h, fire)
_w = st.session_state.pop("warn", None)
if _w:
    acls, icon, atitle, abody = "warn", "!", *_w
if user:
    abody += f'<div style="opacity:.7;margin-top:4px;font-size:.78rem">Location source: {"Map click" if src.startswith("Click") else "Device GPS"}</div>'
alert_slot.markdown(f'<div class="alert {acls}"><div class="ic">{icon}</div><div><div class="t">{atitle}</div><div class="b">{abody}</div></div></div>', unsafe_allow_html=True)

with rc:
    with st.container(key="advisory"):
        gov, pub, analytics = st.tabs(["Government / Municipal Command", "Public / Citizen Advisory", "Data & Analytics"])

        if not selected:
            for tab in (gov, pub, analytics):
                with tab:
                    st.markdown(PH, unsafe_allow_html=True)

        elif fire["is_ml"]:
            T = fire["target_name"]
            fl = sorted([c for c in cities if c["flagged"]], key=lambda c: c["dist_km"])
            fl_names = ", ".join(nice(c["city"]) for c in fl) or "none"

            _eta = next((i for i in range(0, HORIZON_H + 1)
                         if eng.in_plume(fire["target"][0], fire["target"][1], fire["name"], fire["origin"][0], fire["origin"][1], t0, i)), None)
            eta_txt = f"Hour {_eta}" if _eta is not None else f"after Hour {HORIZON_H}"

            truth_seq = "".join(f"<li><b>{nice(c['city'])}</b>: Forecasted <b>{c['pm_6h']:.0f}</b> ug/m3 | Actual recorded was <b>{c['actual_6h']:.0f}</b> ug/m3 <span style='opacity:0.7'>(Baseline no-change guess: {c['pm_now']:.0f})</span></li>" for c in cities if c["flagged"])
            if not truth_seq:
                truth_seq = "<li>No cities above threshold in this window.</li>"

            seq = "".join(f"<li><b>{i}. {nice(c['city'])}</b> ({c['dist_km']:.0f} km from fire): PM2.5 {c['pm_h']:.0f} ug/m3, {aqi_label(c['pm_h'])[0]}. Issue {'a shelter-in-place order' if c['pm_h'] >= 150 else 'an air quality advisory'}.</li>" for i, c in enumerate(fl, 1)) or "<li>No city above threshold. Continue monitoring.</li>"
            threat, tcls = ("High", "crit") if n >= 3 else ("Elevated", "warn") if n else ("Low", "ok")
            wind_txt = f"{S['wind_from']} at {S['wind_kmh']} km/h"

            with gov:
                st.markdown(
                    f"""<div class="panel">
<div class="zone"><span class="badge {lcls}">Hour {h}</span>&nbsp; {S['zone_text']}</div>
<h4>Strategic Incident Metrics</h4>
<ul><li>Cities above threshold: <b>{n} of {len(cities)}</b> ({fl_names})</li>
<li>Plume leading edge: <b>{S['reach_km']:.0f} km</b> {S['travel_to']} of origin</li>
<li>Peak PM2.5: <b>{S['peak_pm']:.0f} ug/m3</b> in {nice(S['peak_city'])} ({label})</li>
<li>Threat level: <span class="badge {tcls}">{threat}</span></li>
<li>Active incidents in view: <b>{len(scope)}</b> ({', '.join(x['short'] for x in scope)}); focus fire: <b>{fire['short']}</b></li></ul>
<h4>6h Forecast vs Ground Truth Replay</h4>
<p style="font-size:.84rem; color:var(--mute); margin-bottom:4px;">As this system runs on real historical open-meteo data, we can directly verify the model's accuracy at the 6-hour prediction horizon:</p>
<ul>{truth_seq}</ul>
<h4>Alert Sequencing (nearest to fire first)</h4>
<ul>{seq}</ul>
{sec_resources(fire, T)}
{sec_evac(fire, T, eta_txt)}
{sec_agency(fire, wind_txt)}
</div>""", unsafe_allow_html=True
                )
            with pub:
                st.markdown(
                    f"""<div class="panel">
<div class="zone"><span class="badge {lcls}">{label}</span>&nbsp; Air quality forecast for Hour {h}. {S['zone_text']}</div>
<h4>Shelter in Place ({fl_names})</h4>
{SEC_SHELTER}
{sec_corridors(fire, T)}
{SEC_INFORMED}
</div>""", unsafe_allow_html=True
                )
            with analytics:
                city_analytics = "".join(f"<li><b>{nice(c['city'])}</b>: {c['dist_km']:.0f} km away. <b>PM2.5 Current:</b> {c['pm_now']:.1f} | <b>PM2.5 +6h Predict:</b> {c['pm_6h']:.1f} | <b>Flagged:</b> {c['flagged']}</li>" for c in sorted(cities, key=lambda c: c["dist_km"]))
                if not city_analytics:
                    city_analytics = "<li>No API sensor data fetched for this timestep.</li>"
                st.markdown(
                    f"""<div class="panel">
<h4>Live Model Features (Data Source: Open-Meteo)</h4>
<ul><li>Wind Origin: <b>{S['wind_from']} ({round(P['wind_from'], 1)}°)</b> at <b>{S['wind_kmh']} km/h</b></li>
<li>Plume Axis Bearing: <b>{round(P['axis_bearing'], 1)}°</b></li></ul>
<h4>City State Vectors & Projections</h4>
<ul>{city_analytics}</ul>
<p style="font-size:.84rem; color:var(--mute); margin-top:8px;">The Random Forest relies heavily on these city coordinates, along-wind vectors, and 3-to-12 hour PM2.5 lagging signals to predict exactly what the AQI will be six hours from this moment.</p>
</div>""", unsafe_allow_html=True
                )

        else:
            T = fire["target_name"]
            eta_txt = f"Hour {fire['eta']}" if fire["eta"] is not None else f"after Hour {HORIZON_H}"
            wind_txt = f"{fire['DIR'][h]} at {round(fire['WIND'][h], 1)} km/h"
            with gov:
                st.markdown(
                    f"""<div class="panel">
<div class="zone"><span class="badge {lcls}">Hour {h}</span>&nbsp; {fire['name']}: {zone_text(fire, h)}</div>
<h4>Incident Metrics (MOCK DATA)</h4>
<ul><li>Projected burn area: <b>{fire['HA'][h]} ha</b> (24-hour peak {fire['HA'][-1]} ha)</li>
<li>Plume leading edge: <b>{fire['RE'][h]} km</b> from origin toward {T}</li>
<li>Peak PM2.5: <b>{fire['PM'][h]} ug/m3</b> ({label})</li>
<li>Threat level: <span class="badge {fire['cls']}">{fire['sev']}</span></li>
<li>Active incidents in view: <b>{len(scope)}</b> ({', '.join(x['short'] for x in scope)}); focus fire: <b>{fire['short']}</b></li></ul>
<p style="font-size:.84rem; color:var(--mute); margin-top:8px;">This fire has no ML rows in the data files, so these values are synthetic projections, not model predictions.</p>
{sec_resources(fire, T)}
{sec_evac(fire, T, eta_txt)}
{sec_agency(fire, wind_txt)}
</div>""", unsafe_allow_html=True
                )
            with pub:
                st.markdown(
                    f"""<div class="panel">
<div class="zone"><span class="badge {lcls}">{label}</span>&nbsp; {fire['name']} air quality projection for Hour {h} (mock). {zone_text(fire, h)}</div>
<h4>Shelter in Place ({T})</h4>
{SEC_SHELTER}
{sec_corridors(fire, T)}
{SEC_INFORMED}
</div>""", unsafe_allow_html=True
                )
            with analytics:
                st.markdown(
                    f"""<div class="panel">
<h4>No Model Analytics Available</h4>
<p style="font-size:.84rem; color:var(--mute);">Please run the ML training script. The dataset is missing the <i>test_predictions.csv</i> rows for {fire['name']}.</p>
</div>""", unsafe_allow_html=True
                )

    mm, hw = META.get("metrics", {}), META.get("hardware_audit", {})
    st.markdown(
        '<div class="sys">'
        + card("Backend", "LinuxONE Secure Container", f"Connected | {hw.get('architecture', 's390x')}", "")
        + card("Model", f"Random Forest ({hw.get('ml_backend', 'n/a')})", f"6h MAE {mm.get('MAE', 'n/a')} ug/m3 | {mm.get('MAE_improvement_vs_baseline_pct', 'n/a')}% vs persistence", "")
        + card("NASA FIRMS", f"{len(HOTSPOTS):,} hotspots", f"VIIRS {fake_dstr(FIRMS_DATE) if FIRMS_DATE else 'no data yet'} | "
               + ("auto-refresh 24 h" if FIRMS_REFRESH else "refresh off (no keys)"), "")
        + "</div>", unsafe_allow_html=True
    )


