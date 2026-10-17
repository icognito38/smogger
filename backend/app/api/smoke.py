from fastapi import APIRouter

from app.models.smoke import SmokeForecastRequest, SmokeForecastResponse
from app.services.smoke_dispersion import predict_smoke_dispersion

router = APIRouter(prefix="/smoke", tags=["smoke"])


@router.post("/forecast", response_model=SmokeForecastResponse)
def forecast_smoke(request: SmokeForecastRequest) -> SmokeForecastResponse:
    return predict_smoke_dispersion(request)
