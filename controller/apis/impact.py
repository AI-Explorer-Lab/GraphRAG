from __future__ import annotations

from fastapi import APIRouter, Depends

from controller.dependencies import get_impact_service
from domain.req import ImpactRequest
from service.impact_service import ImpactService

router = APIRouter(tags=["impact"])


@router.post("/v1/impact/what-if")
def what_if_impact(payload: ImpactRequest, service: ImpactService = Depends(get_impact_service)):
    return service.what_if_impact(payload)
