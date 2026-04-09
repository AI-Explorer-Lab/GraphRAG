from __future__ import annotations

from typing import Any

from lineage_graphrag.domain.lineage_models import LineageInput


class LineageParser:
    """Parse and validate lineage payloads."""

    def parse(self, raw_json: dict[str, Any]) -> LineageInput:
        return LineageInput.model_validate(raw_json)

