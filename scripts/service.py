"""Main logic: turn stored data into a pollution level for every city."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from .aqi import POLLUTANT_LABELS, category_for_aqi, overall_aqi
from .estimator import BACKGROUND_PM25, estimate_pm10, estimate_pm25
from .models import City, Fire, Reading, utc_now
from .storage import Database, JsonStorage

DEFAULT_MAX_AGE_HOURS = 24.0

SOURCE_MEASURED = "measured"
SOURCE_ESTIMATED = "estimated"
SOURCE_MIXED = "measured+estimated"


@dataclass
class CityAirQuality:
    """The result for one city."""

    city: str
    aqi: int
    level: str
    dominant_pollutant: str
    pm25: float
    pm10: float
    co_ppm: Optional[float]
    source: str
    advice: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def latest_reading(
    readings: Sequence[Reading],
    city_name: str,
    now: datetime,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
) -> Optional[Reading]:
    """Newest reading for a city that is not older than ``max_age_hours``.

    Readings with a timestamp in the future (clock errors) are ignored.
    """
    oldest_allowed = now - timedelta(hours=max_age_hours)
    candidates = [
        reading
        for reading in readings
        if reading.city.casefold() == city_name.casefold()
        and oldest_allowed <= reading.time <= now
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda reading: reading.time)


def assess_city(
    city: City,
    fires: Sequence[Fire],
    readings: Sequence[Reading],
    now: Optional[datetime] = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    background_pm25: float = BACKGROUND_PM25,
) -> CityAirQuality:
    """Work out the pollution level of one city.

    * Sensor values are always preferred when a recent reading exists.
    * Missing pollutants are filled in from the wildfire smoke estimate.
    """
    now = now or utc_now()
    reading = latest_reading(readings, city.name, now, max_age_hours)

    estimated_pm25: Optional[float] = None
    if reading is None or reading.pm25 is None:
        estimated_pm25 = estimate_pm25(city, fires, background_pm25)

    if reading is not None and reading.pm25 is not None:
        pm25 = reading.pm25
    else:
        pm25 = estimated_pm25 if estimated_pm25 is not None else background_pm25

    if reading is not None and reading.pm10 is not None:
        pm10 = reading.pm10
    else:
        pm10 = estimate_pm10(pm25)

    co_ppm = reading.co_ppm if reading is not None else None

    if reading is None:
        source = SOURCE_ESTIMATED
    elif reading.pm25 is not None and reading.pm10 is not None:
        source = SOURCE_MEASURED
    else:
        source = SOURCE_MIXED

    concentrations = {"pm25": pm25, "pm10": pm10, "co": co_ppm}
    aqi, dominant = overall_aqi(concentrations)
    category = category_for_aqi(aqi)

    return CityAirQuality(
        city=city.name,
        aqi=aqi,
        level=category.name,
        dominant_pollutant=POLLUTANT_LABELS[dominant],
        pm25=round(pm25, 1),
        pm10=round(pm10, 1),
        co_ppm=co_ppm,
        source=source,
        advice=category.advice,
    )


def assess_all(
    database: Database,
    now: Optional[datetime] = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    background_pm25: float = BACKGROUND_PM25,
) -> List[CityAirQuality]:
    """Pollution level of every city in the database, in database order."""
    now = now or utc_now()
    return [
        assess_city(
            city,
            database.fires,
            database.readings,
            now=now,
            max_age_hours=max_age_hours,
            background_pm25=background_pm25,
        )
        for city in database.cities
    ]


def get_pollution_levels(
    data_file: Union[str, Path],
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
) -> Dict[str, str]:
    """Convenience function: ``{"Los Angeles": "Unhealthy", ...}``.

    This is the "return the pollution level of each city" entry point for
    other programs that want to import this project.
    """
    database = JsonStorage(data_file).load()
    results = assess_all(database, max_age_hours=max_age_hours)
    return {result.city: result.level for result in results}
