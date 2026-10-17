from pydantic import BaseModel, Field


class FireContext(BaseModel):
    size_hectares: float = Field(gt=0)
    intensity: float = Field(gt=0, le=1)


class PredictedCity(BaseModel):
    name: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    arrival_hour: int = Field(ge=0, le=6)
    distance_from_fire_km: float = Field(ge=0)
    path_probability: float = Field(ge=0, le=1, default=1)


class SmokeImpactRequest(BaseModel):
    fire: FireContext
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
