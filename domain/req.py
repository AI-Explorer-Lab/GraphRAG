from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .models import ChangeSpecModel


class ImportRequest(BaseModel):
    graph_id: str
    graph_json: dict[str, Any]


class GraphPreviewRequest(BaseModel):
    graph_json: dict[str, Any]


class TextImportRequest(BaseModel):
    graph_id: str
    text: str = Field(min_length=1)
    schema_hint: Optional[str] = None
    fallback_graph_json: Optional[dict[str, Any]] = None
    prefer_fallback_graph_json: bool = False


class AskRequest(BaseModel):
    graph_id: str
    question: str
    top_k: int = Field(default=8, ge=1, le=50)
    mode: Literal["agent", "noagent"] = "agent"
    max_steps: int = Field(default=4, ge=1, le=10)


class ImpactRequest(BaseModel):
    graph_id: str
    change_spec: ChangeSpecModel
    target_node_id: Optional[str] = None
