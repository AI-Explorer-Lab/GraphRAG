from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EntityInput(BaseModel):
    id: str
    properties: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    children: list[str] = Field(default_factory=list)


class TransitionInput(BaseModel):
    source: str
    target: str
    properties: dict[str, Any] = Field(default_factory=dict)


class HasRelation(BaseModel):
    source: str
    target: str
    properties: dict[str, Any] = Field(default_factory=dict)


class LineageInput(BaseModel):
    entities: list[EntityInput] = Field(default_factory=list)
    transitions: list[TransitionInput] = Field(default_factory=list)
    has_relations: list[HasRelation] = Field(default_factory=list)


class NormalizedLineage(BaseModel):
    entities: list[EntityInput] = Field(default_factory=list)
    transitions: list[TransitionInput] = Field(default_factory=list)
    has_relations: list[HasRelation] = Field(default_factory=list)

