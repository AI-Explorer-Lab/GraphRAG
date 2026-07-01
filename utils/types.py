from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import networkx as nx


@dataclass
class GraphBuildResult:
    graph: nx.MultiDiGraph
    evidence_chunks: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
