import json
import os
from math import asin, cos, radians, sin, sqrt

import folium
import streamlit as st
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation, streamlit_js_eval

from plume import ALERT_UGM3, HEAT_GRADIENT, IGNITION, PlumeEngine, LAYERS, LAYER_STYLE

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
.sys { display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-top:6px; }
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

# ---------- ML engine initialisation ----------
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

if "hour" not in st.session_state: st.session_state.hour = 0
if "t0" not in st.session_state: st.session_state.t0 = eng.default_t0()

def reset_hour():
    st.session_state.hour = 0

# ---------- Active fires setup ----------
HA_S = [0, .13, .31, .53, .73, .89, 1]
PM_S = [.025, .2, .375, .54, .71, .85, 1]
RE_S = [0, .2, .38, .57, .75, .88, 1]
WIND_S = [0, 0, 2, 3, 1, 0, -1]

QUEBEC_FIRE = dict(
    name="Quebec Fire Complex", short="Quebec", origin=IGNITION, target=(45.5017, -73.5673),
    target_name="Montreal", ha=0, pm=0, reach=0, wind=0, wdir="N", walt="N",
    country="Canada", region="Quebec", sev="Critical Risk", cls="crit", color="darkred",
    staging="Val-d'Or staging area", helibase="Quebec helibase", route="Route 117 southbound",
    hospital="Montreal General Hospital", avoid="Route 113", nearby="Senneterre", is_ml=True
)

FIRES = [
    QUEBEC_FIRE,
    dict(name="Sector 4 - North Hills", short="Sector 4", origin=(37.8044, -122.4500), target=(37.7450, -122.3850),
         target_name="Oakridge District", ha=45, pm=480, reach=10.2, wind=28, wdir="NW", walt="NNW",
         country="United States", region="California / San Francisco County",
         sev="High Risk", cls="crit", color="red", staging="North Ridge access road staging area",
         helibase="Sector 4 helibase", route="Route 9 southbound", hospital="Oakridge Community Hospital",
         avoid="Ridge Road", nearby="Marlow Heights"),
    dict(name="East Bay Ridge Corridor", short="East Bay Ridge", origin=(37.8350, -122.2100), target=(37.8030, -122.2700),
         target_name="Lakeshore Flats", ha=78, pm=560, reach=9.5, wind=34, wdir="E", walt="ENE",
         country="United States", region="California / Alameda County",
         sev="Extreme Risk", cls="crit", color="darkred", staging="Grizzly Peak staging area",
         helibase="Ridge Corridor helibase", route="Route 24 westbound", hospital="Lakeshore Medical Center",
         avoid="Skyline Spur Road", nearby="Hillcrest Terrace"),
    dict(name="Skyline Boulevard", short="Skyline Blvd", origin=(37.6800, -122.4900), target=(37.7200, -122.4300),
         target_name="Bayview Heights", ha=22, pm=310, reach=8.0, wind=21, wdir="SW", walt="WSW",
         country="United States", region="California / San Mateo County",
         sev="Moderate Risk", cls="warn", color="orange", staging="Skyline summit staging area",
         helibase="Skyline helibase", route="Route 1 northbound", hospital="Bayview Heights Clinic",
         avoid="Skyline Boulevard", nearby="Crestmoor"),
    dict(name="North Shore Mountains", short="North Shore", origin=(49.3900, -123.0900), target=(49.3300, -123.0000),
         target_name="Burnaby Heights", ha=38, pm=420, reach=10.5, wind=24, wdir="NW", walt="NNW",
         country="Canada", region="British Columbia / Metro Vancouver Region",
         sev="High Risk", cls="crit", color="purple", staging="Seymour staging area",
         helibase="North Shore helibase", route="Highway 1 eastbound", hospital="Burnaby General Hospital",
         avoid="Mount Seymour Parkway", nearby="Capitol Hill"),
    dict(name="Blue Mountains Escarpment", short="Blue Mountains", origin=(-33.7100, 150.3000), target=(-33.7600, 150.3900),
         target_name="Glenbrook Township", ha=120, pm=540, reach=11.0, wind=38, wdir="W", walt="WNW",
         country="Australia", region="New South Wales / Blue Mountains Region",
         sev="Extreme Risk", cls="crit", color="cadetblue", staging="Great Western Highway staging area",
         helibase="Blue Mountains helibase", route="Great Western Highway eastbound", hospital="Nepean Rural Hospital",
         avoid="Bells Line of Road", nearby="Blaxland"),
    dict(name="Twin Peaks Brush Fire", short="Twin Peaks", origin=(37.7544, -122.4477), target=(37.7300, -122.4000),
         target_name="Excelsior District", ha=14, pm=260, reach=6.5, wind=22, wdir="NW", walt="NNW",
         country="United States", region="California / San Francisco County",
         sev="Moderate Risk", cls="warn", color="lightred", staging="Twin Peaks reservoir staging area",
         helibase="Twin Peaks helipad", route="Route 101 southbound", hospital="Excelsior Medical Center",
         avoid="Portola Drive", nearby="Glen Park"),
    dict(name="Tilden Park Interface", short="Tilden Park", origin=(37.8950, -122.2450), target=(37.8700, -122.2800),
         target_name="Berkeley Flats", ha=31, pm=380, reach=7.0, wind=29, wdir="E", walt="ENE",
         country="United States", region="California / Alameda County",
         sev="High Risk", cls="crit", color="green", staging="Inspiration Point staging area",
         helibase="Tilden helibase", route="Route 80 westbound", hospital="Berkeley General Hospital",
         avoid="Grizzly Peak Boulevard", nearby="Kensington Heights"),
]

COUNTRIES = {
    "Canada": dict(center=(56.0, -96.0), zoom=3),
    "United States": dict(center=(39.5, -98.5), zoom=4),
    "Australia": dict(center=(-25.5, 134.0), zoom=4),
}
REGION_ZOOM = 11
FIRE_BY_NAME = {f["name"]: f for f in FIRES}

for f in FIRES:
    if f.get("is_ml"):
        f["HA"] = f["PM"] = f["RE"] = f["WIND"] = [0]*7
        f["DIR"] = ["N"]*7
        f["dist"] = km_between(f["origin"], f["target"])
        f["eta"] = None
        continue
    f["HA"] = [round(f["ha"] * x) for x in HA_S]
    f["PM"] = [round(f["pm"] * x) for x in PM_S]
    f["RE"] = [round(f["reach"] * x, 1) for x in RE_S]
    f["WIND"] = [f["wind"] + x for x in WIND_S]
    f["DIR"] = [f["walt"] if h_ == 4 else f["wdir"] for h_ in range(7)]
    f["dist"] = km_between(f["origin"], f["target"])
    f["eta"] = next((i for i, r in enumerate(f["RE"]) if r >= f["dist"]), None)

# ---------- Mock math logic ----------
def zone_text(f, h):
    if h == 0: return "Ignition origin only. No smoke plume projected."
    if f["RE"][h] < f["dist"]: return f"Plume {f['dist'] - f['RE'][h]:.1f} km from the {f['target_name']} boundary."
    return f"Leading edge has reached the {f['target_name']}; plume continuing downwind."

def _path(f, h):
    (la0, lo0), (la1, lo1) = f["origin"], f["target"]
    dx, dy = la1 - la0, lo1 - lo0
    n = (dx * dx + dy * dy) ** 0.5
    ux, uy = dx / n, dy / n
    return ux, uy, uy, -ux, n * f["RE"][h] / f["dist"], 0.004 + 0.0022 * f["RE"][h]

# NEW: We draw the mock plumes using the exact same multi-layer gradient aesthetic as the ML engine!
def mock_layers(f, h):
    ux, uy, px, py, length, half = _path(f, h)
    o = f["origin"]
    polys = []
    for name, ws_, lf in LAYERS:
        L = length * lf
        W = half * ws_
        side = lambda s: [
            (o[0] + ux * L * t + s * px * W * (0.3 + 0.7 * t), o[1] + uy * L * t + s * py * W * (0.3 + 0.7 * t))
            for t in (i / 6 for i in range(7))
        ]
        polys.append((name, side(1) + side(-1)[::-1]))
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

def location_alert_ml(user, h, geo_state, t0, cities):
    if user is None:
        if geo_state == "pending": return "", "?", "Requesting Location", "Allow location access in the browser prompt. You can also click the map to test a point."
        note = "Device GPS is blocked or unavailable. " if st.session_state.get("fell_back") else ""
        return "", "?", "Awaiting Location", note + "Click anywhere on the map to test a location."
    dist = km_between(user, IGNITION)
    near = min(cities, key=lambda c: km_between(user, (c["lat"], c["lon"])))
    near_txt = f"Nearest monitored city: {nice(near['city'])}, PM2.5 {near['pm_h']:.0f} ug/m3 ({aqi_label(near['pm_h'])[0]})."
    if eng.in_plume(*user, t0, h):
        return "crit", "!", "Danger: Inside Smoke Plume", (f"Your location is under the plume at Hour {h}. {near_txt} Shelter in place or follow official guidance. Fire is {dist:.0f} km away.")
    eta = eng.eta_hour(*user, t0, h)
    if eta:
        return "crit", "!", f"Danger: Plume Arrives Hour {eta}", (f"Smoke is forecast over your location in {eta - h} h. {near_txt} Prepare now. Fire is {dist:.0f} km away.")
    return "ok", "OK", "Safe: Outside Plume Zone", (f"Fire is {dist:.0f} km away. {near_txt} Your location stays clear of the model's plume through Hour 6. Keep monitoring.")

def location_alert_mock(user, h, geo_state, f):
    if user is None:
        if geo_state == "pending": return "", "?", "Requesting Location", "Allow location access in the browser prompt. You can also click the map to test a point."
        note = "Device GPS is blocked or unavailable. " if st.session_state.get("fell_back") else ""
        return "", "?", "Awaiting Location", note + "Click anywhere on the map to test a location."
    dist = km_between(user, f["origin"])
    
    # Quick fix: compute outer plume bounds using the layer system
    mock_pols = mock_layers(f, h)
    outer_poly = mock_pols[0][1] if mock_pols else []
    
    if h and in_poly(user, outer_poly):
        return "crit", "!", "Danger: Inside Smoke Plume", (f"Your location is under the {f['short']} plume at Hour {h} (PM2.5 {f['PM'][h]} ug/m3, {aqi_label(f['PM'][h])[0]}). Shelter in place or evacuate if ordered. Fire is {dist:.1f} km away.")
    eta = next((i for i in range(h + 1, 7) if in_poly(user, mock_layers(f, i)[0][1])), None)
    if eta:
        return "crit", "!", f"Danger: Plume Arrives Hour {eta}", (f"Smoke from {f['name']} is forecast over your location in {eta - h} h. Prepare to evacuate now. Fire is {dist:.1f} km away.")
    return "ok", "OK", "Safe: Outside Plume Zone", (f"The nearest fire, {f['name']}, is {dist:.1f} km away. Your location stays clear of its plume through Hour 6. Keep monitoring.")

# ---------- Dropdown controls state setup ----------
ALL = "All regions"

def regions_of(country):
    return [ALL] + list(dict.fromkeys(x["region"] for x in FIRES if x["country"] == country))

st.session_state.setdefault("country", FIRES[0]["country"])
st.session_state.setdefault("region", FIRES[0]["region"])
st.session_state.setdefault("view", "region")

# NEW: We strictly manage map bounds here so it doesn't jump randomly
st.session_state.setdefault("map_center", COUNTRIES[FIRES[0]["country"]]["center"])
st.session_state.setdefault("map_zoom", COUNTRIES[FIRES[0]["country"]]["zoom"])

def update_map_view(c, z):
    st.session_state.map_center = c
    st.session_state.map_zoom = z

if "pending_fire" in st.session_state:
    pf = st.session_state.pop("pending_fire")
    st.session_state.active_fire_name = pf
    _f = FIRE_BY_NAME[pf]
    st.session_state.country, st.session_state.region = _f["country"], _f["region"]
    update_map_view(_f["origin"], REGION_ZOOM)

st.session_state.setdefault("prev_sel", (st.session_state.country, st.session_state.region))
if st.session_state.region not in regions_of(st.session_state.country):
    st.session_state.region = ALL

GATE_MSG = "Please allow location access or click any point on the map first to select regions."

def _gated():
    if st.session_state.get("located"): return False
    st.session_state.country, st.session_state.region = st.session_state.prev_sel
    st.session_state.gate_warn = True
    st.toast(GATE_MSG)
    return True

def on_country():
    if _gated(): return
    st.session_state.region = ALL
    st.session_state.view = "country"
    st.session_state.fire_touched = True
    st.session_state.pop("active_fire_name", None)
    update_map_view(COUNTRIES[st.session_state.country]["center"], COUNTRIES[st.session_state.country]["zoom"])

def on_region():
    if _gated(): return
    st.session_state.view = "country" if st.session_state.region == ALL else "region"
    st.session_state.fire_touched = True
    st.session_state.pop("active_fire_name", None)
    
    sc = [x for x in FIRES if x["country"] == st.session_state.country and st.session_state.region in (ALL, x["region"])]
    if sc:
        c = (sum(x["origin"][0] for x in sc) / len(sc), sum(x["origin"][1] for x in sc) / len(sc))
        z = COUNTRIES[st.session_state.country]["zoom"] if st.session_state.region == ALL else REGION_ZOOM
        update_map_view(c, z)

# ---------- Header & Core App Logic ----------
t1, t3, t2 = st.columns([5, 3, 1.4], vertical_alignment="bottom")
t1.slider("Forecast timeline (hours from forecast issue)", 0, 6, key="hour", format="Hour %d")
h = st.session_state.hour
t0 = st.session_state.t0

scope = [x for x in FIRES if x["country"] == st.session_state.country and st.session_state.region in (ALL, x["region"])]

if any(x.get("is_ml") for x in scope):
    t3.selectbox("Forecast issued at", eng.times, key="t0", format_func=lambda t: t.strftime("%d %b %Y %H:%M UTC"))
else:
    with t3: st.write("")
t2.button("Reset to Hour 0", on_click=reset_hour)

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
        lat, lon = geo["coords"]["latitude"], geo["coords"]["longitude"]
        old_gps = st.session_state.get("gps_loc")
        # NEW: Debounce GPS coordinates by 50 meters so map doesn't drift/bounce
        if old_gps is None or km_between(old_gps, (lat, lon)) > 0.05:
            st.session_state.gps_loc = (lat, lon)
            if not st.session_state.get("fire_touched"):
                update_map_view((lat, lon), REGION_ZOOM)
                
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
    alert_slot = st.empty()

if st.session_state.get("active_fire_name") and FIRE_BY_NAME.get(st.session_state.active_fire_name) in scope:
    fire = FIRE_BY_NAME[st.session_state.active_fire_name]
else:
    fire = min(scope, key=lambda x: km_between(user, x["origin"])) if user else scope[0]
    
cities = []

if fire.get("is_ml"):
    S = eng.summary(t0, h)
    P = eng.build(t0, h)
    cities = P["cities"]
    n = S["n_flagged"]
    label, lcls = aqi_label(S["peak_pm"])
    cards_slot.markdown(
        '<div class="cards">'
        + card("Active Monitoring Zone", fire["name"], f"Forecast issued {t0:%d %b %H:%M} UTC", "")
        + card("Cities Above Alert Threshold", f"{n} of {len(cities)}", f"PM2.5 >= {ALERT_UGM3:.0f} ug/m3 (Hour {h})", "crit" if n >= 3 else "warn" if n else "")
        + card("Wind Vector at Fire", f"{S['wind_kmh']} km/h ({S['wind_from']})", f"Smoke moving toward {S['travel_to']}", "warn")
        + card("Downwind Air Quality", f"{label} (PM2.5: {S['peak_pm']:.0f})", f"Peak city: {nice(S['peak_city'])}", lcls)
        + "</div>",
        unsafe_allow_html=True,
    )
else:
    label, lcls = aqi_label(fire["PM"][h])
    wind_delta = "Shifting" if 2 <= h <= 4 else "Stable"
    cards_slot.markdown(
        '<div class="cards">'
        + card("Active Monitoring Zone", fire["name"], f"Nearest of {len(scope)} active fire{'s' if len(scope) > 1 else ''}" if user else "Live Feed", "")
        + card("Predicted Fire Severity", fire["sev"], f"{fire['HA'][h]} Hectares (Hour {h})", fire["cls"])
        + card("Wind Vector", f"{fire['WIND'][h]} km/h ({fire['DIR'][h]})", wind_delta, "warn")
        + card("Downwind Air Quality", f"{label} (PM2.5: {fire['PM'][h]})", "Alert Active" if h else "Baseline", lcls)
        + "</div>",
        unsafe_allow_html=True,
    )

if fire.get("is_ml") and getattr(eng, "demo", False):
    st.markdown('<div class="zone"><span class="badge warn">Demo data</span>&nbsp; Model files not found, so this runs on a built-in '
                'synthetic smoke event. Put test_predictions.csv and fire_wind.csv in ./data to use the real model output.</div>',
                unsafe_allow_html=True)

with left:
    r1, r2, r3 = st.columns([3, 5, 5], vertical_alignment="center")
    r1.selectbox("Country", list(COUNTRIES), key="country", on_change=on_country, label_visibility="collapsed", format_func=lambda c: f"Country: {c}")
    r2.selectbox("County / Province / Region", regions_of(st.session_state.country), key="region", on_change=on_region, label_visibility="collapsed", format_func=lambda r: f"Region: {r}")
    st.session_state.prev_sel = (st.session_state.country, st.session_state.region)
    mode = r3.radio("Map display mode", ["Wildfire Plume & Spread", "Air Quality (AQI) Heat Map"], horizontal=True, label_visibility="collapsed", key="mode")
    
    # NEW: Rely strictly on explicit session_state variables to prevent jumpy map
    m = folium.Map(location=st.session_state.map_center, zoom_start=st.session_state.map_zoom, tiles="OpenStreetMap")
    m.get_root().header.add_child(folium.Element("<style>html,body{height:100%;margin:0;overflow:hidden}#map_div,#map_div2,.folium-map{height:100vh!important}</style>"))
    
    # NEW: We only draw markers inside the `scope` to accurately reflect the active dropdown filter
    for x in scope:
        sel = x is fire
        if sel: folium.CircleMarker(x["origin"], radius=22, color="#e03131", weight=3, fill=True, fill_opacity=0.12).add_to(m)
        ha_text = f"{x['HA'][h]} ha at Hour {h}" if not x.get("is_ml") else "ML Engine Active"
        folium.Marker(
            x["origin"],
            tooltip=x["name"],
            popup=folium.Popup(f"{x['name']}: {x['sev']}, {ha_text}", max_width=280),
            icon=folium.Icon(color=x["color"], icon="fire", prefix="fa"),
        ).add_to(m)
        
    if user:
        folium.Marker(user, tooltip="Your test location", icon=folium.Icon(color="darkblue", icon="user", prefix="fa")).add_to(m)
        
    if mode.startswith("Air"):
        heat_data = []
        for x in scope:
            if x.get("is_ml"): heat_data.extend(eng.heat_points(t0, h))
            else: heat_data.extend(get_heatmap_data(x, h))
        if heat_data:
            grad = HEAT_GRADIENT if any(x.get("is_ml") for x in scope) else {0.2: "#4a6fa5", 0.5: "#c98a0b", 0.8: "#c2410c", 1.0: "#7a0f12"}
            HeatMap(heat_data, radius=38, blur=28, min_opacity=0.25, max_val=1.0, gradient=grad).add_to(m)
    elif h > 0:
        for x in scope:
            if x.get("is_ml"):
                eng.add_to_map(m, t0, h)
            else:
                # NEW: Feed the exact identical visual renderer to all mock fires!
                for layer_name, poly in mock_layers(x, h):
                    st_ = LAYER_STYLE[layer_name]
                    folium.Polygon(poly, color="#7a0f12", weight=st_["weight"], fill=True, fill_color=st_["fill"], fill_opacity=st_["opacity"], tooltip=f"{x['short']} Hour {h}: {x['HA'][h]} ha, PM2.5 {x['PM'][h]} ug/m3, reach {x['RE'][h]} km").add_to(m)
                
    res = st_folium(m, use_container_width=True, height=560, returned_objects=["last_clicked", "last_object_clicked_tooltip"], key="map")
    res = res or {}
    tt = res.get("last_object_clicked_tooltip")
    
    if tt in FIRE_BY_NAME and tt != st.session_state.get("last_tt"):
        st.session_state.last_tt = tt
        st.session_state.pending_fire = tt
        st.session_state.view = "region"
        st.session_state.fire_touched = True
        st.rerun()
        
    c = res.get("last_clicked")
    if c and src.startswith("Click") and (c["lat"], c["lng"]) != st.session_state.get("click_loc"):
        st.session_state.click_loc = (c["lat"], c["lng"])
        st.rerun()

acls, icon, atitle, abody = location_alert_ml(user, h, geo_state, t0, cities) if fire.get("is_ml") else location_alert_mock(user, h, geo_state, fire)
if user is None and st.session_state.get("gate_warn"):
    acls, icon, atitle, abody = "warn", "!", "Location Required", GATE_MSG
elif user is not None:
    st.session_state.gate_warn = False
if user:
    abody += f'<div style="opacity:.7;margin-top:4px;font-size:.78rem">Location source: {"Map click" if src.startswith("Click") else "Device GPS"}</div>'
alert_slot.markdown(f'<div class="alert {acls}"><div class="ic">{icon}</div><div><div class="t">{atitle}</div><div class="b">{abody}</div></div></div>', unsafe_allow_html=True)

with rc:
    with st.container(key="advisory"):
        gov, pub = st.tabs(["Government / Municipal Command", "Public / Citizen Advisory"])
        if fire.get("is_ml"):
            fl = sorted([c for c in cities if c["flagged"]], key=lambda c: c["dist_km"])
            fl_names = ", ".join(nice(c["city"]) for c in fl) or "none"
            seq = "".join(f"<li><b>{i}. {nice(c['city'])}</b> ({c['dist_km']:.0f} km from fire): PM2.5 {c['pm_h']:.0f} ug/m3, {aqi_label(c['pm_h'])[0]}. Issue {'a shelter-in-place order' if c['pm_h'] >= 150 else 'an air quality advisory'}.</li>" for i, c in enumerate(fl, 1)) or "<li>No city above threshold. Continue monitoring.</li>"
            threat, tcls = ("High", "crit") if n >= 3 else ("Elevated", "warn") if n else ("Low", "ok")

            with gov:
                st.markdown(
                    f"""<div class="panel">
<div class="zone"><span class="badge {lcls}">Hour {h}</span>&nbsp; {S['zone_text']}</div>
<h4>Strategic Incident Metrics</h4>
<ul><li>Cities above threshold: <b>{n} of {len(cities)}</b> ({fl_names})</li>
<li>Plume leading edge: <b>{S['reach_km']:.0f} km</b> {S['travel_to']} of origin</li>
<li>Peak PM2.5: <b>{S['peak_pm']:.0f} ug/m3</b> in {nice(S['peak_city'])} ({label})</li>
<li>Threat level: <span class="badge {tcls}">{threat}</span></li></ul>
<h4>Resource Pre-Positioning Orders</h4>
<ul><li>Mobile air-quality monitors to: {fl_names}</li>
<li>Health system surge readiness (respiratory cases) in: {fl_names}</li>
<li>Respirator and HEPA filter stockpiles released to county health</li></ul>
<h4>Alert Sequencing (nearest to fire first)</h4>
<ul>{seq}</ul>
<h4>Inter-Agency Coordination</h4>
<ul><li>Fire and environment agencies: unified smoke-incident command</li>
<li>Public health: shelter and respirator distribution</li>
<li>Meteorological service: hourly wind-shift updates to the dispersion model</li></ul>
</div>""", unsafe_allow_html=True
                )
            with pub:
                st.markdown(
                    f"""<div class="panel">
<div class="zone"><span class="badge {lcls}">{label}</span>&nbsp; Air quality forecast for Hour {h}. {S['zone_text']}</div>
<h4>Shelter in Place ({fl_names})</h4>
<ul><li>Stay indoors. Close all windows, doors and fireplace dampers.</li>
<li>Turn off fans that draw in outside air; set HVAC to recirculate.</li></ul>
<h4>Air Filtration</h4>
<ul><li>Run HEPA purifiers in one sealed room.</li>
<li>If you must go outside, wear a fitted N95 or P100 respirator. Cloth and surgical masks do not protect against smoke.</li>
<li>Children, older adults and people with asthma or heart conditions should avoid all exertion.</li></ul>
<h4>Stay Informed</h4>
<ul><li>Follow official alerts on the emergency channel and emergency radio.</li>
<li>Emergency information line: 211</li></ul>
</div>""", unsafe_allow_html=True
                )
        else:
            f_, T = fire, fire["target_name"]
            eta_txt = f"Hour {f_['eta']}" if f_["eta"] is not None else "after Hour 6"
            with gov:
                st.markdown(
                    f"""<div class="panel">
<div class="zone"><span class="badge {lcls}">Hour {h}</span>&nbsp; {f_['name']}: {zone_text(f_, h)}</div>
<h4>Strategic Incident Metrics</h4>
<ul><li>Projected burn area: <b>{f_['HA'][h]} ha</b> (6-hour peak {f_['ha']} ha)</li>
<li>Plume leading edge: <b>{f_['RE'][h]} km</b> from origin toward {T}</li>
<li>Peak PM2.5: <b>{f_['PM'][h]} ug/m3</b> ({label})</li>
<li>Threat level: <span class="badge {f_['cls']}">{f_['sev']}</span></li>
<li>Active incidents in view: <b>{len(scope)}</b> ({', '.join(x['short'] for x in scope)}); nearest to your location: <b>{f_['short']}</b></li></ul>
<h4>Resource Pre-Positioning Orders</h4>
<ul><li>Engine Strike Teams 1-3 to the {f_['staging']}</li>
<li>Air tanker and helitanker standby at {f_['helibase']}</li>
<li>Mobile air-quality monitors to {T} and {f_['nearby']}</li>
<li>EMS surge units to {f_['hospital']}</li></ul>
<h4>Mandatory Evacuation Sequencing</h4>
<ul><li><b>Phase 1</b> (Hour 0-2): {f_['short']} residences and trailheads</li>
<li><b>Phase 2</b> (Hour 2-4): {f_['nearby']}, special-needs and care facilities first</li>
<li><b>Phase 3</b> (smoke arrival: {eta_txt}): {T}, via {f_['route']}</li></ul>
<h4>Inter-Agency Coordination</h4>
<ul><li>State fire agency: unified command established at the {f_['short']} post</li>
<li>Highway patrol: contraflow on {f_['route']} on Phase 3 order</li>
<li>County health: shelter and respirator distribution</li>
<li>Meteorological service: hourly wind-shift updates ({f_['DIR'][h]} at {f_['WIND'][h]} km/h) to the dispersion model</li></ul>
</div>""", unsafe_allow_html=True
                )
            with pub:
                st.markdown(
                    f"""<div class="panel">
<div class="zone"><span class="badge {lcls}">{label}</span>&nbsp; {f_['name']} air quality forecast for Hour {h}. {zone_text(f_, h)}</div>
<h4>Shelter in Place ({T})</h4>
<ul><li>Stay indoors. Close all windows, doors and fireplace dampers.</li>
<li>Turn off fans that draw in outside air; set HVAC to recirculate.</li></ul>
<h4>Air Filtration</h4>
<ul><li>Run HEPA purifiers in one sealed room.</li>
<li>If you must go outside, wear a fitted N95 or P100 respirator. Cloth and surgical masks do not protect against smoke.</li>
<li>Children, older adults and people with asthma or heart conditions should avoid all exertion.</li></ul>
<h4>Evacuation Corridors</h4>
<ul><li><b>{T}:</b> leave via {f_['route']} only when ordered. Do not travel toward the fire ({f_['short']}).</li>
<li>Avoid {f_['avoid']}; it is reserved for emergency vehicles.</li>
<li>Take medications, documents, pets and a 3-day supply of water.</li></ul>
<h4>Stay Informed</h4>
<ul><li>Follow official alerts on the county emergency channel and emergency radio.</li>
<li>Emergency information line: 211</li></ul>
</div>""", unsafe_allow_html=True
                )

    if fire.get("is_ml"):
        meta = load_meta(eng.data_dir) if eng.data_dir else {}
        mm, hw = meta.get("metrics", {}), meta.get("hardware_audit", {})
        st.markdown(
            '<div class="sys">'
            + card("Backend", "LinuxONE Secure Container", f"Connected | {hw.get('architecture', 's390x')}", "")
            + card("Model", f"Random Forest ({hw.get('ml_backend', 'n/a')})", ("Demo data (synthetic)" if getattr(eng, "demo", False) else f"6h MAE {mm.get('MAE', 'n/a')} ug/m3 | {mm.get('MAE_improvement_vs_baseline_pct', 'n/a')}% vs persistence"), "")
            + "</div>", unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div class="sys">'
            + card("Backend", "LinuxONE Secure Container", "Connected", "")
            + card("Model", "Random Forest + Dispersion Grid", "Inference 42 ms (-8 ms)", "")
            + "</div>", unsafe_allow_html=True
        )
