"""Command-line interface for the wildfire smog air quality app.

Examples (Windows PowerShell / VS Code terminal)::

    python main.py init
    python main.py report
    python main.py report --city "Los Angeles"
    python main.py report --sort aqi --json
    python main.py add-city Oakland 37.8044 -122.2712 --wind-from 270 --wind-speed 18
    python main.py add-fire "Pine Fire" 37.9 -122.0 5000 --containment 10
    python main.py add-reading Oakland --pm25 55.2 --pm10 70
    python main.py list
    python main.py export results.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from .models import City, Fire, Reading, ValidationError
from .service import DEFAULT_MAX_AGE_HOURS, CityAirQuality, assess_all
from .storage import JsonStorage, StorageError, sample_database

DEFAULT_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "smog_data.json"


# --------------------------------------------------------------------------- #
# Output helpers
# --------------------------------------------------------------------------- #
def format_table(results: Sequence[CityAirQuality]) -> str:
    """Return a plain-text table (no colours, works in any Windows terminal)."""
    headers = ["City", "AQI", "Level", "Main pollutant", "PM2.5", "PM10", "Source"]
    rows = [
        [
            r.city,
            str(r.aqi),
            r.level,
            r.dominant_pollutant,
            f"{r.pm25:.1f}",
            f"{r.pm10:.1f}",
            r.source,
        ]
        for r in results
    ]
    widths = [len(h) for h in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def line(cells: Sequence[str]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells)).rstrip()

    separator = "  ".join("-" * w for w in widths)
    return "\n".join([line(headers), separator] + [line(row) for row in rows])


def print_city_details(result: CityAirQuality) -> None:
    print(f"City:              {result.city}")
    print(f"AQI:               {result.aqi}")
    print(f"Pollution level:   {result.level}")
    print(f"Main pollutant:    {result.dominant_pollutant}")
    print(f"PM2.5:             {result.pm25:.1f} ug/m3")
    print(f"PM10:              {result.pm10:.1f} ug/m3")
    co_text = "n/a" if result.co_ppm is None else f"{result.co_ppm:.1f} ppm"
    print(f"CO:                {co_text}")
    print(f"Data source:       {result.source}")
    print(f"Advice:            {result.advice}")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_init(args: argparse.Namespace, storage: JsonStorage) -> int:
    if storage.exists() and not args.force:
        print(f"{storage.path} already exists. Use --force to overwrite it.")
        return 1
    storage.save(sample_database())
    print(f"Created sample data file: {storage.path}")
    return 0


def cmd_report(args: argparse.Namespace, storage: JsonStorage) -> int:
    database = storage.load()
    if not database.cities:
        print("No cities stored yet. Add one with: python main.py add-city ...")
        return 1

    results = assess_all(database, max_age_hours=args.max_age_hours)

    if args.city:
        wanted = args.city.strip().casefold()
        results = [r for r in results if r.city.casefold() == wanted]
        if not results:
            print(f"City not found: {args.city!r}")
            return 1

    if args.sort == "aqi":
        results = sorted(results, key=lambda r: (-r.aqi, r.city))
    elif args.sort == "name":
        results = sorted(results, key=lambda r: r.city.casefold())

    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False))
        return 0

    print(format_table(results))
    if len(results) == 1:
        print()
        print_city_details(results[0])
    else:
        worst = max(results, key=lambda r: r.aqi)
        print()
        print(f"Most polluted city: {worst.city} (AQI {worst.aqi}, {worst.level})")
        print(f"Advice: {worst.advice}")
    return 0


def cmd_add_city(args: argparse.Namespace, storage: JsonStorage) -> int:
    database = storage.load()
    city = City(
        name=args.name,
        latitude=args.latitude,
        longitude=args.longitude,
        wind_from_deg=args.wind_from,
        wind_speed_kmh=args.wind_speed,
    )
    replaced = database.upsert_city(city)
    storage.save(database)
    print(f"{'Updated' if replaced else 'Added'} city: {city.name}")
    return 0


def cmd_add_fire(args: argparse.Namespace, storage: JsonStorage) -> int:
    database = storage.load()
    fire = Fire(
        name=args.name,
        latitude=args.latitude,
        longitude=args.longitude,
        area_hectares=args.area,
        containment_percent=args.containment,
    )
    replaced = database.upsert_fire(fire)
    storage.save(database)
    print(f"{'Updated' if replaced else 'Added'} fire: {fire.name}")
    return 0


def cmd_add_reading(args: argparse.Namespace, storage: JsonStorage) -> int:
    database = storage.load()
    reading = Reading(
        city=args.city,
        pm25=args.pm25,
        pm10=args.pm10,
        co_ppm=args.co,
        timestamp=args.time or "",
    )
    database.add_reading(reading)
    storage.save(database)
    print(f"Stored reading for {reading.city} at {reading.timestamp}")
    return 0


def cmd_list(args: argparse.Namespace, storage: JsonStorage) -> int:
    database = storage.load()
    print(f"Cities ({len(database.cities)}):")
    for city in database.cities:
        print(
            f"  {city.name:<16} lat {city.latitude:>8.4f}  lon {city.longitude:>9.4f}  "
            f"wind from {city.wind_from_deg:>5.1f} deg at {city.wind_speed_kmh:.1f} km/h"
        )
    print(f"\nFires ({len(database.fires)}):")
    for fire in database.fires:
        print(
            f"  {fire.name:<22} lat {fire.latitude:>8.4f}  lon {fire.longitude:>9.4f}  "
            f"{fire.area_hectares:,.0f} ha, {fire.containment_percent:.0f}% contained"
        )
    print(f"\nReadings stored: {len(database.readings)}")
    return 0


def cmd_export(args: argparse.Namespace, storage: JsonStorage) -> int:
    database = storage.load()
    results = assess_all(database, max_age_hours=args.max_age_hours)
    output = Path(args.output)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as handle:
            json.dump([r.to_dict() for r in results], handle, indent=2, ensure_ascii=False)
            handle.write("\n")
    except OSError as exc:
        raise StorageError(f"Could not write {output}: {exc}") from exc
    print(f"Exported {len(results)} cities to {output}")
    return 0


# --------------------------------------------------------------------------- #
# Argument parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Estimate post-wildfire smog levels (AQI) for each city.",
    )
    parser.add_argument(
        "--data",
        default=str(DEFAULT_DATA_FILE),
        help="path to the JSON data file (default: data/smog_data.json)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create a sample data file")
    p.add_argument("--force", action="store_true", help="overwrite an existing file")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("report", help="show the pollution level of each city")
    p.add_argument("--city", help="show only this city (with details)")
    p.add_argument("--sort", choices=["none", "aqi", "name"], default="aqi")
    p.add_argument("--json", action="store_true", help="print results as JSON")
    p.add_argument(
        "--max-age-hours",
        type=float,
        default=DEFAULT_MAX_AGE_HOURS,
        help="ignore sensor readings older than this (default: %(default)s)",
    )
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("add-city", help="add or update a city")
    p.add_argument("name")
    p.add_argument("latitude", type=float)
    p.add_argument("longitude", type=float)
    p.add_argument("--wind-from", type=float, default=0.0, help="degrees the wind blows FROM")
    p.add_argument("--wind-speed", type=float, default=0.0, help="wind speed in km/h")
    p.set_defaults(func=cmd_add_city)

    p = sub.add_parser("add-fire", help="add or update a wildfire")
    p.add_argument("name")
    p.add_argument("latitude", type=float)
    p.add_argument("longitude", type=float)
    p.add_argument("area", type=float, help="burned area in hectares")
    p.add_argument("--containment", type=float, default=0.0, help="percent contained (0-100)")
    p.set_defaults(func=cmd_add_fire)

    p = sub.add_parser("add-reading", help="store a sensor reading for a city")
    p.add_argument("city")
    p.add_argument("--pm25", type=float, help="PM2.5 in ug/m3")
    p.add_argument("--pm10", type=float, help="PM10 in ug/m3")
    p.add_argument("--co", type=float, help="carbon monoxide in ppm")
    p.add_argument("--time", help="ISO timestamp, e.g. 2026-10-17T12:00:00Z (default: now)")
    p.set_defaults(func=cmd_add_reading)

    p = sub.add_parser("list", help="list stored cities, fires and reading count")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("export", help="write all city results to a JSON file")
    p.add_argument("output", help="output file, e.g. results.json")
    p.add_argument("--max-age-hours", type=float, default=DEFAULT_MAX_AGE_HOURS)
    p.set_defaults(func=cmd_export)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    storage = JsonStorage(args.data)
    try:
        return args.func(args, storage)
    except (ValidationError, StorageError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
