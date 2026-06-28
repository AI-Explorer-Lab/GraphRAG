from __future__ import annotations

from typing import Optional

from domain.req import AskRequest
from domain.res import AskResponse
from exceptions import NotFoundException, ServiceUnavailableException
from graph.graph_views import extract_graph, extract_subgraph
from mapper.graph_repository import GraphRepository
from retrieval.agentic_ircot import AgenticIRCoT


class QueryService:
    def __init__(self, repo: GraphRepository, cfg) -> None:
        self.repo = repo
        self.cfg = cfg

    def list_graphs(self) -> dict:
        return {"graphs": self.repo.list_graph_ids()}

    def sync_graphs(self) -> dict:
        status = self.repo.sync_from_falkordb(clear_existing=True)
        if status.get("enabled") is False:
            raise ServiceUnavailableException("FalkorDB is disabled for this API runtime.")
        if status.get("available") is False:
            raise ServiceUnavailableException("FalkorDB is unavailable; start the database and retry sync.")
        return status

    def ask_question(self, payload: AskRequest) -> AskResponse:
        graph = self.repo.get_graph(payload.graph_id)
        if graph is None:
            raise NotFoundException(f"graph_id '{payload.graph_id}' not built")
        chunks = self.repo.get_chunks(payload.graph_id)

        chain = AgenticIRCoT.from_config(self.cfg)
        mode = payload.mode or self.cfg.default_ask_mode
        result = chain.run(
            graph=graph,
            chunks=chunks,
            question=payload.question,
            top_k=payload.top_k,
            mode=mode,
            max_steps=payload.max_steps,
        )
        return AskResponse(
            answer=str(result.get("answer", "")),
            sub_questions=result.get("sub_questions", []),  # type: ignore[arg-type]
            involved_types=result.get("involved_types", {}),  # type: ignore[arg-type]
            retrieval=result.get("retrieval", {}),
        )

    def get_subgraph(self, graph_id: str, node_id: Optional[str], hops: int) -> dict:
        graph = self.repo.get_graph(graph_id)
        if graph is None:
            raise NotFoundException(f"graph_id '{graph_id}' not built")
        if not node_id:
            return extract_graph(graph)
        return extract_subgraph(graph, node_id=node_id, hops=hops)
