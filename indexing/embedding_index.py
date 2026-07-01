from __future__ import annotations

import hashlib
import re
from typing import Sequence

import numpy as np

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # pragma: no cover - optional in some envs
    SentenceTransformer = None  # type: ignore[assignment]


class EmbeddingIndex:
    """Text embedding utility with deterministic fallback."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self.model_name = model_name
        self.model = None
        if SentenceTransformer is not None:
            try:
                # Avoid network download stalls in offline/deploy environments.
                self.model = SentenceTransformer(model_name, local_files_only=True)
            except Exception:
                self.model = None
        self.fallback_dim = 384

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        normalized = [t if isinstance(t, str) else str(t) for t in texts]
        if not normalized:
            return np.zeros((0, self.fallback_dim), dtype=np.float32)
        if self.model is not None:
            arr = self.model.encode(normalized, convert_to_numpy=True, show_progress_bar=False)
            return np.asarray(arr, dtype=np.float32)
        vectors = [self._hashed_bow(text) for text in normalized]
        return np.asarray(vectors, dtype=np.float32)

    def _hashed_bow(self, text: str) -> np.ndarray:
        vec = np.zeros((self.fallback_dim,), dtype=np.float32)
        tokens = re.findall(r"[A-Za-z0-9_]+", text.lower())
        if not tokens:
            return vec
        for token in tokens:
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            idx = h % self.fallback_dim
            vec[idx] += 1.0
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec
