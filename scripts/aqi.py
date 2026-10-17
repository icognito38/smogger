"""Air Quality Index (AQI) calculation.

Uses the piecewise-linear formula published by the US EPA:

    AQI = (I_hi - I_lo) / (C_hi - C_lo) * (C - C_lo) + I_lo

where C is the (truncated) pollutant concentration and the breakpoints come
from the table below. The overall AQI of a city is the highest AQI of any
single pollutant, and that pollutant is called the "dominant" pollutant.

NOTE: breakpoint tables are revised from time to time by the EPA. They are
kept in one place (``BREAKPOINTS``) so they are easy to check and update.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Dict, List, Mapping, Tuple

# (concentration_low, concentration_high, aqi_low, aqi_high)
Breakpoint = Tuple[float, float, int, int]

BREAKPOINTS: Dict[str, List[Breakpoint]] = {
    # PM2.5, ug/m3 (24-hour)
    "pm25": [
        (0.0, 9.0, 0, 50),
        (9.1, 35.4, 51, 100),
        (35.5, 55.4, 101, 150),
        (55.5, 125.4, 151, 200),
        (125.5, 225.4, 201, 300),
        (225.5, 325.4, 301, 500),
    ],
    # PM10, ug/m3 (24-hour)
    "pm10": [
        (0, 54, 0, 50),
        (55, 154, 51, 100),
        (155, 254, 101, 150),
        (255, 354, 151, 200),
        (355, 424, 201, 300),
        (425, 604, 301, 500),
    ],
    # Carbon monoxide, ppm (8-hour)
    "co": [
        (0.0, 4.4, 0, 50),
        (4.5, 9.4, 51, 100),
        (9.5, 12.4, 101, 150),
        (12.5, 15.4, 151, 200),
        (15.5, 30.4, 201, 300),
        (30.5, 50.4, 301, 500),
    ],
}

# Number of decimals each pollutant is truncated to before the lookup.
TRUNCATE_DECIMALS: Dict[str, int] = {"pm25": 1, "pm10": 0, "co": 1}

POLLUTANT_LABELS: Dict[str, str] = {"pm25": "PM2.5", "pm10": "PM10", "co": "CO"}

MAX_AQI = 500


@dataclass(frozen=True)
class Category:
    """A named AQI band with health advice."""

    name: str
    low: int
    high: int
    advice: str


CATEGORIES: List[Category] = [
    Category("Good", 0, 50, "Air quality is satisfactory. No precautions needed."),
    Category(
        "Moderate",
        51,
        100,
        "Unusually sensitive people should consider reducing prolonged outdoor exertion.",
    ),
    Category(
        "Unhealthy for Sensitive Groups",
        101,
        150,
        "Children, older adults and people with asthma or heart/lung disease "
        "should limit time outdoors.",
    ),
    Category(
        "Unhealthy",
        151,
        200,
        "Everyone should reduce prolonged outdoor exertion. Keep windows closed.",
    ),
    Category(
        "Very Unhealthy",
        201,
        300,
        "Avoid outdoor activity. Wear an N95/FFP2 mask if you must go outside "
        "and use an air purifier indoors.",
    ),
    Category(
        "Hazardous",
        301,
        MAX_AQI,
        "Health emergency. Stay indoors with filtered air and follow local "
        "authority instructions.",
    ),
]


def truncate(value: float, decimals: int) -> float:
    """Truncate (not round) ``value`` to ``decimals`` places.

    ``Decimal`` is used to avoid binary floating point surprises such as
    ``0.29 * 100 == 28.999999999999996``.
    """
    quantum = Decimal(1).scaleb(-decimals)
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_DOWN))


def compute_aqi(pollutant: str, concentration: float) -> int:
    """Return the AQI sub-index (0-500) for one pollutant."""
    if pollutant not in BREAKPOINTS:
        raise ValueError(f"Unknown pollutant: {pollutant!r}")
    if concentration is None or math.isnan(concentration) or concentration < 0:
        raise ValueError(f"Concentration must be a non-negative number, got {concentration!r}")

    value = truncate(concentration, TRUNCATE_DECIMALS[pollutant])
    table = BREAKPOINTS[pollutant]

    # Anything above the top of the scale is capped at 500.
    if value > table[-1][1]:
        return MAX_AQI

    for c_low, c_high, i_low, i_high in table:
        if value <= c_high:
            fraction = (value - c_low) / (c_high - c_low)
            index = (i_high - i_low) * fraction + i_low
            return int(math.floor(index + 0.5))  # round half up

    return MAX_AQI  # pragma: no cover - unreachable, kept for safety


def overall_aqi(concentrations: Mapping[str, float]) -> Tuple[int, str]:
    """Return ``(aqi, dominant_pollutant)`` for a set of concentrations.

    Pollutants whose value is ``None`` are ignored. Ties are resolved in the
    order PM2.5, PM10, CO.
    """
    best_aqi = -1
    best_pollutant = ""
    for pollutant in ("pm25", "pm10", "co"):
        value = concentrations.get(pollutant)
        if value is None:
            continue
        index = compute_aqi(pollutant, value)
        if index > best_aqi:
            best_aqi, best_pollutant = index, pollutant
    if best_aqi < 0:
        raise ValueError("No pollutant concentrations were provided")
    return best_aqi, best_pollutant


def category_for_aqi(aqi: int) -> Category:
    """Return the AQI band that contains ``aqi``."""
    if aqi < 0:
        raise ValueError("AQI cannot be negative")
    for category in CATEGORIES:
        if aqi <= category.high:
            return category
    return CATEGORIES[-1]
