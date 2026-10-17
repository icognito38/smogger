from pydantic import BaseModel, Field, model_validator


class FireContext(BaseModel):
    """Optional context identifying the fire used by the prediction model."""

    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)


class PredictedCity(BaseModel):
    name: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    arrival_hour: int = Field(ge=0, le=6)
    distance_from_fire_km: float | None = Field(default=None, ge=0)
    distance_from_fire_miles: float | None = Field(default=None, ge=0)
    path_probability: float = Field(ge=0, le=1, default=1)
    predicted_pm25_6h: float = Field(alias="Predicted_PM25_6h", ge=0)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_distance(self) -> "PredictedCity":
        if self.distance_from_fire_km is None and self.distance_from_fire_miles is None:
            raise ValueError(
                "Provide distance_from_fire_km or distance_from_fire_miles"
            )
        if self.distance_from_fire_km is None:
            self.distance_from_fire_km = self.distance_from_fire_miles * 1.609344
        return self


class SmokeImpactRequest(BaseModel):
    fire: FireContext | None = None
    cities: list[PredictedCity] = Field(min_length=1)
    forecast_hours: int = Field(default=6, ge=1, le=6)


class CitySmokeImpact(BaseModel):
    name: str
    latitude: float
    longitude: float
    arrival_hour: int
    estimated_pm25: float
    risk_score_percent: float = Field(ge=0, le=100)
    risk_level: str
    confidence_percent: float = Field(ge=0, le=100)
    exposure_duration_hours: int
    health_advisory: str


class SmokeImpactResponse(BaseModel):
    cities: list[CitySmokeImpact]
    model_note: str
