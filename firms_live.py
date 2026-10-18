"""NASA FIRMS hotspots -> live fire incidents for app.py.

The ingestion package (backend/ingestion) writes data/firms_hotspots.json. This module reads it, groups the
detections into 0.1-degree cells worldwide, and turns the densest cells into selectable regions holding fire
dicts with the same keys as the hand-written FIRES in app.py. These live fires have no Random Forest rows, so app.py runs them
through its fallback dispersion path; FIRMS gives position, size and detection confidence, not wind.
"""
import json
import logging
import sys
import threading
from collections import defaultdict
from math import cos, radians
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIRMS_JSON = ROOT / "data" / "firms_hotspots.json"
CONF_SCORE = {"l": 25.0, "n": 50.0, "h": 90.0}  # VIIRS low / nominal / high
CELL_DEG = 0.1
MIN_DETECTIONS = 3
FIRES_PER_REGION = 2
LOGGER = logging.getLogger(__name__)


def load_hotspots(path=FIRMS_JSON):
    """(hotspots, date) from the ingestion JSON; ([], None) when the file is missing or unreadable."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data.get("hotspots", []), data.get("date")
    except (OSError, ValueError):
        return [], None


def in_box(lat, lon, b):
    return b[0] <= lat <= b[2] and b[1] <= lon <= b[3]


LIVE_COUNTRY = "Live NASA FIRMS"
CLUSTERS = 10  # densest clusters worldwide that become selectable regions
PAD_DEG = 0.3


def live_fires(hotspots, date=None, clusters=CLUSTERS, cell=CELL_DEG):
    """Densest hotspot clusters worldwide -> (fire dicts keyed like app.py FIRES, {region: bounds box})."""
    cells = defaultdict(list)
    for p in hotspots:
        cells[(int(p["latitude"] // cell), int(p["longitude"] // cell))].append(p)
    top = sorted((c for c in cells.values() if len(c) >= MIN_DETECTIONS), key=len, reverse=True)[:clusters]
    fires, bounds = [], {}
    for i, pts in enumerate(top, 1):
        n = len(pts)
        lat = sum(p["latitude"] for p in pts) / n
        lon = sum(p["longitude"] for p in pts) / n
        conf = round(sum(CONF_SCORE.get(p["confidence"], 50.0) for p in pts) / n, 1)
        high = sum(p["confidence"] == "h" for p in pts) / n
        score = min(100, round(20 + 60 * min(n, 30) / 30 + 20 * high))
        sev, cls = ("Extreme Risk", "crit") if score >= 80 else ("High Risk", "crit") if score >= 60 else ("Moderate Risk", "warn")
        region = f"Cluster {i} ({lat:.2f}, {lon:.2f})"
        bounds[region] = (min(p["latitude"] for p in pts) - PAD_DEG, min(p["longitude"] for p in pts) - PAD_DEG,
                          max(p["latitude"] for p in pts) + PAD_DEG, max(p["longitude"] for p in pts) + PAD_DEG)
        # shortcut: FIRMS has no wind, so smoke is assumed to drift east (prevailing westerlies); use real wind once available
        target = (lat, lon + 10 / (111.32 * cos(radians(lat))))
        fires.append(dict(
            name=f"FIRMS Cluster {i}", short=f"Cluster {i}", origin=(lat, lon), target=target,
            target_name="downwind communities", ha=n * 14,  # one VIIRS pixel ~ 375 m x 375 m ~ 14 ha
            pm=min(560, 120 + 15 * n), reach=min(15.0, 4 + 0.3 * n), wind=20, wdir="W", walt="WSW",
            country=LIVE_COUNTRY, region=region, sev=sev, cls=cls, score=score, conf=conf,
            staging="nearest fire station staging area", helibase="regional helibase",
            route="the designated evacuation route", hospital="the nearest hospital",
            avoid="fire-access roads", nearby="adjacent settlements",
            live=True, detections=n, firms_date=date,
        ))
    return fires, bounds


def start_refresh_thread():
    """Fetch now if the JSON is missing or >24 h old, then every 24 h, in a daemon thread. False if no keys."""
    sys.path.insert(0, str(ROOT / "backend"))
    try:
        from ingestion.client import FirmsClient
        from ingestion.config import FirmsConfig
        from ingestion.scheduler import run_every_24h
        client = FirmsClient(FirmsConfig.from_environment())
    except Exception as error:  # no keys / missing dependency: the app still runs on the last saved file
        LOGGER.warning("FIRMS refresh disabled: %s", error)
        return False
    threading.Thread(target=run_every_24h, args=(client, FIRMS_JSON), daemon=True, name="firms-refresh").start()
    return True


if __name__ == "__main__":  # self-check on a tiny synthetic set
    pts = [dict(latitude=49.01 + k * 0.001, longitude=-73.01, confidence="h") for k in range(5)]
    [f], b = live_fires(pts, "2026-10-17")
    assert f["detections"] == 5 and f["conf"] == 90.0 and in_box(49.01, -73.01, b[f["region"]])
    print("ok", f["region"], f["score"], f["sev"])
