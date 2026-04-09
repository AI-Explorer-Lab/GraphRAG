from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChangeSpecModel(BaseModel):
    source: str
    target: str
    relation: str = "transitions"
    relation_property_patch: dict[str, Any] = Field(default_factory=dict)
    max_depth: int = 3
    scope: str | None = None


class ImpactPath(BaseModel):
    path: list[str] = Field(default_factory=list)
    relations: list[str] = Field(default_factory=list)
    depth: int = 0


class ImpactReport(BaseModel):
    direct_impacts: list[str] = Field(default_factory=list)
    indirect_impacts: list[str] = Field(default_factory=list)
    target_impact: list[str] = Field(default_factory=list)
    scoped_impact: list[str] = Field(default_factory=list)
    evidence_paths: list[ImpactPath] = Field(default_factory=list)

