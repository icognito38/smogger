from app.models.smoke import (
    FireContext,
    PredictedCity,
    SmokeImpactRequest,
)
from app.services.smoke_dispersion import assess_smoke_impact


def make_request() -> SmokeImpactRequest:
    return SmokeImpactRequest(
        fire=FireContext(size_hectares=120, intensity=0.8),
        cities=[
            PredictedCity(
                name="City A",
                latitude=34.2,
                longitude=-118.1,
                arrival_hour=2,
                distance_from_fire_km=24,
                path_probability=0.72,
                Predicted_PM25_6h=42.8,
            )
        ],
    )


def test_returns_percentage_risk_without_recalculating_trajectory():
    result = assess_smoke_impact(make_request())

    city = result.cities[0]
    assert 0 <= city.risk_score_percent <= 100
    assert city.confidence_percent == 72
    assert city.arrival_hour == 2
    assert city.name == "City A"
    assert city.estimated_pm25 == 42.8
    assert city.risk_score_percent == round((42.8 / 150) * 0.72 * 100, 2)


def test_larger_distance_reduces_impact():
    request = make_request()
    request.cities.append(
        PredictedCity(
            name="Far city",
            latitude=35,
            longitude=-118,
            arrival_hour=5,
            distance_from_fire_km=200,
            path_probability=0.72,
            Predicted_PM25_6h=10,
        )
    )

    result = assess_smoke_impact(request)

    assert result.cities[0].risk_score_percent > result.cities[1].risk_score_percent


def test_endpoint_contract_has_only_city_impacts():
    result = assess_smoke_impact(make_request()).model_dump()

    assert set(result) == {"cities", "model_note"}
    assert "geometry" not in result
    assert "forecast" not in result


def test_cities_are_ranked_by_risk_score_descending():
    request = make_request()
    request.cities.extend(
        [
            PredictedCity(
                name="Highest risk",
                latitude=35,
                longitude=-118,
                arrival_hour=3,
                distance_from_fire_km=50,
                path_probability=1,
                Predicted_PM25_6h=150,
            ),
            PredictedCity(
                name="Lowest risk",
                latitude=36,
                longitude=-118,
                arrival_hour=5,
                distance_from_fire_km=200,
                path_probability=0.5,
                Predicted_PM25_6h=10,
            ),
        ]
    )

    result = assess_smoke_impact(request)

    assert [city.name for city in result.cities] == [
        "Highest risk",
        "City A",
        "Lowest risk",
    ]
    assert [city.rank for city in result.cities] == [1, 2, 3]
    assert [city.model_dump()["rank"] for city in result.cities] == [1, 2, 3]


def test_accepts_notebook_field_names_and_converts_miles():
    request = SmokeImpactRequest(
        cities=[
            PredictedCity(
                name="Montreal",
                latitude=45.5016,
                longitude=-73.5672,
                arrival_hour=6,
                distance_from_fire_miles=100,
                Predicted_PM25_6h=35,
            )
        ]
    )

    city = assess_smoke_impact(request).cities[0]

    assert city.estimated_pm25 == 35
    assert city.risk_score_percent == round((35 / 150) * 100, 2)
