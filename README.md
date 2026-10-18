# 🔥 Smogger

**Predict wildfires. Track smoke. Protect communities.**

WildfireAI is an AI-powered platform designed to predict wildfire risks, simulate smoke dispersion, and identify communities potentially affected by downwind pollution.

By combining **predictive AI, generative AI, and geospatial visualisation**, the project transforms environmental data into actionable insights to support wildfire preparedness and public safety.

## 🌍 Key Features

- 🔥 **Wildfire Prediction** — Identify potential fire ignition zones and estimate fire severity and burned area.
- 💨 **Smoke Dispersion** — Simulate how wind carries smoke across surrounding regions.
- 🌫️ **Air Quality Estimation** — Estimate potential pollution impacts in affected areas.
- 🏙️ **Community Risk Assessment** — Identify towns and population centres potentially exposed to wildfire smoke.
- 🤖 **Generative AI Advisories** — Generate clear, context-aware safety recommendations and public health alerts.
- 🗺️ **Interactive Visualisation** — Display wildfire risks, smoke trajectories, affected communities, and alerts on a map.
- ☁️ **LinuxONE Deployment** — Explore AI-powered environmental monitoring within an IBM LinuxONE environment.

## ⚙️ How It Works

WildfireAI combines environmental and meteorological data with machine learning to predict wildfire risks and potential fire severity. Wind-based dispersion modelling estimates the movement of smoke, helping identify potentially affected communities.

Generative AI then transforms these predictions into accessible safety advisories, while interactive visualisations communicate the results clearly.

## 🎯 Our Mission

To go beyond predicting where wildfires may occur by understanding where their effects may spread.

WildfireAI aims to demonstrate how predictive and generative AI can work together to support faster risk assessment, clearer communication, and more informed wildfire preparedness.

## ⚠️ Disclaimer

WildfireAI is a prototype for research and demonstration purposes. Smoke dispersion and air quality outputs are estimates, not certified forecasts. The platform is not a substitute for official emergency warnings or professional environmental assessments.

---

**Built with AI for a safer, more resilient future.**

## 🛰️ Live fire data: NASA FIRMS

`backend/ingestion` downloads one day of global VIIRS (`VIIRS_SNPP_NRT`) hotspots from NASA FIRMS:

1. `data_availability` endpoint first, to find the newest available date;
2. `area` endpoint for that date (CSV, streamed row by row; usually 50,000+ rows).

Up to five map keys (`FIRMS_MAP_KEYS1` … `FIRMS_MAP_KEYS5`) are tried in order; a key that errors or has no data
falls through to the next. Each record keeps only latitude, longitude, date, time and confidence and is saved to
`data/firms_hotspots.json`.

`app.py` starts a background refresh on launch (fetch if the file is missing or older than 24 h, then every 24 h),
groups the hotspots into the densest clusters worldwide and lists them under **Country: Live NASA FIRMS**. These
clusters run through the app's fallback dispersion; the Random Forest plume model only covers the fires it was
trained on (Quebec).

```bash
cp backend/ingestion/.env.example backend/ingestion/.env   # then paste your keys; never commit this file
cd backend && python -m ingestion.cli --once                # one fetch now
cd backend && python -m ingestion.cli                        # fetch every 24 h
python -m pytest backend/ingestion/tests                     # from backend/: python -m pytest ingestion/tests
```

See `backend/ingestion/README.md` for details.
