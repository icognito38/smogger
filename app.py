import json
import os
from math import asin, cos, radians, sin, sqrt

import folium
import streamlit as st
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation, streamlit_js_eval

from plume import ALERT_UGM3, HEAT_GRADIENT, IGNITION, PlumeEngine  # plume.py must sit next to this file

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
div[data-testid="stWidgetLabel"] p, div[data-testid="stSlider"] label p, div[data-testid="stRadio"] label p { color:var(--text) !important; }
div[data-testid="stSlider"] label p, .stButton button { font-size:.78rem; text-transform:uppercase; letter-spacing:.05em; }
.stButton button { border-radius:0; background:var(--panel); border:1px solid var(--line); color:var(--text); width:100%; }
.stButton button:hover { border-color:var(--crimson); color:#fff; }
</style>
""",
    unsafe_allow_html=True,
)

# ---------- model outputs (written by the training script) ----------
DATA_DIR = os.environ.get("SMOKE_DATA_DIR")  # optional; the engine also auto-searches ./data, . and /home/ibm-user/shared


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

if "hour" not in st.session_state:
    st.session_state.hour = 0
if "t0" not in st.session_state:
    st.session_state.t0 = eng.default_t0()


def reset_hour():
    st.session_state.hour = 0


def aqi_label(pm):
    if pm >= 250:
        return "Hazardous", "crit"
    if pm >= 150:
        return "Very Unhealthy", "crit"
    if pm >= 55:
        return "Unhealthy", "warn"
    if pm >= ALERT_UGM3:
        return "Unhealthy (Sensitive)", "warn"
    if pm >= 12:
        return "Moderate", "ok"
    return "Good", "ok"


def km_between(a, b):
    la1, lo1, la2, lo2 = map(radians, (*a, *b))
    x = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * asin(sqrt(x))


def nice(city):
    return city.replace("_", " ")


def location_alert(user, h, geo_state, t0, cities):
    """(css class, icon text, title, body) for the active location at forecast hour h, driven by the model."""
    if user is None:
        if geo_state == "pending":
            return "", "?", "Requesting Location", "Allow location access in the browser prompt. You can also click the map to test a point."
        note = "Device GPS is blocked or unavailable. " if st.session_state.get("fell_back") else ""
        return "", "?", "Awaiting Location", note + "Click anywhere on the map to test a location."
    dist = km_between(user, IGNITION)
    near = min(cities, key=lambda c: km_between(user, (c["lat"], c["lon"])))
    near_txt = f"Nearest monitored city: {nice(near['city'])}, PM2.5 {near['pm_h']:.0f} ug/m3 ({aqi_label(near['pm_h'])[0]})."
    if eng.in_plume(*user, t0, h):
        return "crit", "!", "Danger: Inside Smoke Plume", (
            f"Your location is under the plume at Hour {h}. {near_txt} "
            f"Shelter in place or follow official guidance. Fire is {dist:.0f} km away.")
    eta = eng.eta_hour(*user, t0, h)
    if eta:
        return "crit", "!", f"Danger: Plume Arrives Hour {eta}", (
            f"Smoke is forecast over your location in {eta - h} h. {near_txt} Prepare now. Fire is {dist:.0f} km away.")
    return "ok", "OK", "Safe: Outside Plume Zone", (
        f"Fire is {dist:.0f} km away. {near_txt} Your location stays clear of the model's plume through Hour 6. Keep monitoring.")


def card(label, value, delta, cls=""):
    return f'<div class="card {cls}"><div class="l">{label}</div><div class="v">{value}</div><div class="d">{delta}</div></div>'


# ---------- header, timeline, metrics ----------
t1, t3, t2 = st.columns([5, 3, 1.4], vertical_alignment="bottom")
t1.slider("Forecast timeline (hours after forecast issue time)", 0, 6, key="hour", format="Hour %d")
t3.selectbox("Forecast issued at", eng.times, key="t0", format_func=lambda t: t.strftime("%d %b %Y %H:%M UTC"))
t2.button("Reset to Hour 0", on_click=reset_hour)
h = st.session_state.hour  # re-read after the widgets/callback
t0 = st.session_state.t0

S = eng.summary(t0, h)  # everything below comes from the model's predictions
P = eng.build(t0, h)
cities = P["cities"]
n = S["n_flagged"]
label, lcls = aqi_label(S["peak_pm"])

st.markdown(
    '<div class="cards">'
    + card("Active Monitoring Zone", "Quebec Fire Complex", f"Forecast issued {t0:%d %b %H:%M} UTC", "")
    + card("Cities Above Alert Threshold", f"{n} of {len(cities)}", f"PM2.5 >= {ALERT_UGM3:.0f} ug/m3 (Hour {h})",
           "crit" if n >= 3 else "warn" if n else "")
    + card("Wind Vector at Fire", f"{S['wind_kmh']} km/h ({S['wind_from']})", f"Smoke moving toward {S['travel_to']}", "warn")
    + card("Downwind Air Quality", f"{label} (PM2.5: {S['peak_pm']:.0f})", f"Peak city: {nice(S['peak_city'])}", lcls)
    + "</div>",
    unsafe_allow_html=True,
)

if eng.demo:
    st.markdown('<div class="zone"><span class="badge warn">Demo data</span>&nbsp; Model files not found, so this runs on a built-in '
                'synthetic smoke event. Put test_predictions.csv and fire_wind.csv in ./data to use the real model output.</div>',
                unsafe_allow_html=True)

# ---------- map + advisory ----------
left, right = st.columns([2, 1])
rc = right.container(key="rightcol")

with rc:
    # Permission state is re-read when the forecast hour changes; a switch to "granted" re-requests GPS.
    perm = streamlit_js_eval(
        js_expressions="(navigator.permissions ? navigator.permissions.query({name:'geolocation'}).then(r => r.state) : Promise.resolve('unknown'))",
        key=f"perm_{h}",
    )
    prev = st.session_state.get("perm_last")
    if perm and perm != prev:
        st.session_state.perm_last = perm
        if perm == "granted" and prev is not None:  # permission changed: drop map override, ask GPS again
            st.session_state.geo_n = st.session_state.get("geo_n", 0) + 1
            st.session_state.pop("click_loc", None)
            st.session_state.pop("gps_loc", None)
            st.session_state.fell_back = False
            st.session_state.locsrc = "Auto-detect Device GPS"
    geo = get_geolocation(component_key=f"geo_{st.session_state.get('geo_n', 0)}")  # prompts on first load
    if geo and "coords" in geo:
        st.session_state.gps_loc = (geo["coords"]["latitude"], geo["coords"]["longitude"])
    elif geo and "error" in geo:
        st.session_state.gps_loc = None
    if st.session_state.get("locsrc") is None:
        st.session_state.locsrc = "Auto-detect Device GPS"
    # Fallback: GPS denied/unavailable -> switch the toggle to map clicks (before the radio is created)
    if geo and "error" in geo and not st.session_state.get("fell_back"):
        st.session_state.fell_back = True
        st.session_state.locsrc = "Click on Map to Test Location"
    src = st.radio("Test location source", ["Auto-detect Device GPS", "Click on Map to Test Location"], horizontal=True, key="locsrc")
    if src.startswith("Auto") and st.session_state.get("prev_src", "").startswith("Click"):
        # switched back to auto-detect: re-request browser geolocation, no button needed
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
    alert_slot = st.empty()  # filled after the map so a fresh click is already known

with left:
    mode = st.radio("Map display mode", ["Wildfire Plume & Spread", "Air Quality (AQI) Heat Map"],
                    horizontal=True, label_visibility="collapsed", key="mode")
    # Auto mode with a nearby GPS fix: open on the user; otherwise the regional overview of the fire
    if src.startswith("Auto") and user and km_between(user, IGNITION) < 3000:
        center, zoom = user, 7
    else:
        center, zoom = (45.0, -74.5), 5
    m = folium.Map(location=center, zoom_start=zoom, tiles="OpenStreetMap")
    # st_folium sets #map_div to an inline `height` px; make it fill the (CSS-resized) iframe instead
    m.get_root().header.add_child(
        folium.Element("<style>html,body{height:100%;margin:0;overflow:hidden}#map_div,#map_div2,.folium-map{height:100vh!important}</style>")
    )
    folium.Marker(
        IGNITION,
        tooltip="Fire origin",
        popup="Fire origin - Quebec",
        icon=folium.Icon(color="red", icon="fire", prefix="fa"),
    ).add_to(m)
    if user:
        folium.Marker(user, tooltip="Your test location", icon=folium.Icon(color="darkblue", icon="user", prefix="fa")).add_to(m)
    if mode.startswith("Air"):
        HeatMap(eng.heat_points(t0, h), radius=38, blur=28, min_opacity=0.25, max_val=1.0, gradient=HEAT_GRADIENT).add_to(m)
    else:
        eng.add_to_map(m, t0, h)  # model-synced plume + flagged/unflagged city markers
    res = st_folium(m, use_container_width=True, height=560, returned_objects=["last_clicked"], key="map")
    c = (res or {}).get("last_clicked")
    if c and src.startswith("Click") and (c["lat"], c["lng"]) != st.session_state.get("click_loc"):
        st.session_state.click_loc = (c["lat"], c["lng"])
        st.rerun()

acls, icon, atitle, abody = location_alert(user, h, geo_state, t0, cities)
if user:
    abody += f'<div style="opacity:.7;margin-top:4px;font-size:.78rem">Location source: {"Map click" if src.startswith("Click") else "Device GPS"}</div>'
alert_slot.markdown(
    f'<div class="alert {acls}"><div class="ic">{icon}</div><div><div class="t">{atitle}</div><div class="b">{abody}</div></div></div>',
    unsafe_allow_html=True,
)

# ---------- advisory text generated from the flagged cities ----------
fl = sorted([c for c in cities if c["flagged"]], key=lambda c: c["dist_km"])  # nearest to the fire first
fl_names = ", ".join(nice(c["city"]) for c in fl) or "none"
seq = "".join(
    f"<li><b>{i}. {nice(c['city'])}</b> ({c['dist_km']:.0f} km from fire): PM2.5 {c['pm_h']:.0f} ug/m3, "
    f"{aqi_label(c['pm_h'])[0]}. Issue {'a shelter-in-place order' if c['pm_h'] >= 150 else 'an air quality advisory'}.</li>"
    for i, c in enumerate(fl, 1)
) or "<li>No city above threshold. Continue monitoring.</li>"
threat, tcls = ("High", "crit") if n >= 3 else ("Elevated", "warn") if n else ("Low", "ok")

with rc:
    with st.container(key="advisory"):
        gov, pub = st.tabs(["Government / Municipal Command", "Public / Citizen Advisory"])
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
</div>""",
                unsafe_allow_html=True,
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
</div>""",
                unsafe_allow_html=True,
            )

    meta = load_meta(eng.data_dir) if eng.data_dir else {}
    mm, hw = meta.get("metrics", {}), meta.get("hardware_audit", {})
    st.markdown(
        '<div class="sys">'
        + card("Backend", "LinuxONE Secure Container", f"Connected | {hw.get('architecture', 's390x')}", "")
        + card("Model", f"Random Forest ({hw.get('ml_backend', 'n/a')})",
               ("Demo data (synthetic)" if eng.demo else f"6h MAE {mm.get('MAE', 'n/a')} ug/m3 | {mm.get('MAE_improvement_vs_baseline_pct', 'n/a')}% vs persistence"), "")
        + "</div>",
        unsafe_allow_html=True,
    )
