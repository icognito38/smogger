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
        )
    )

    result = assess_smoke_impact(request)

    assert result.cities[0].risk_score_percent > result.cities[1].risk_score_percent


def test_endpoint_contract_has_only_city_impacts():
    result = assess_smoke_impact(make_request()).model_dump()

    assert set(result) == {"cities", "model_note"}
    assert "geometry" not in result
    assert "forecast" not in result
