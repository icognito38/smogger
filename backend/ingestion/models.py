from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class FireHotspot:
    fire_id: str
    latitude: float
    longitude: float
    confidence: str
    confidence_score: float | None
    acquired_at_utc: str
    satellite: str
    instrument: str
    source: str
    source_day_range: int
    brightness_temperature_k: float | None
    fire_radiative_power_mw: float | None
    daynight: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FireHotspotBatch:
    schema_version: str
    source: str
    region: str
    day_range: int
    retrieved_at_utc: str
    hotspots: list[FireHotspot]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "region": self.region,
            "day_range": self.day_range,
            "retrieved_at_utc": self.retrieved_at_utc,
            "hotspots": [hotspot.to_dict() for hotspot in self.hotspots],
        }


@dataclass(frozen=True)
class DataAvailabilityResult:
    source: str
    available: bool
    checked_at_utc: str
    status_code: int
    response_excerpt: str
