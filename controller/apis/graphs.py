from __future__ import annotations

from fastapi import APIRouter, Depends

from controller.dependencies import get_graph_service
from domain.req import GraphPreviewRequest, ImportRequest, TextImportRequest
from service.graph_service import GraphService

router = APIRouter(prefix="/v1/graphs", tags=["graphs"])


@router.post("/preview")
def preview_graph(payload: GraphPreviewRequest, service: GraphService = Depends(get_graph_service)):
    return service.preview_graph(payload)


@router.post("/import")
def import_graph(payload: ImportRequest, service: GraphService = Depends(get_graph_service)):
    return service.import_graph(payload)


@router.post("/import-text")
def import_graph_text(payload: TextImportRequest, service: GraphService = Depends(get_graph_service)):
    return service.import_graph_text(payload)
