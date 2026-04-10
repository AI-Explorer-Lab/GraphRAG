from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class CacheEntry:
    key: str
    value: Any


class CacheRegistry:
    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def get(self, key: str) -> Any:
        return self._store.get(key)

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def clear(self) -> None:
        self._store.clear()

