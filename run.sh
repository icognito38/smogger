#!/usr/bin/env bash
# Run with the project's venv; the global pipx `streamlit` has no folium installed.
cd "$(dirname "$0")"
[ -d .venv ] || { python -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
exec .venv/bin/streamlit run app.py "$@"
