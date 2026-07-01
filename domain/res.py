from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .models import ImpactPath


class AskResponse(BaseModel):
    answer: str
    sub_questions: list[dict[str, str]] = Field(default_factory=list)
    involved_types: dict[str, list[str]] = Field(default_factory=dict)
    retrieval: dict[str, Any] = Field(default_factory=dict)


class ImpactReport(BaseModel):
    answer: str = ""
    answer_source: str = "graph"
    llm_called: bool = False
    impact_subgraph: dict[str, Any] = Field(default_factory=dict)
    direct_impacts: list[str] = Field(default_factory=list)
    indirect_impacts: list[str] = Field(default_factory=list)
    target_impact: list[str] = Field(default_factory=list)
    scoped_impact: list[str] = Field(default_factory=list)
    evidence_paths: list[ImpactPath] = Field(default_factory=list)
