from fastapi import APIRouter

from app.models.smoke import SmokeImpactRequest, SmokeImpactResponse
from app.services.smoke_dispersion import assess_smoke_impact

router = APIRouter(prefix="/smoke", tags=["smoke impact"])


@router.post("/impact", response_model=SmokeImpactResponse)
def assess_impact(request: SmokeImpactRequest) -> SmokeImpactResponse:
    return assess_smoke_impact(request)
