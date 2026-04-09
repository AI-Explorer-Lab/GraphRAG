from __future__ import annotations


def rank_chunk_ids(question: str, chunks: dict[str, str], chunk_ids: list[str], top_k: int) -> list[str]:
    q_tokens = set(question.lower().split())
    scored: list[tuple[str, int]] = []
    for chunk_id in chunk_ids:
        text = chunks.get(chunk_id, "")
        tokens = set(text.lower().split())
        score = len(tokens & q_tokens)
        scored.append((chunk_id, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [cid for cid, _ in scored[:top_k]]

