from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from constants.graph import ALLOWED_ENTITY_RELATIONS


class EntityInput(BaseModel):
    id: str
    name: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    children: list[str] = Field(default_factory=list)


class TransitionInput(BaseModel):
    id: str
    source: str
    target: str
    relation: str = "transitions"
    properties: dict[str, Any] = Field(default_factory=dict)


class HasRelation(BaseModel):
    source: str
    target: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphInput(BaseModel):
    entities: dict[str, EntityInput] = Field(default_factory=dict)
    transitions: list[TransitionInput] = Field(default_factory=list)
    has_relations: list[HasRelation] = Field(default_factory=list)


class NormalizedGraph(BaseModel):
    entities: list[EntityInput] = Field(default_factory=list)
    transitions: list[TransitionInput] = Field(default_factory=list)
    has_relations: list[HasRelation] = Field(default_factory=list)


class ChangeSpecModel(BaseModel):
    source: str
    target: str
    relation: str = "transitions"
    relation_property_patch: dict[str, Any] = Field(default_factory=dict)
    max_depth: int = 3
    scope: Optional[str] = None


class ImpactPath(BaseModel):
    path: list[str] = Field(default_factory=list)
    relations: list[str] = Field(default_factory=list)
    depth: int = 0
