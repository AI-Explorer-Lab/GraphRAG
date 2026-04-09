from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from lineage_graphrag.api.dependencies import get_repo
from lineage_graphrag.domain.query_models import AskRequest, AskResponse
from lineage_graphrag.graph.graph_views import extract_subgraph
from lineage_graphrag.llm.answer_generator import AnswerGenerator
from lineage_graphrag.retrieval.decomposer import LineageQuestionDecomposer
from lineage_graphrag.retrieval.orchestrator import LineageRetriever
from lineage_graphrag.storage.graph_repository import GraphRepository

router = APIRouter(tags=["query"])


@router.post("/v1/queries/ask", response_model=AskResponse)
def ask_question(
    payload: AskRequest,
    request: Request,
    repo: GraphRepository = Depends(get_repo),
) -> AskResponse:
    graph = repo.get_graph(payload.graph_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f"graph_id '{payload.graph_id}' not built")
    chunks = repo.get_chunks(payload.graph_id)

    decomposer = LineageQuestionDecomposer()
    retrieval = LineageRetriever()
    answer_gen = AnswerGenerator.from_config(request.app.state.config)

    decomposition = decomposer.decompose(payload.question)
    sub_questions = decomposition["sub_questions"]
    involved_types = decomposition["involved_types"]

    merged_triples: list[str] = []
    merged_chunk_ids: list[str] = []
    merged_chunk_contents: list[str] = []
    merged_paths = []

    for sub_q in sub_questions:
        sub_text = str(sub_q.get("sub-question", payload.question))
        result = retrieval.retrieve(
            graph=graph,
            chunks=chunks,
            question=sub_text,
            top_k=payload.top_k,
            involved_types=involved_types,  # type: ignore[arg-type]
        )
        merged_triples.extend(result.get("triples", []))
        merged_chunk_ids.extend(result.get("chunk_ids", []))
        merged_chunk_contents.extend(result.get("chunk_contents", []))
        merged_paths.extend(result.get("paths", []))

    retrieval_result = {
        "triples": list(dict.fromkeys(merged_triples))[: payload.top_k],
        "chunk_ids": list(dict.fromkeys(merged_chunk_ids))[: payload.top_k],
        "chunk_contents": list(dict.fromkeys(merged_chunk_contents))[: payload.top_k],
        "paths": merged_paths[: payload.top_k],
    }

    answer = answer_gen.generate(payload.question, retrieval_result)
    return AskResponse(
        answer=answer,
        sub_questions=sub_questions,  # type: ignore[arg-type]
        involved_types=involved_types,  # type: ignore[arg-type]
        retrieval=retrieval_result,
    )


@router.get("/v1/graphs/{graph_id}/subgraph")
def get_subgraph(
    graph_id: str,
    node_id: str = Query(..., description="center node id"),
    hops: int = Query(1, ge=1, le=3),
    repo: GraphRepository = Depends(get_repo),
):
    graph = repo.get_graph(graph_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f"graph_id '{graph_id}' not built")
    return extract_subgraph(graph, node_id=node_id, hops=hops)
