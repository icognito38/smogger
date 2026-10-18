from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class FireHotspot:
    """One FIRMS detection, reduced to the five fields the platform uses."""

    latitude: float
    longitude: float
    date: str  # acq_date, YYYY-MM-DD (UTC)
    time: str  # acq_time as HH:MM (UTC)
    confidence: str  # FIRMS value as supplied: l / n / h for VIIRS

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DataAvailabilityResult:
    source: str
    available: bool
    checked_at_utc: str
    status_code: int
    min_date: str | None = None
    max_date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FireHotspotBatch:
    schema_version: str
    source: str
    region: str
    day_range: int
    date: str | None
    retrieved_at_utc: str
    hotspots: list[FireHotspot]
    data_availability: list[DataAvailabilityResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "region": self.region,
            "day_range": self.day_range,
            "date": self.date,
            "retrieved_at_utc": self.retrieved_at_utc,
            "count": len(self.hotspots),
            "data_availability": [a.to_dict() for a in self.data_availability],
            "hotspots": [h.to_dict() for h in self.hotspots],
        }
