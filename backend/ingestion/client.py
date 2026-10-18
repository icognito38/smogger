import csv
import logging
from collections.abc import Iterable
from datetime import datetime, timezone

import requests

from ingestion.config import FirmsConfig
from ingestion.models import DataAvailabilityResult, FireHotspot, FireHotspotBatch

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api"
AVAILABILITY_URL = BASE_URL + "/data_availability/csv/{key}/{source}"
AREA_URL = BASE_URL + "/area/csv/{key}/{source}/{region}/{day_range}/{date}"


class FirmsClient:
    def __init__(self, config: FirmsConfig, session: requests.Session | None = None):
        self.config = config
        self.session = session or requests.Session()

    def check_data_availability(self, key: str) -> DataAvailabilityResult:
        """Step 1: ask FIRMS which dates exist for the source (CSV: data_id,min_date,max_date)."""
        checked_at = datetime.now(timezone.utc).isoformat()
        response = self.session.get(
            AVAILABILITY_URL.format(key=key, source=self.config.source),
            timeout=self.config.timeout_seconds,
        )
        min_date = max_date = None
        if response.ok:
            for row in csv.DictReader(response.text.splitlines()):
                if row.get("data_id") == self.config.source:
                    min_date, max_date = row.get("min_date"), row.get("max_date")
        return DataAvailabilityResult(
            source=self.config.source,
            # an invalid key returns 200 with a text error, so a dated row is the real signal
            available=bool(response.ok and max_date),
            checked_at_utc=checked_at,
            status_code=response.status_code,
            min_date=min_date,
            max_date=max_date,
        )

    def fetch_global_hotspots(self) -> FireHotspotBatch:
        """Try each map key in order: availability check, then the area download for the newest date."""
        failures: list[str] = []
        availability_results: list[DataAvailabilityResult] = []
        for key_number, key in enumerate(self.config.map_keys, start=1):
            try:
                availability = self.check_data_availability(key)
                availability_results.append(availability)
                if not availability.available:
                    failures.append(f"key {key_number}: no data available (HTTP {availability.status_code})")
                    continue

                # newest available day, counted backwards by day_range
                date = availability.max_date
                with self.session.get(
                    AREA_URL.format(key=key, source=self.config.source, region=self.config.region,
                                    day_range=self.config.day_range, date=date),
                    timeout=self.config.timeout_seconds,
                    stream=True,
                ) as response:
                    response.raise_for_status()
                    hotspots = parse_firms_lines(response.iter_lines(decode_unicode=True))
                return FireHotspotBatch(
                    schema_version="2.0",
                    source=self.config.source,
                    region=self.config.region,
                    day_range=self.config.day_range,
                    date=date,
                    retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
                    hotspots=hotspots,
                    data_availability=availability_results,
                )
            except requests.RequestException as error:
                failures.append(f"key {key_number}: {type(error).__name__}")
            except ValueError as error:
                failures.append(f"key {key_number}: invalid response ({error})")
            LOGGER.warning("FIRMS %s; trying next key", failures[-1])

        raise RuntimeError("NASA FIRMS request failed for every configured map key: " + "; ".join(failures))


def parse_firms_lines(lines: Iterable[str]) -> list[FireHotspot]:
    """Parse FIRMS CSV row by row (the global file can exceed 50k rows) keeping only the 5 used fields."""
    reader = csv.DictReader(line for line in lines if line)
    missing = {"latitude", "longitude", "acq_date", "acq_time"} - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"missing FIRMS columns: {', '.join(sorted(missing))}")
    return [
        FireHotspot(
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            date=row["acq_date"],
            time=_hhmm(row["acq_time"]),
            confidence=str(row.get("confidence", "")).strip().lower(),
        )
        for row in reader
    ]


def parse_firms_csv(csv_text: str) -> list[FireHotspot]:
    return parse_firms_lines(csv_text.splitlines())


def _hhmm(acq_time: str) -> str:
    digits = "".join(c for c in str(acq_time) if c.isdigit()).zfill(4)
    return f"{digits[:2]}:{digits[2:4]}"
