from app.models.smoke import (
    FireLocation,
    PopulationLocation,
    SmokeForecastRequest,
    WeatherConditions,
)
from app.services.smoke_dispersion import predict_smoke_dispersion


def make_request(**overrides) -> SmokeForecastRequest:
    values = {
        "fire": FireLocation(
            latitude=34.0522,
            longitude=-118.2437,
            size_hectares=120,
            intensity=0.8,
        ),
        "weather": WeatherConditions(
            wind_speed_kmh=25,
            wind_direction_degrees=315,
            temperature_c=32,
            humidity_percent=25,
        ),
        "forecast_hours": 12,
        "time_step_hours": 1,
        "locations": [],
    }
    values.update(overrides)
    return SmokeForecastRequest(**values)


def test_smoke_moves_downwind():
    result = predict_smoke_dispersion(make_request())

    assert result.smoke_direction_degrees == 135
    assert len(result.forecast) == 12
    assert result.forecast[0].distance_km == 25
    assert result.forecast[-1].distance_km == 300


def test_pm25_decreases_with_distance():
    result = predict_smoke_dispersion(make_request())

    assert result.forecast[0].estimated_pm25 > result.forecast[-1].estimated_pm25


def test_downwind_location_is_flagged():
    result = predict_smoke_dispersion(
        make_request(
            locations=[
                PopulationLocation(
                    name="Downwind town",
                    latitude=33.9,
                    longitude=-118.05,
                ),
                PopulationLocation(
                    name="Far town",
                    latitude=36.0,
                    longitude=-118.0,
                ),
            ]
        )
    )

    assert [location.name for location in result.affected_locations] == [
        "Downwind town"
    ]


def test_geojson_plume_is_a_closed_polygon():
    result = predict_smoke_dispersion(make_request())
    geometry = result.geometry.features[0].geometry

    assert geometry["type"] == "Polygon"
    assert geometry["coordinates"][0][0] == geometry["coordinates"][0][-1]
