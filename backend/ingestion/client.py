import csv
import hashlib
import io
import logging
from datetime import datetime, timezone
from typing import Any

import requests

from ingestion.config import FirmsConfig
from ingestion.models import (
    DataAvailabilityResult,
    FireHotspot,
    FireHotspotBatch,
)

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api"
AVAILABILITY_URL = BASE_URL + "/data_availability/html/{key}/{source}"
AREA_URL = BASE_URL + "/area/csv/{key}/{source}/{region}/{day_range}"
CONFIDENCE_SCORES = {"l": 25.0, "n": 50.0, "h": 90.0}


class FirmsClient:
    def __init__(self, config: FirmsConfig, session: requests.Session | None = None):
        self.config = config
        self.session = session or requests.Session()

    def check_data_availability(self, key: str) -> DataAvailabilityResult:
        checked_at = datetime.now(timezone.utc).isoformat()
        response = self.session.get(
            AVAILABILITY_URL.format(key=key, source=self.config.source),
            timeout=self.config.timeout_seconds,
        )
        excerpt = response.text[:500]
        return DataAvailabilityResult(
            source=self.config.source,
            # FIRMS may return a generic HTML availability page containing the
            # phrase "MAP_KEY" even when the request itself is successful.
            available=response.ok,
            checked_at_utc=checked_at,
            status_code=response.status_code,
            response_excerpt=excerpt,
        )

    def fetch_global_hotspots(self) -> FireHotspotBatch:
        failures: list[str] = []
        availability_results: list[DataAvailabilityResult] = []
        for key_number, key in enumerate(self.config.map_keys, start=1):
            try:
                availability = self.check_data_availability(key)
                availability_results.append(availability)
                if not availability.available:
                    failures.append(
                        f"key {key_number}: availability check failed "
                        f"(HTTP {availability.status_code})"
                    )
                    continue

                response = self.session.get(
                    AREA_URL.format(
                        key=key,
                        source=self.config.source,
                        region=self.config.region,
                        day_range=self.config.day_range,
                    ),
                    timeout=self.config.timeout_seconds,
                )
                response.raise_for_status()
                hotspots = parse_firms_csv(
                    response.text,
                    source=self.config.source,
                    day_range=self.config.day_range,
                )
                return FireHotspotBatch(
                    schema_version="1.0",
                    source=self.config.source,
                    region=self.config.region,
                    day_range=self.config.day_range,
                    retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
                    hotspots=hotspots,
                    data_availability=availability_results,
                )
            except requests.RequestException as error:
                failures.append(f"key {key_number}: {type(error).__name__}")
            except ValueError as error:
                failures.append(f"key {key_number}: invalid response ({error})")

        raise RuntimeError(
            "NASA FIRMS request failed for every configured map key: "
            + "; ".join(failures)
        )


def parse_firms_csv(
    csv_text: str, source: str, day_range: int
) -> list[FireHotspot]:
    reader = csv.DictReader(io.StringIO(csv_text))
    required_columns = {"latitude", "longitude", "acq_date", "acq_time"}
    missing = required_columns - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"missing FIRMS columns: {', '.join(sorted(missing))}")

    hotspots = []
    for row in reader:
        latitude = float(row["latitude"])
        longitude = float(row["longitude"])
        acquired_at = _parse_acquired_at(row["acq_date"], row["acq_time"])
        confidence = str(row.get("confidence", "")).strip().lower()
        hotspots.append(
            FireHotspot(
                fire_id=_fire_id(row, acquired_at),
                latitude=latitude,
                longitude=longitude,
                confidence=confidence,
                confidence_score=CONFIDENCE_SCORES.get(confidence),
                acquired_at_utc=acquired_at,
                satellite=str(row.get("satellite", "")).strip(),
                instrument=str(row.get("instrument", "")).strip(),
                source=source,
                source_day_range=day_range,
                brightness_temperature_k=_optional_float(row.get("bright_ti4")),
                fire_radiative_power_mw=_optional_float(row.get("frp")),
                daynight=str(row.get("daynight", "")).strip() or None,
            )
        )
    return hotspots


def _parse_acquired_at(acq_date: str, acq_time: str) -> str:
    digits = "".join(character for character in str(acq_time) if character.isdigit())
    digits = digits.zfill(4)
    hours, minutes = int(digits[:2]), int(digits[2:4])
    timestamp = datetime.strptime(
        f"{acq_date} {hours:02d}:{minutes:02d}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=timezone.utc)
    return timestamp.isoformat()


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _fire_id(row: dict[str, str], acquired_at: str) -> str:
    identity = "|".join(
        [
            row["latitude"],
            row["longitude"],
            acquired_at,
            row.get("satellite", ""),
            row.get("instrument", ""),
        ]
    )
    return "firms-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
