"""Data models for the wildfire smog project.

Every model validates its own data in ``__post_init__`` so that bad values
(from the command line or from a hand-edited JSON file) are rejected early
with a clear message instead of causing strange results later.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class ValidationError(ValueError):
    """Raised when input or stored data is invalid."""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def utc_now() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


def to_iso(moment: datetime) -> str:
    """Format a datetime as an ISO-8601 UTC string without microseconds."""
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def parse_timestamp(text: Any) -> datetime:
    """Parse an ISO-8601 string into a timezone-aware UTC datetime."""
    if not isinstance(text, str):
        raise ValidationError(f"Timestamp must be a string, got {text!r}")
    try:
        moment = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"Invalid timestamp: {text!r}") from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _number(
    value: Any,
    field: str,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    """Return ``value`` as a finite float inside [minimum, maximum]."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{field} must be a number, got {value!r}")
    result = float(value)
    if math.isnan(result) or math.isinf(result):
        raise ValidationError(f"{field} must be a finite number")
    if minimum is not None and result < minimum:
        raise ValidationError(f"{field} must be >= {minimum}, got {result}")
    if maximum is not None and result > maximum:
        raise ValidationError(f"{field} must be <= {maximum}, got {result}")
    return result


def _optional_number(value: Any, field: str, minimum: float = 0.0) -> Optional[float]:
    return None if value is None else _number(value, field, minimum=minimum)


def _name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} must be a non-empty string")
    return value.strip()


def _require(data: Dict[str, Any], key: str) -> Any:
    if key not in data:
        raise ValidationError(f"Missing required field: {key!r}")
    return data[key]


def _check_dict(data: Any, what: str) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise ValidationError(f"{what} must be a JSON object, got {type(data).__name__}")
    return data


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
@dataclass
class City:
    """A city whose air quality we want to know.

    ``wind_from_deg`` follows the meteorological convention: 0/360 means the
    wind blows FROM the north, 90 from the east, and so on.
    """

    name: str
    latitude: float
    longitude: float
    wind_from_deg: float = 0.0
    wind_speed_kmh: float = 0.0

    def __post_init__(self) -> None:
        self.name = _name(self.name, "City name")
        self.latitude = _number(self.latitude, "latitude", -90, 90)
        self.longitude = _number(self.longitude, "longitude", -180, 180)
        self.wind_from_deg = _number(self.wind_from_deg, "wind_from_deg", 0, 360) % 360
        self.wind_speed_kmh = _number(self.wind_speed_kmh, "wind_speed_kmh", 0, 400)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "City":
        data = _check_dict(data, "City")
        return cls(
            name=_require(data, "name"),
            latitude=_require(data, "latitude"),
            longitude=_require(data, "longitude"),
            wind_from_deg=data.get("wind_from_deg", 0.0),
            wind_speed_kmh=data.get("wind_speed_kmh", 0.0),
        )


@dataclass
class Fire:
    """An active wildfire that produces smoke."""

    name: str
    latitude: float
    longitude: float
    area_hectares: float
    containment_percent: float = 0.0

    def __post_init__(self) -> None:
        self.name = _name(self.name, "Fire name")
        self.latitude = _number(self.latitude, "latitude", -90, 90)
        self.longitude = _number(self.longitude, "longitude", -180, 180)
        self.area_hectares = _number(self.area_hectares, "area_hectares", 0)
        self.containment_percent = _number(
            self.containment_percent, "containment_percent", 0, 100
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "Fire":
        data = _check_dict(data, "Fire")
        return cls(
            name=_require(data, "name"),
            latitude=_require(data, "latitude"),
            longitude=_require(data, "longitude"),
            area_hectares=_require(data, "area_hectares"),
            containment_percent=data.get("containment_percent", 0.0),
        )


@dataclass
class Reading:
    """A measurement from an air quality sensor in a city.

    Units: ``pm25`` and ``pm10`` in micrograms per cubic metre (ug/m3),
    ``co_ppm`` in parts per million. At least one pollutant is required.
    """

    city: str
    pm25: Optional[float] = None
    pm10: Optional[float] = None
    co_ppm: Optional[float] = None
    timestamp: str = ""

    def __post_init__(self) -> None:
        self.city = _name(self.city, "Reading city")
        self.pm25 = _optional_number(self.pm25, "pm25")
        self.pm10 = _optional_number(self.pm10, "pm10")
        self.co_ppm = _optional_number(self.co_ppm, "co_ppm")
        if self.pm25 is None and self.pm10 is None and self.co_ppm is None:
            raise ValidationError("A reading needs at least one of pm25, pm10 or co_ppm")
        moment = utc_now() if not self.timestamp else parse_timestamp(self.timestamp)
        self.timestamp = to_iso(moment)

    @property
    def time(self) -> datetime:
        return parse_timestamp(self.timestamp)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> "Reading":
        data = _check_dict(data, "Reading")
        return cls(
            city=_require(data, "city"),
            pm25=data.get("pm25"),
            pm10=data.get("pm10"),
            co_ppm=data.get("co_ppm"),
            timestamp=data.get("timestamp", ""),
        )
