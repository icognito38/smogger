"""JSON storage for cities, fires and sensor readings.

All data lives in one JSON file with this layout::

    {
      "version": 1,
      "cities":   [ {...}, ... ],
      "fires":    [ {...}, ... ],
      "readings": [ {...}, ... ]
    }

Saving is atomic: data is written to a temporary file first and then moved
over the real file, so a crash in the middle of a save cannot corrupt it.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .models import City, Fire, Reading, ValidationError, to_iso, utc_now

SCHEMA_VERSION = 1
MAX_READINGS_PER_CITY = 50


class StorageError(Exception):
    """Raised when the data file cannot be read or written."""


@dataclass
class Database:
    """In-memory copy of everything stored in the JSON file."""

    cities: List[City] = field(default_factory=list)
    fires: List[Fire] = field(default_factory=list)
    readings: List[Reading] = field(default_factory=list)

    # ---- lookups ------------------------------------------------------- #
    def find_city(self, name: str) -> Optional[City]:
        wanted = name.strip().casefold()
        for city in self.cities:
            if city.name.casefold() == wanted:
                return city
        return None

    # ---- modifications (upsert by name) -------------------------------- #
    def upsert_city(self, city: City) -> bool:
        """Add or replace a city. Returns True if it replaced an existing one."""
        for index, existing in enumerate(self.cities):
            if existing.name.casefold() == city.name.casefold():
                self.cities[index] = city
                return True
        self.cities.append(city)
        return False

    def upsert_fire(self, fire: Fire) -> bool:
        for index, existing in enumerate(self.fires):
            if existing.name.casefold() == fire.name.casefold():
                self.fires[index] = fire
                return True
        self.fires.append(fire)
        return False

    def add_reading(self, reading: Reading) -> None:
        """Store a reading for a known city and trim old ones."""
        city = self.find_city(reading.city)
        if city is None:
            raise ValidationError(f"Unknown city: {reading.city!r}. Add it first.")
        reading.city = city.name  # use the stored spelling
        self.readings.append(reading)
        self._trim_readings(city.name)

    def _trim_readings(self, city_name: str) -> None:
        own = [r for r in self.readings if r.city.casefold() == city_name.casefold()]
        if len(own) <= MAX_READINGS_PER_CITY:
            return
        own.sort(key=lambda r: r.time)
        to_remove = {id(r) for r in own[:-MAX_READINGS_PER_CITY]}
        self.readings = [r for r in self.readings if id(r) not in to_remove]

    # ---- conversion ---------------------------------------------------- #
    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": SCHEMA_VERSION,
            "cities": [c.to_dict() for c in self.cities],
            "fires": [f.to_dict() for f in self.fires],
            "readings": [r.to_dict() for r in self.readings],
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Database":
        if not isinstance(data, dict):
            raise StorageError("The data file must contain a JSON object at the top level")
        try:
            return cls(
                cities=[City.from_dict(item) for item in _as_list(data, "cities")],
                fires=[Fire.from_dict(item) for item in _as_list(data, "fires")],
                readings=[Reading.from_dict(item) for item in _as_list(data, "readings")],
            )
        except ValidationError as exc:
            raise StorageError(f"Invalid data in file: {exc}") from exc


def _as_list(data: Dict[str, Any], key: str) -> List[Any]:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise StorageError(f"'{key}' must be a list")
    return value


class JsonStorage:
    """Reads and writes a :class:`Database` to a JSON file."""

    def __init__(self, path: Union[str, Path]) -> None:
        self.path = Path(path)

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> Database:
        if not self.exists():
            raise StorageError(
                f"Data file not found: {self.path}\n"
                "Create it with:  python main.py init"
            )
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except json.JSONDecodeError as exc:
            raise StorageError(f"{self.path} is not valid JSON: {exc}") from exc
        except OSError as exc:
            raise StorageError(f"Could not read {self.path}: {exc}") from exc
        return Database.from_dict(raw)

    def save(self, database: Database) -> None:
        payload = json.dumps(database.to_dict(), indent=2, ensure_ascii=False)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=str(self.path.parent),
                prefix=self.path.name + ".",
                suffix=".tmp",
                delete=False,
            )
            try:
                with handle:
                    handle.write(payload)
                    handle.write("\n")
                os.replace(handle.name, self.path)  # atomic, also works on Windows
            except BaseException:
                try:
                    os.unlink(handle.name)
                except OSError:
                    pass
                raise
        except OSError as exc:
            raise StorageError(f"Could not write {self.path}: {exc}") from exc


def sample_database() -> Database:
    """Example data: a fictional wildfire season in California."""
    now = to_iso(utc_now())
    return Database(
        cities=[
            City("Los Angeles", 34.0522, -118.2437, wind_from_deg=45, wind_speed_kmh=25),
            City("Santa Barbara", 34.4208, -119.6982, wind_from_deg=90, wind_speed_kmh=15),
            City("San Diego", 32.7157, -117.1611, wind_from_deg=270, wind_speed_kmh=12),
            City("Bakersfield", 35.3733, -119.0187, wind_from_deg=315, wind_speed_kmh=10),
            City("Fresno", 36.7378, -119.7871, wind_from_deg=300, wind_speed_kmh=8),
            City("Sacramento", 38.5816, -121.4944, wind_from_deg=200, wind_speed_kmh=14),
            City("San Francisco", 37.7749, -122.4194, wind_from_deg=270, wind_speed_kmh=20),
            City("Redding", 40.5865, -122.3917, wind_from_deg=0, wind_speed_kmh=18),
        ],
        fires=[
            Fire("Canyon Ridge Fire", 34.45, -118.55, area_hectares=12000, containment_percent=20),
            Fire("Northern Valley Fire", 40.80, -122.30, area_hectares=5000, containment_percent=40),
        ],
        readings=[
            Reading("Los Angeles", pm25=95.4, pm10=130.0, co_ppm=2.1, timestamp=now),
            Reading("Redding", pm25=60.2, pm10=82.0, timestamp=now),
            Reading("Sacramento", pm25=41.0, timestamp=now),
        ],
    )
