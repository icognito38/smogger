import folium
import streamlit as st
from streamlit_folium import st_folium

st.set_page_config(page_title="Wildfire & Smog Intelligence", page_icon="🔥", layout="wide")

# Mock data (replace with LinuxONE inference output)
CENTER = (37.7749, -122.4194)
IGNITION = (37.8044, -122.4500)
# Plume widens toward the SE (downwind of a NW wind) over Oakridge District
PLUME = [
    (37.8044, -122.4500),
    (37.7950, -122.4620),
    (37.7650, -122.4150),
    (37.7450, -122.3850),
    (37.7550, -122.3650),
    (37.7850, -122.3900),
]

st.title("🔥 Real-Time Wildfire & Smog Intelligence Platform")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Active Monitoring Zone", "Sector 4 (North Hills)", "Live Feed", delta_color="off")
c2.metric("Predicted Fire Severity", "High Risk", "45 Hectares", delta_color="inverse")
c3.metric("Wind Vector", "28 km/h (NW)", "Shifting", delta_color="off")
c4.metric("Downwind Air Quality", "Hazardous (PM2.5)", "Alert Active", delta_color="inverse")

left, right = st.columns([2, 1])

with left:
    m = folium.Map(location=CENTER, zoom_start=12, tiles="OpenStreetMap")
    folium.Marker(
        IGNITION,
        popup="Predicted ignition origin",
        tooltip="Predicted ignition origin",
        icon=folium.Icon(color="red", icon="fire", prefix="fa"),
    ).add_to(m)
    folium.Polygon(
        PLUME,
        color="#8b0000",
        weight=2,
        fill=True,
        fill_color="#d2420a",
        fill_opacity=0.45,
        tooltip="Projected smog plume (next 6 h)",
    ).add_to(m)
    st_folium(m, use_container_width=True, height=560, returned_objects=[])

with right:
    st.subheader("🤖 AI Municipal Advisory")
    st.error(
        "**THREAT LEVEL: HIGH**\n\n"
        "A wildfire is forecast to ignite in Sector 4 (North Hills) and grow to ~45 ha. "
        "NW winds at 28 km/h will carry hazardous PM2.5 smoke toward the **Oakridge District** "
        "within ~2 hours.\n\n"
        "**Recommendations**\n"
        "- Issue voluntary evacuation for Oakridge District\n"
        "- Close schools and open indoor air-filtered shelters\n"
        "- Advise N95 use and keep windows closed\n"
        "- Pre-position fire crews on the north ridge access road"
    )


    st.subheader("⚙️ System Status")
    st.success("🟢 Connected: LinuxONE Secure Container")
    s1, s2 = st.columns(2)
    s1.metric("Model", "Random Forest")
    s2.metric("Dispersion", "Grid")
    s3, s4 = st.columns(2)
    s3.metric("Inference", "42 ms", "-8 ms")
    s4.metric("Last Refresh", "2 s ago")
