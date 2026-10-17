import folium
import streamlit as st
from folium.plugins import HeatMap
from math import asin, cos, radians, sin, sqrt
from streamlit_folium import st_folium

st.set_page_config(page_title="Wildfire & Smog Intelligence Platform", layout="wide")

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root { --bg:#14181d; --panel:#1c222a; --line:#38424f; --text:#e6e9ed; --mute:#98a2b0;
        --crimson:#a4161a; --amber:#c98a0b; --slate:#4a6fa5; --ok:#3f7d58; --top:200px; --foot:88px; --radio:44px; --pre:190px; }
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
.alert { border:1px solid var(--line); border-left:6px solid var(--slate); background:var(--panel); padding:8px 12px; font-size:.84rem; min-height:96px; box-sizing:border-box; }
.alert.crit { border-left-color:var(--crimson); } .alert.ok { border-left-color:var(--ok); }
.alert b.t { display:block; font-size:.78rem; text-transform:uppercase; letter-spacing:.06em; margin-bottom:3px; }
.stTabs [data-baseweb="tab-list"] { gap:0; border-bottom:1px solid var(--line); }
.stTabs [data-baseweb="tab"] { background:var(--panel); border:1px solid var(--line); border-bottom:none;
        padding:6px 14px; font-size:.78rem; font-weight:600; text-transform:uppercase; letter-spacing:.05em; color:var(--mute); }
.stTabs [aria-selected="true"] { background:var(--slate); color:#fff; }
.panel h4 { font-size:.78rem; text-transform:uppercase; letter-spacing:.08em; color:var(--mute);
            border-bottom:1px solid var(--line); padding-bottom:3px; margin:10px 0 4px 0; }
.panel ul { margin:0 0 0 1.1rem; padding:0; font-size:.84rem; } .panel li { margin-bottom:3px; }
.sys { display:grid; grid-template-columns:1fr 1fr; gap:6px; margin-top:6px; }
.sys .card { border-top-width:2px; padding:5px 10px; } .sys .v { font-size:1rem; }
/* vertical fill: iframe + advisory pane track the viewport height */
iframe[title="streamlit_folium.st_folium"] { height:calc(100vh - var(--top) - var(--radio)) !important; min-height:380px; border:1px solid var(--line); display:block; }
.st-key-advisory { height:calc(100vh - var(--top) - var(--foot) - var(--pre)) !important; min-height:420px; overflow-y:auto; border:1px solid var(--line); background:var(--panel); padding:4px 12px; }
div[data-testid="stSlider"] label p, .stButton button { font-size:.78rem; text-transform:uppercase; letter-spacing:.05em; }
.stButton button { border-radius:0; background:var(--panel); border:1px solid var(--line); color:var(--text); width:100%; }
.stButton button:hover { border-color:var(--crimson); color:#fff; }
</style>
""",
    unsafe_allow_html=True,
)

IGNITION = (37.8044, -122.4500)
OAKRIDGE = (37.7450, -122.3850)
HECTARES = [0, 6, 14, 24, 33, 40, 45]
PM25 = [12, 95, 180, 260, 340, 410, 480]  # ug/m3
REACH_KM = [0, 2.0, 3.9, 5.8, 7.6, 9.0, 10.2]  # plume leading edge; Oakridge is ~8.7 km out
WIND = [28, 28, 30, 31, 29, 28, 27]
WIND_DIR = ["NW", "NW", "NW", "NW", "NNW", "NW", "NW"]
ZONE = [
    "Ignition origin only. No smoke plume projected.",
    "Plume confined to the North Hills ridge corridor (Sector 4).",
    "Plume crossing the southern boundary of Sector 4.",
    "Plume over the Marlow Heights residential corridor.",
    "Plume 1 km from the Oakridge District boundary.",
    "Leading edge has entered the Oakridge District.",
    "Oakridge District fully within the plume; spreading toward the bay shoreline.",
]

if "hour" not in st.session_state:
    st.session_state.hour = 0


def reset_hour():
    st.session_state.hour = 0


def aqi_label(pm):
    if pm >= 250:
        return "Hazardous", "crit"
    if pm >= 150:
        return "Very Unhealthy", "crit"
    if pm >= 55:
        return "Unhealthy", "warn"
    return "Good", "ok"


def plume(h):
    """Fan-shaped polygon from the origin toward Oakridge (SE); length and width grow with hour."""
    dx, dy = OAKRIDGE[0] - IGNITION[0], OAKRIDGE[1] - IGNITION[1]
    n = (dx * dx + dy * dy) ** 0.5
    ux, uy = dx / n, dy / n  # along-wind unit vector (degrees)
    px, py = uy, -ux  # cross-wind unit vector
    length = n * REACH_KM[h] / 8.7
    half = 0.004 + 0.0022 * REACH_KM[h]
    ts = [i / 6 for i in range(7)]
    side = lambda s: [
        (
            IGNITION[0] + ux * length * t + s * px * half * (0.3 + 0.7 * t),
            IGNITION[1] + uy * length * t + s * py * half * (0.3 + 0.7 * t),
        )
        for t in ts
    ]
    return side(1) + side(-1)[::-1]


def get_heatmap_data(h):
    """[lat, lon, weight] points spreading from the ignition along the wind path; intensity tracks PM2.5."""
    dx, dy = OAKRIDGE[0] - IGNITION[0], OAKRIDGE[1] - IGNITION[1]
    n = (dx * dx + dy * dy) ** 0.5
    ux, uy = dx / n, dy / n
    px, py = uy, -ux
    peak = PM25[h] / max(PM25)
    if h == 0:
        return [[*IGNITION, peak]]
    length = n * REACH_KM[h] / 8.7
    half = 0.004 + 0.0022 * REACH_KM[h]
    pts = []
    for i in range(14):
        t = i / 13
        w = peak * (1 - 0.6 * t)  # concentration falls off downwind
        spread = half * (0.3 + 0.7 * t)
        for c in (-1.0, -0.5, 0, 0.5, 1.0):
            pts.append([
                IGNITION[0] + ux * length * t + px * spread * c,
                IGNITION[1] + uy * length * t + py * spread * c,
                w * (1 - 0.5 * abs(c)),
            ])
    return pts


LOCATIONS = {
    "Inside Plume / Affected Zone (Oakridge District / Marlow Heights)": OAKRIDGE,
    "Outside Plume / Safe Zone (Downtown SF / Remote)": (37.7879, -122.4075),
}


def km_between(a, b):
    la1, lo1, la2, lo2 = map(radians, (*a, *b))
    x = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * asin(sqrt(x))


def location_alert(loc, h):
    """Returns (css class, title, body) for the selected test location at forecast hour h."""
    where = LOCATIONS[loc]
    dist = km_between(where, IGNITION)
    if where == OAKRIDGE:
        eta = next((i for i, r in enumerate(REACH_KM) if r >= km_between(where, IGNITION)), None)
        if eta is not None and h >= eta:
            return "crit", "Urgent: Evacuation Order", (
                f"Smoke plume is over your location (PM2.5 {PM25[h]} ug/m3). Evacuate via Route 9 southbound "
                "if ordered; otherwise shelter in place with windows sealed.")
        return "crit", "Urgent: Evacuation Alert", (
            f"Your location is inside the projected plume path. Smoke arrives at about Hour {eta} "
            f"({eta - h} h from now). Prepare to evacuate now; the fire is {dist:.1f} km away in Sector 4.")
    return "ok", "Safety Alert: Outside Affected Zone", (
        f"The nearest fire is {dist:.1f} km away in Sector 4, United States. "
        "Your location is outside the projected plume for the 6-hour forecast. No action required; keep monitoring.")


def card(label, value, delta, cls=""):
    return f'<div class="card {cls}"><div class="l">{label}</div><div class="v">{value}</div><div class="d">{delta}</div></div>'


# ---------- header, timeline, metrics ----------
h = st.session_state.hour
t1, t2 = st.columns([6, 1], vertical_alignment="bottom")
t1.slider("Forecast timeline (hours from predicted ignition)", 0, 6, key="hour", format="Hour %d")
t2.button("Reset to Hour 0", on_click=reset_hour)
h = st.session_state.hour  # re-read after the widget/callback

label, lcls = aqi_label(PM25[h])
wind_delta = "Stable" if WIND_DIR[h] == "NW" and h in (0, 1, 5, 6) else "Shifting"
st.markdown(
    '<div class="cards">'
    + card("Active Monitoring Zone", "Sector 4 (North Hills)", "Live Feed", "")
    + card("Predicted Fire Severity", "High Risk", f"{HECTARES[h]} Hectares (Hour {h})", "crit")
    + card("Wind Vector", f"{WIND[h]} km/h ({WIND_DIR[h]})", wind_delta, "warn")
    + card("Downwind Air Quality", f"{label} (PM2.5: {PM25[h]})", "Alert Active" if h else "Baseline", lcls)
    + "</div>",
    unsafe_allow_html=True,
)

# ---------- map + advisory ----------
left, right = st.columns([2, 1])

with left:
    mode = st.radio("Map display mode", ["Wildfire Plume & Spread", "Air Quality (AQI) Heat Map"],
                    horizontal=True, label_visibility="collapsed", key="mode")
    m = folium.Map(location=(37.775, -122.43), zoom_start=12, tiles="OpenStreetMap")
    # st_folium sets #map_div to an inline `height` px; make it fill the (CSS-resized) iframe instead
    m.get_root().header.add_child(
        folium.Element("<style>html,body{height:100%;margin:0;overflow:hidden}#map_div,#map_div2,.folium-map{height:100vh!important}</style>")
    )
    folium.Marker(
        IGNITION,
        tooltip="Predicted ignition origin",
        popup="Predicted ignition origin - Sector 4 (North Hills)",
        icon=folium.Icon(color="red", icon="fire", prefix="fa"),
    ).add_to(m)
    folium.Marker(
        OAKRIDGE,
        tooltip="Oakridge District",
        icon=folium.Icon(color="blue", icon="home", prefix="fa"),
    ).add_to(m)
    if mode.startswith("Air"):
        HeatMap(get_heatmap_data(h), radius=38, blur=28, min_opacity=0.25, max_val=1.0,
                gradient={0.2: "#4a6fa5", 0.5: "#c98a0b", 0.8: "#c2410c", 1.0: "#7a0f12"}).add_to(m)
    elif h > 0:
        folium.Polygon(
            plume(h),
            color="#7a0f12",
            weight=2,
            fill=True,
            fill_color="#c2410c",
            fill_opacity=0.45,
            tooltip=f"Hour {h}: {HECTARES[h]} ha, PM2.5 {PM25[h]} ug/m3, reach {REACH_KM[h]} km",
        ).add_to(m)
    st_folium(m, use_container_width=True, height=560, returned_objects=[], key=f"map_{mode}_{h}")

with right:
    loc = st.selectbox("Test User Location", list(LOCATIONS), key="loc")
    cls, title, body = location_alert(loc, h)
    st.markdown(f'<div class="alert {cls}"><b class="t">{title}</b>{body}</div>', unsafe_allow_html=True)
    with st.container(key="advisory", height=560):
        gov, pub = st.tabs(["Government / Municipal Command", "Public / Citizen Advisory"])
        with gov:
            st.markdown(
                f"""<div class="panel">
<div class="zone"><span class="badge {lcls}">Hour {h}</span>&nbsp; {ZONE[h]}</div>
<h4>Strategic Incident Metrics</h4>
<ul><li>Projected burn area: <b>{HECTARES[h]} ha</b></li>
<li>Plume leading edge: <b>{REACH_KM[h]} km</b> SE of origin</li>
<li>Peak PM2.5: <b>{PM25[h]} ug/m3</b> ({label})</li>
<li>Threat level: <span class="badge crit">High</span></li></ul>
<h4>Resource Pre-Positioning Orders</h4>
<ul><li>Engine Strike Teams 1-3 to the North Ridge access road staging area</li>
<li>Air tanker and helitanker standby at Sector 4 helibase</li>
<li>Mobile air-quality monitors to Oakridge District and Marlow Heights</li>
<li>EMS surge units to Oakridge Community Hospital</li></ul>
<h4>Mandatory Evacuation Sequencing</h4>
<ul><li><b>Phase 1</b> (Hour 0-2): Sector 4 residences and ridge trailheads</li>
<li><b>Phase 2</b> (Hour 2-4): Marlow Heights, special-needs and care facilities first</li>
<li><b>Phase 3</b> (Hour 4-6): Oakridge District, via Route 9 southbound</li></ul>
<h4>Inter-Agency Coordination</h4>
<ul><li>State fire agency: unified command established at Sector 4 post</li>
<li>Highway patrol: contraflow on Route 9 on Phase 3 order</li>
<li>County health: shelter and respirator distribution</li>
<li>Meteorological service: hourly wind-shift updates to the dispersion model</li></ul>
</div>""",
                unsafe_allow_html=True,
            )
        with pub:
            st.markdown(
                f"""<div class="panel">
<div class="zone"><span class="badge {lcls}">{label}</span>&nbsp; Air quality forecast for Hour {h}. {ZONE[h]}</div>
<h4>Shelter in Place (Oakridge District)</h4>
<ul><li>Stay indoors. Close all windows, doors and fireplace dampers.</li>
<li>Turn off fans that draw in outside air; set HVAC to recirculate.</li></ul>
<h4>Air Filtration</h4>
<ul><li>Run HEPA purifiers in one sealed room.</li>
<li>If you must go outside, wear a fitted N95 or P100 respirator. Cloth and surgical masks do not protect against smoke.</li>
<li>Children, older adults and people with asthma or heart conditions should avoid all exertion.</li></ul>
<h4>Evacuation Corridors</h4>
<ul><li><b>Oakridge District:</b> leave via Route 9 southbound only when ordered. Do not travel north or west.</li>
<li>Avoid Ridge Road; it is reserved for emergency vehicles.</li>
<li>Take medications, documents, pets and a 3-day supply of water.</li></ul>
<h4>Stay Informed</h4>
<ul><li>Follow official alerts on the county emergency channel and emergency radio.</li>
<li>Emergency information line: 211</li></ul>
</div>""",
                unsafe_allow_html=True,
            )

    st.markdown(
        '<div class="sys">'
        + card("Backend", "LinuxONE Secure Container", "Connected", "")
        + card("Model", "Random Forest + Dispersion Grid", "Inference 42 ms (-8 ms)", "")
        + "</div>",
        unsafe_allow_html=True,
    )
