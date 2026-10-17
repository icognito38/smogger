import math

from app.models.smoke import (
    AffectedLocation,
    ForecastPoint,
    GeoJSONFeature,
    GeoJSONFeatureCollection,
    SmokeForecastRequest,
    SmokeForecastResponse,
)

EARTH_RADIUS_KM = 6371.0088
MODEL_NOTE = (
    "Approximate smoke trajectory for decision support; not an official "
    "emergency or air-quality forecast."
)


def _normalise_bearing(degrees: float) -> float:
    return degrees % 360


def _destination(
    latitude: float, longitude: float, bearing_degrees: float, distance_km: float
) -> tuple[float, float]:
    """Return a destination coordinate using the great-circle formula."""
    latitude_radians = math.radians(latitude)
    longitude_radians = math.radians(longitude)
    bearing_radians = math.radians(bearing_degrees)
    angular_distance = distance_km / EARTH_RADIUS_KM

    destination_latitude = math.asin(
        math.sin(latitude_radians) * math.cos(angular_distance)
        + math.cos(latitude_radians)
        * math.sin(angular_distance)
        * math.cos(bearing_radians)
    )
    destination_longitude = longitude_radians + math.atan2(
        math.sin(bearing_radians)
        * math.sin(angular_distance)
        * math.cos(latitude_radians),
        math.cos(angular_distance)
        - math.sin(latitude_radians) * math.sin(destination_latitude),
    )

    return (
        math.degrees(destination_latitude),
        ((math.degrees(destination_longitude) + 540) % 360) - 180,
    )


def _distance_and_bearing(
    origin_latitude: float,
    origin_longitude: float,
    destination_latitude: float,
    destination_longitude: float,
) -> tuple[float, float]:
    """Return great-circle distance and initial bearing between coordinates."""
    origin_latitude_radians = math.radians(origin_latitude)
    destination_latitude_radians = math.radians(destination_latitude)
    latitude_delta = destination_latitude_radians - origin_latitude_radians
    longitude_delta = math.radians(destination_longitude - origin_longitude)

    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(origin_latitude_radians)
        * math.cos(destination_latitude_radians)
        * math.sin(longitude_delta / 2) ** 2
    )
    distance_km = EARTH_RADIUS_KM * 2 * math.atan2(
        math.sqrt(haversine), math.sqrt(1 - haversine)
    )

    bearing = math.degrees(
        math.atan2(
            math.sin(longitude_delta) * math.cos(destination_latitude_radians),
            math.cos(origin_latitude_radians) * math.sin(destination_latitude_radians)
            - math.sin(origin_latitude_radians)
            * math.cos(destination_latitude_radians)
            * math.cos(longitude_delta),
        )
    )
    return distance_km, _normalise_bearing(bearing)


def _angular_difference(first: float, second: float) -> float:
    return abs((first - second + 180) % 360 - 180)


def _risk_level(estimated_pm25: float) -> str:
    if estimated_pm25 >= 150:
        return "hazardous"
    if estimated_pm25 >= 55.5:
        return "unhealthy"
    if estimated_pm25 >= 35.5:
        return "unhealthy_for_sensitive_groups"
    if estimated_pm25 >= 12.1:
        return "moderate"
    return "good"


def _estimate_pm25(request: SmokeForecastRequest, distance_km: float) -> float:
    fire = request.fire
    base_emission = fire.size_hectares * fire.intensity
    return round(
        base_emission * 100 * math.exp(-distance_km / request.decay_distance_km),
        2,
    )


def _plume_feature(
    request: SmokeForecastRequest, smoke_direction: float, max_distance_km: float
) -> GeoJSONFeature:
    fire = request.fire
    half_width_km = (
        request.initial_width_km + request.dispersion_rate * max_distance_km
    ) / 2
    left = _destination(
        fire.latitude,
        fire.longitude,
        smoke_direction - 90,
        half_width_km,
    )
    right = _destination(
        fire.latitude,
        fire.longitude,
        smoke_direction + 90,
        half_width_km,
    )
    end_left = _destination(
        *_destination(
            fire.latitude, fire.longitude, smoke_direction, max_distance_km
        ),
        smoke_direction - 90,
        half_width_km,
    )
    end_right = _destination(
        *_destination(
            fire.latitude, fire.longitude, smoke_direction, max_distance_km
        ),
        smoke_direction + 90,
        half_width_km,
    )

    coordinates = [
        [
            [left[1], left[0]],
            [end_left[1], end_left[0]],
            [end_right[1], end_right[0]],
            [right[1], right[0]],
            [left[1], left[0]],
        ]
    ]
    return GeoJSONFeature(
        type="Feature",
        properties={"kind": "estimated_smoke_plume"},
        geometry={"type": "Polygon", "coordinates": coordinates},
    )


def predict_smoke_dispersion(
    request: SmokeForecastRequest,
) -> SmokeForecastResponse:
    """Estimate downwind smoke trajectory and relative PM2.5 impact."""
    smoke_direction = _normalise_bearing(
        request.weather.wind_direction_degrees + 180
    )
    max_distance_km = request.weather.wind_speed_kmh * request.forecast_hours
    forecast = []

    for hour in range(
        request.time_step_hours,
        request.forecast_hours + 1,
        request.time_step_hours,
    ):
        distance_km = request.weather.wind_speed_kmh * hour
        latitude, longitude = _destination(
            request.fire.latitude,
            request.fire.longitude,
            smoke_direction,
            distance_km,
        )
        plume_width_km = (
            request.initial_width_km + request.dispersion_rate * distance_km
        )
        estimated_pm25 = _estimate_pm25(request, distance_km)
        forecast.append(
            ForecastPoint(
                hour=hour,
                latitude=round(latitude, 6),
                longitude=round(longitude, 6),
                distance_km=round(distance_km, 2),
                plume_width_km=round(plume_width_km, 2),
                estimated_pm25=estimated_pm25,
                risk_level=_risk_level(estimated_pm25),
            )
        )

    affected_locations = []
    max_half_width = (
        request.initial_width_km + request.dispersion_rate * max_distance_km
    ) / 2
    for location in request.locations:
        distance_km, bearing = _distance_and_bearing(
            request.fire.latitude,
            request.fire.longitude,
            location.latitude,
            location.longitude,
        )
        if distance_km > max_distance_km:
            continue
        cross_track_distance = distance_km * math.sin(
            math.radians(_angular_difference(bearing, smoke_direction))
        )
        if abs(cross_track_distance) > max_half_width:
            continue
        estimated_pm25 = _estimate_pm25(request, distance_km)
        affected_locations.append(
            AffectedLocation(
                name=location.name,
                latitude=location.latitude,
                longitude=location.longitude,
                distance_km=round(distance_km, 2),
                bearing_degrees=round(bearing, 2),
                estimated_pm25=estimated_pm25,
                risk_level=_risk_level(estimated_pm25),
            )
        )

    return SmokeForecastResponse(
        fire_location={
            "latitude": request.fire.latitude,
            "longitude": request.fire.longitude,
        },
        smoke_direction_degrees=round(smoke_direction, 2),
        forecast=forecast,
        affected_locations=affected_locations,
        geometry=GeoJSONFeatureCollection(
            type="FeatureCollection",
            features=[
                _plume_feature(request, smoke_direction, max_distance_km)
            ],
        ),
        model_note=MODEL_NOTE,
    )
