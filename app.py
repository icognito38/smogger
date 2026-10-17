"""SmokeShield test console. Run:  streamlit run app.py   (needs smokeshield.py next to it)"""
import platform
import time
from datetime import timedelta

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import smokeshield as sm

st.set_page_config(page_title="SmokeShield test console", layout="wide")
st.markdown(
    """<style>
:root { --bg:#14181d; --panel:#1c222a; --line:#38424f; --text:#e6e9ed; --mute:#98a2b0; --crimson:#a4161a; --amber:#c98a0b; --slate:#4a6fa5; }
.stApp { background:var(--bg); color:var(--text); }
header[data-testid="stHeader"], footer { display:none; }
.block-container { padding:0.6rem 1.2rem; max-width:100%; }
.banner { background:var(--panel); border:1px solid var(--line); border-left:6px solid var(--crimson); padding:8px 16px; margin-bottom:8px; }
.banner h1 { font-size:1.1rem; text-transform:uppercase; letter-spacing:.04em; margin:0; }
.banner span { font-size:.72rem; color:var(--mute); text-transform:uppercase; }
.cards { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin:8px 0; }
.card { background:var(--panel); border:1px solid var(--line); border-top:3px solid var(--slate); padding:8px 12px; }
.card.crit { border-top-color:var(--crimson); } .card.warn { border-top-color:var(--amber); }
.card .l { font-size:.68rem; text-transform:uppercase; letter-spacing:.08em; color:var(--mute); }
.card .v { font-size:1.25rem; font-weight:700; line-height:1.3; } .card .d { font-size:.74rem; color:var(--mute); }
</style>""",
    unsafe_allow_html=True,
)


@st.cache_resource(show_spinner="Fetching data and loading/training the model (first run only)...")
def boot():
    data = sm.build_features(sm.fetch_raw())
    bundle = sm.load_or_train(data)
    return sm.score(data, bundle), bundle


df, bundle = boot()
met = sm.metrics(df)
col = lambda v: "#2fb36b" if v < 12 else "#e5c100" if v < 35 else "#f08c00" if v < 55 else "#e03131" if v < 150 else "#7048e8"
card = lambda l, v, d, c="": f'<div class="card {c}"><div class="l">{l}</div><div class="v">{v}</div><div class="d">{d}</div></div>'

st.markdown('<div class="banner"><h1>SmokeShield test console</h1><span>Real model output on held-out test data (June 25 to July 15, 2023)</span></div>', unsafe_allow_html=True)

test = df[(df["Time"] >= sm.SPLIT) & df["Forecast"].notna()]
tmin, tmax = test["Time"].min().to_pydatetime(), test["Time"].max().to_pydatetime()
t = pd.Timestamp(st.slider("Time (UTC): the model forecasts 6 hours after this", tmin, tmax, tmin, step=timedelta(hours=1), format="MMM DD, HH:mm"))

rows = df[df["Time"] == t].dropna(subset=["Forecast"]).sort_values("Forecast", ascending=False)
if rows.empty:
    st.warning("No complete data for that hour.")
    st.stop()

t0 = time.perf_counter()
bundle["model"].predict(rows[sm.FEATURES].values)  # live inference on the selected hour
ms = (time.perf_counter() - t0) * 1000
alerts = rows[rows["Forecast"] >= sm.ALERT]
top = rows.iloc[0]

st.markdown(
    '<div class="cards">'
    + card(f"Cities forecast above {sm.ALERT:.0f} µg/m³", f"{len(alerts)} of {len(rows)}", f"in 6 hours, from {t:%b %d %H:%M} UTC", "crit" if len(alerts) else "")
    + card("Highest forecast", f"{top.City.replace('_', ' ')} {top.Forecast:.0f}", "µg/m³ PM2.5 in 6 hours", "warn")
    + card("Model error (held-out)", f"{met['mae']:.2f} µg/m³ MAE", f"vs {met['base_mae']:.2f} if nothing changes")
    + card("Backend", f"{bundle['backend']} on {platform.machine()}", f"Inference {ms:.1f} ms for {len(rows)} cities")
    + "</div>",
    unsafe_allow_html=True,
)

left, right = st.columns([2, 1])
with left:
    mp = folium.Map(location=(44.5, -75.5), zoom_start=5, tiles="OpenStreetMap")
    folium.Marker(sm.FIRE, tooltip="Fire epicentre (assumed)", icon=folium.Icon(color="red", icon="fire", prefix="fa")).add_to(mp)
    for r in rows.itertuples():
        c = sm.CITIES[r.City]
        folium.CircleMarker(
            (c["lat"], c["lon"]), radius=8 + r.Forecast ** 0.5 * 1.6, color=col(r.Forecast), fill=True, fill_opacity=0.55,
            tooltip=f"{r.City.replace('_', ' ')}: now {r.PM2_5:.0f}, forecast +6h {r.Forecast:.0f} µg/m³",
        ).add_to(mp)
    st_folium(mp, use_container_width=True, height=520, returned_objects=[], key=f"map_{t}")

with right:
    st.dataframe(
        pd.DataFrame({
            "City": rows["City"].str.replace("_", " "), "Now": rows["PM2_5"].round(1),
            "Forecast +6h": rows["Forecast"].round(1), "Actual +6h": rows["Target"].round(1),
            "Alert": ["ALERT" if v >= sm.ALERT else "ok" for v in rows["Forecast"]],
        }),
        hide_index=True, use_container_width=True,
    )
    city = st.selectbox("Chart city", list(rows["City"]))
    d = df[(df["City"] == city) & (df["Time"] >= sm.SPLIT)].set_index("Time")
    st.line_chart(pd.DataFrame({"Actual PM2.5": d["PM2_5"], "Forecast (made 6h earlier)": d["Forecast"].shift(6)}))
