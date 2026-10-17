from app.models.smoke import (
    CitySmokeImpact,
    SmokeImpactRequest,
    SmokeImpactResponse,
)

MODEL_NOTE = (
    "Estimated smoke-impact scores based on the supplied city trajectory. "
    "They are not official air-quality measurements or emergency warnings."
)


def _risk_level(risk_score_percent: float) -> str:
    if risk_score_percent >= 90:
        return "hazardous"
    if risk_score_percent >= 70:
        return "unhealthy"
    if risk_score_percent >= 50:
        return "unhealthy_for_sensitive_groups"
    if risk_score_percent >= 25:
        return "moderate"
    return "good"


def _health_advisory(risk_level: str) -> str:
    advisories = {
        "good": "No special precautions are suggested based on this estimate.",
        "moderate": "Sensitive groups should consider reducing prolonged outdoor activity.",
        "unhealthy_for_sensitive_groups": (
            "Sensitive groups should reduce prolonged outdoor activity and monitor local air quality."
        ),
        "unhealthy": (
            "Everyone should reduce prolonged outdoor activity; sensitive groups should avoid it."
        ),
        "hazardous": (
            "Avoid outdoor activity, keep windows closed, and follow official emergency guidance."
        ),
    }
    return advisories[risk_level]


def _impact_score(predicted_pm25: float, path_probability: float) -> float:
    """Convert the teammate model's PM2.5 forecast into a 0-100 score."""
    # 150 ug/m3 is used as the upper reference point for the presentation
    # score. The PM2.5 forecast itself is never recalculated here.
    concentration_factor = min(1.0, predicted_pm25 / 150)
    return concentration_factor * path_probability * 100


def assess_smoke_impact(request: SmokeImpactRequest) -> SmokeImpactResponse:
    """Score cities from a trajectory supplied by the prediction branch."""
    impacts = []
    for city in request.cities:
        risk_score = round(
            _impact_score(city.predicted_pm25_6h, city.path_probability), 2
        )
        risk_level = _risk_level(risk_score)
        confidence = round(city.path_probability * 100, 2)
        impacts.append(
            CitySmokeImpact(
                name=city.name,
                latitude=city.latitude,
                longitude=city.longitude,
                arrival_hour=city.arrival_hour,
                estimated_pm25=city.predicted_pm25_6h,
                risk_score_percent=risk_score,
                risk_level=risk_level,
                confidence_percent=confidence,
                exposure_duration_hours=max(
                    1, request.forecast_hours - city.arrival_hour
                ),
                health_advisory=_health_advisory(risk_level),
            )
        )

    return SmokeImpactResponse(cities=impacts, model_note=MODEL_NOTE)
