from __future__ import annotations

from domain.models import ChangeSpecModel


def describe_change(spec: ChangeSpecModel) -> str:
    patch = ", ".join(f"{k}={v}" for k, v in spec.relation_property_patch.items())
    return f"{spec.source} -[{spec.relation}]-> {spec.target} ({patch})"

