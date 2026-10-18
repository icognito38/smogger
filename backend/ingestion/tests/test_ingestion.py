import json

import requests

from ingestion.client import FirmsClient, parse_firms_csv
from ingestion.config import FirmsConfig
from ingestion.models import FireHotspotBatch
from ingestion.scheduler import is_stale
from ingestion.storage import write_batch


def test_keeps_only_the_five_fields():
    csv_text = (
        "latitude,longitude,bright_ti4,acq_date,acq_time,satellite,instrument,confidence,frp,daynight\n"
        "19.39828,-155.29004,332.19,2026-10-17,5,N,VIIRS,h,59.85,D\n"
    )
    [hotspot] = parse_firms_csv(csv_text)
    assert hotspot.to_dict() == {
        "latitude": 19.39828, "longitude": -155.29004, "date": "2026-10-17", "time": "00:05", "confidence": "h",
    }


def test_loads_numbered_keys_from_ingestion_dotenv(monkeypatch):
    monkeypatch.delenv("FIRMS_MAP_KEYS", raising=False)
    for number in range(1, 6):
        monkeypatch.delenv(f"FIRMS_MAP_KEYS{number}", raising=False)
    from ingestion import config

    monkeypatch.setattr(config, "_read_dotenv", lambda path: {
        "FIRMS_MAP_KEYS1": "'first-key'", "FIRMS_MAP_KEYS2": '"second-key"', "FIRMS_MAP_KEYS3": "third-key",
    })
    assert FirmsConfig.from_environment().map_keys == ("first-key", "second-key", "third-key")


class FakeResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code, self.text, self.ok = status_code, text, status_code < 400

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def iter_lines(self, decode_unicode=False):
        yield from self.text.splitlines()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, timeout, stream=False):
        self.calls.append(url)
        if "bad-key" in url:
            return FakeResponse(403, "invalid key")
        if "no-data-key" in url:  # FIRMS answers 200 with an error text for an unknown key
            return FakeResponse(200, "Invalid MAP_KEY.")
        if "/data_availability/" in url:
            return FakeResponse(200, "data_id,min_date,max_date\nVIIRS_SNPP_NRT,2026-08-01,2026-10-17\n")
        return FakeResponse(200, "latitude,longitude,acq_date,acq_time,confidence\n1,2,2026-10-17,1200,h\n")


def test_tries_keys_in_order_and_fetches_the_available_date():
    session = FakeSession()
    client = FirmsClient(FirmsConfig(map_keys=("bad-key", "no-data-key", "working-key")), session=session)

    batch = client.fetch_global_hotspots()

    assert len(batch.hotspots) == 1 and batch.date == "2026-10-17"
    assert "bad-key" in session.calls[0] and "no-data-key" in session.calls[1]
    assert "/data_availability/" in session.calls[2] and "working-key" in session.calls[2]
    assert session.calls[3].endswith("/area/csv/working-key/VIIRS_SNPP_NRT/world/1/2026-10-17")


def test_write_batch_and_staleness(tmp_path):
    out = tmp_path / "firms.json"
    assert is_stale(out)
    batch = FireHotspotBatch("2.0", "VIIRS_SNPP_NRT", "world", 1, "2026-10-17", "now", parse_firms_csv(
        "latitude,longitude,acq_date,acq_time,confidence\n1,2,2026-10-17,0930,n\n"))
    write_batch(batch, out)
    assert json.loads(out.read_text())["hotspots"][0]["time"] == "09:30"
    assert not is_stale(out)
