from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .impact_models import ChangeSpecModel


class ImportRequest(BaseModel):
    graph_id: str
    lineage_json: dict[str, Any]


class LineagePreviewRequest(BaseModel):
    lineage_json: dict[str, Any]


class TextImportRequest(BaseModel):
    graph_id: str
    text: str = Field(min_length=1)
    schema_hint: Optional[str] = None
    fallback_lineage_json: Optional[dict[str, Any]] = None
    prefer_fallback_lineage_json: bool = False


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


class AskResponse(BaseModel):
    answer: str
    sub_questions: list[dict[str, str]] = Field(default_factory=list)
    involved_types: dict[str, list[str]] = Field(default_factory=dict)
    retrieval: dict[str, Any] = Field(default_factory=dict)
