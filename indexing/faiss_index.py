from __future__ import annotations

import numpy as np

try:
    import faiss
except ImportError:  # pragma: no cover - optional in some envs
    faiss = None  # type: ignore[assignment]


class FaissIndex:
    """Small wrapper around FAISS with a numpy fallback."""

    def __init__(self, use_faiss: bool = True) -> None:
        self.use_faiss = use_faiss and faiss is not None
        self.index = None
        self.matrix: np.ndarray | None = None

    def build(self, vectors: np.ndarray) -> None:
        arr = _normalize_rows(vectors)
        if arr.size == 0:
            self.index = None
            self.matrix = arr
            return
        if self.use_faiss:
            dim = arr.shape[1]
            idx = faiss.IndexFlatIP(dim)
            idx.add(arr.astype(np.float32))
            self.index = idx
            self.matrix = None
            return
        self.matrix = arr
        self.index = None

    def search(self, query_vec: np.ndarray, top_k: int) -> tuple[np.ndarray, np.ndarray]:
        if top_k <= 0:
            return np.zeros((1, 0), dtype=np.float32), np.zeros((1, 0), dtype=np.int64)
        q = _normalize_rows(query_vec.reshape(1, -1))
        if self.use_faiss and self.index is not None:
            scores, indices = self.index.search(q.astype(np.float32), top_k)
            return scores, indices
        if self.matrix is None or self.matrix.size == 0:
            return np.zeros((1, 0), dtype=np.float32), np.zeros((1, 0), dtype=np.int64)
        sims = np.dot(self.matrix, q[0])
        k = min(top_k, sims.shape[0])
        order = np.argsort(-sims)[:k]
        scores = sims[order].astype(np.float32).reshape(1, -1)
        indices = order.astype(np.int64).reshape(1, -1)
        return scores, indices


def _normalize_rows(vectors: np.ndarray) -> np.ndarray:
    arr = np.asarray(vectors, dtype=np.float32)
    if arr.ndim != 2:
        raise ValueError("vectors must be a 2D array")
    if arr.size == 0:
        return arr
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return arr / norms

