"""Estimate smoke pollution in a city from nearby wildfires.

This is a simple, explainable heuristic model -- NOT a replacement for real
atmospheric dispersion models or official monitoring. It is meant for cities
that have no (recent) sensor data.

For every fire we compute a smoke contribution to the city's PM2.5:

    contribution = peak(fire) * exp(-distance / decay) * wind_factor

* peak(fire)   - PM2.5 right next to the fire. Grows with the square root of
                 the burned area and shrinks as containment increases.
* decay        - distance scale in km. Stronger wind carries smoke further.
* wind_factor  - 1.0 when the wind blows the smoke straight at the city,
                 small when the wind blows it away. With almost no wind the
                 smoke spreads in all directions, so direction matters less.

The city's estimated PM2.5 is the background level plus all contributions.
"""

from __future__ import annotations

import math
from typing import Iterable

from .models import City, Fire

EARTH_RADIUS_KM = 6371.0088

BACKGROUND_PM25 = 8.0           # ug/m3 with no fires around
EMISSION_COEFFICIENT = 8.0      # peak = coefficient * sqrt(hectares)
MAX_PEAK_PM25 = 600.0           # cap for the peak next to one fire
MAX_CONTAINMENT_REDUCTION = 0.7  # a 100% contained fire still emits 30%
BASE_DECAY_KM = 60.0            # decay distance with no wind
WIND_DECAY_KM_PER_KMH = 1.5     # extra decay distance per km/h of wind
FULL_DIRECTIONAL_WIND_KMH = 15.0  # at/above this speed wind direction fully applies
MIN_DIRECTION_FACTOR = 0.05     # smoke never drops to exactly zero upwind
MAX_ESTIMATED_PM25 = 1000.0
PM10_TO_PM25_RATIO = 1.3        # smoke is mostly fine particles


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    a = min(1.0, max(0.0, a))  # guard against tiny floating point overshoot
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial compass bearing (0-360, 0 = north) from point 1 to point 2."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_lambda = math.radians(lon2 - lon1)
    x = math.sin(d_lambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def angle_difference_deg(a: float, b: float) -> float:
    """Smallest absolute difference between two compass angles (0-180)."""
    diff = abs(a - b) % 360.0
    return 360.0 - diff if diff > 180.0 else diff


def fire_peak_pm25(fire: Fire) -> float:
    """PM2.5 (ug/m3) right next to the fire."""
    peak = min(MAX_PEAK_PM25, EMISSION_COEFFICIENT * math.sqrt(fire.area_hectares))
    reduction = MAX_CONTAINMENT_REDUCTION * (fire.containment_percent / 100.0)
    return peak * (1.0 - reduction)


def wind_direction_factor(fire: Fire, city: City, distance_km: float) -> float:
    """How strongly the wind pushes this fire's smoke towards the city (0-1)."""
    if distance_km < 0.01:  # fire is (practically) inside the city
        return 1.0

    # ``wind_from_deg`` is where the wind comes FROM, smoke travels the opposite way.
    smoke_travel_deg = (city.wind_from_deg + 180.0) % 360.0
    fire_to_city = bearing_deg(fire.latitude, fire.longitude, city.latitude, city.longitude)
    alignment = math.cos(math.radians(angle_difference_deg(smoke_travel_deg, fire_to_city)))

    directional = 0.5 + 0.5 * alignment            # 1 = downwind, 0 = upwind
    weight = min(1.0, city.wind_speed_kmh / FULL_DIRECTIONAL_WIND_KMH)
    factor = 1.0 - weight * (1.0 - directional)    # calm wind -> factor near 1
    return max(MIN_DIRECTION_FACTOR, factor)


def smoke_contribution(fire: Fire, city: City) -> float:
    """PM2.5 (ug/m3) that one fire adds to one city."""
    distance = haversine_km(fire.latitude, fire.longitude, city.latitude, city.longitude)
    decay_km = BASE_DECAY_KM + WIND_DECAY_KM_PER_KMH * city.wind_speed_kmh
    attenuation = math.exp(-distance / decay_km)
    return fire_peak_pm25(fire) * attenuation * wind_direction_factor(fire, city, distance)


def estimate_pm25(
    city: City,
    fires: Iterable[Fire],
    background: float = BACKGROUND_PM25,
) -> float:
    """Estimated PM2.5 (ug/m3) for a city from all known fires."""
    if background < 0:
        raise ValueError("background must be non-negative")
    total = background + sum(smoke_contribution(fire, city) for fire in fires)
    return round(min(total, MAX_ESTIMATED_PM25), 1)


def estimate_pm10(pm25: float) -> float:
    """Rough PM10 estimate (ug/m3) derived from PM2.5."""
    return round(pm25 * PM10_TO_PM25_RATIO, 1)
