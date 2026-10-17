from pydantic import BaseModel, Field


class FireLocation(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    size_hectares: float = Field(gt=0)
    intensity: float = Field(gt=0, le=1)


class WeatherConditions(BaseModel):
    wind_speed_kmh: float = Field(ge=0)
    wind_direction_degrees: float = Field(ge=0, lt=360)
    temperature_c: float
    humidity_percent: float = Field(ge=0, le=100)


class PopulationLocation(BaseModel):
    name: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class SmokeForecastRequest(BaseModel):
    fire: FireLocation
    weather: WeatherConditions
    forecast_hours: int = Field(default=12, ge=1, le=72)
    time_step_hours: int = Field(default=1, ge=1, le=12)
    initial_width_km: float = Field(default=1, gt=0)
    dispersion_rate: float = Field(default=0.15, ge=0)
    decay_distance_km: float = Field(default=25, gt=0)
    locations: list[PopulationLocation] = Field(default_factory=list)


class ForecastPoint(BaseModel):
    hour: int
    latitude: float
    longitude: float
    distance_km: float
    plume_width_km: float
    estimated_pm25: float
    risk_level: str


class AffectedLocation(BaseModel):
    name: str
    latitude: float
    longitude: float
    distance_km: float
    bearing_degrees: float
    estimated_pm25: float
    risk_level: str


class GeoJSONFeature(BaseModel):
    type: str
    properties: dict
    geometry: dict


class GeoJSONFeatureCollection(BaseModel):
    type: str
    features: list[GeoJSONFeature]


class SmokeForecastResponse(BaseModel):
    fire_location: dict[str, float]
    smoke_direction_degrees: float
    forecast: list[ForecastPoint]
    affected_locations: list[AffectedLocation]
    geometry: GeoJSONFeatureCollection
    model_note: str
