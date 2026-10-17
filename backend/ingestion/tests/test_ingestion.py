import requests

from ingestion.client import FirmsClient, parse_firms_csv
from ingestion.config import FirmsConfig
from ingestion.scheduler import next_midnight


def test_parses_standardized_hotspot_fields():
    csv_text = (
        "latitude,longitude,bright_ti4,acq_date,acq_time,satellite,"
        "instrument,confidence,frp,daynight\n"
        "19.39828,-155.29004,332.19,2026-10-17,5,N,VIIRS,h,59.85,D\n"
    )

    hotspots = parse_firms_csv(csv_text, "VIIRS_SNPP_NRT", 1)

    assert len(hotspots) == 1
    assert hotspots[0].latitude == 19.39828
    assert hotspots[0].longitude == -155.29004
    assert hotspots[0].confidence == "h"
    assert hotspots[0].confidence_score == 90.0
    assert hotspots[0].acquired_at_utc == "2026-10-17T00:05:00+00:00"


def test_next_midnight_uses_london_timezone():
    scheduled = next_midnight()
    assert scheduled.tzinfo is not None
    assert scheduled.hour == 0
    assert scheduled.minute == 0


def test_loads_numbered_keys_from_ingestion_dotenv(monkeypatch):
    monkeypatch.delenv("FIRMS_MAP_KEYS", raising=False)
    for number in range(1, 6):
        monkeypatch.delenv(f"FIRMS_MAP_KEYS{number}", raising=False)

    from ingestion import config

    monkeypatch.setattr(
        config,
        "_read_dotenv",
        lambda path: {
            "FIRMS_MAP_KEYS1": "'first-key'",
            "FIRMS_MAP_KEYS2": '"second-key"',
            "FIRMS_MAP_KEYS3": "third-key",
        },
    )

    assert FirmsConfig.from_environment().map_keys == (
        "first-key",
        "second-key",
        "third-key",
    )


class FakeResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text
        self.ok = status_code < 400

    def raise_for_status(self):
        if not self.ok:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, timeout):
        self.calls.append(url)
        if "bad-key" in url:
            return FakeResponse(403, "invalid key")
        if "/data_availability/" in url:
            return FakeResponse(200, "availability")
        return FakeResponse(
            200,
            "latitude,longitude,acq_date,acq_time,confidence\n"
            "1,2,2026-10-17,1200,h\n",
        )


def test_tries_keys_in_order_until_one_succeeds():
    session = FakeSession()
    client = FirmsClient(
        FirmsConfig(map_keys=("bad-key", "working-key")),
        session=session,
    )

    batch = client.fetch_global_hotspots()

    assert len(batch.hotspots) == 1
    assert "bad-key" in session.calls[0]
    assert "working-key" in session.calls[1]
    assert "working-key" in session.calls[2]
