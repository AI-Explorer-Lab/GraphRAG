from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


ALLOWED_ENTITY_RELATIONS = {
    "owns",
    "uses",
    "transfers_to",
    "provides_to",
    "scores",
    "triggers",
    # Backward-compatible lineage default.
    "transitions",
}


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


class LineageInput(BaseModel):
    # New canonical format:
    # {
    #   "entities": {"id1": {...}, "id2": {...}},
    #   "transitions": [{"id":"t1","source":"id1","target":"id2","properties":{...}}]
    # }
    entities: dict[str, EntityInput] = Field(default_factory=dict)
    transitions: list[TransitionInput] = Field(default_factory=list)
    has_relations: list[HasRelation] = Field(default_factory=list)


class NormalizedLineage(BaseModel):
    entities: list[EntityInput] = Field(default_factory=list)
    transitions: list[TransitionInput] = Field(default_factory=list)
    has_relations: list[HasRelation] = Field(default_factory=list)
