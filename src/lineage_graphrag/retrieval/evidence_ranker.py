from __future__ import annotations

import re


def rank_chunk_ids(question: str, chunks: dict[str, str], chunk_ids: list[str], top_k: int) -> list[str]:
    q_tokens = _tokens(question)
    scored: list[tuple[str, int, str]] = []
    for chunk_id in chunk_ids:
        text = f"{chunk_id} {chunks.get(chunk_id, '')}"
        tokens = _tokens(text)
        score = len(tokens & q_tokens)
        scored.append((chunk_id, score, chunk_id))
    scored.sort(key=lambda x: (-x[1], x[2]))
    return [cid for cid, _, _ in scored[:top_k]]


def _tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for part in re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]+", text.lower()):
        tokens.add(part)
        if re.fullmatch(r"[\u4e00-\u9fff]+", part):
            tokens.update(part)
            tokens.update(part[index : index + 2] for index in range(max(len(part) - 1, 0)))
    return tokens
