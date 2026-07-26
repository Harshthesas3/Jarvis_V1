"""JSON-backed semantic (fact) memory.

Implements :class:`jarvis.interfaces.memory.SemanticMemory` using JSON file
storage for facts.  This is a **basic implementation** that stores facts as
structured items under the ``"items"`` key (matching the legacy
``memory.json`` format).  It does **not** perform vector-based similarity
search — text matching is done via simple substring / keyword checks.

An embedding-powered replacement should swap in a vector database adapter
(e.g. Chroma, FAISS, or an external embedding API).
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from jarvis.interfaces.memory import SemanticMemory as SemanticMemoryABC
from jarvis.memory.store import JsonMemoryStore


class JsonSemanticMemory(SemanticMemoryABC):
    """Fact-based long-term memory backed by JSON storage.

    Facts are stored as entries in the ``"items"`` list inside the backing
    store, exactly as the legacy ``memory.json`` format expects.

    Parameters
    ----------
    store : JsonMemoryStore
        The backing memory store whose ``"items"`` key holds the fact list.
    """

    def __init__(self, store: JsonMemoryStore) -> None:
        self._store = store

    # ------------------------------------------------------------------
    # SemanticMemory ABC — embedding interface
    # ------------------------------------------------------------------

    def store_embedding(
        self, key: str, text: str, metadata: Optional[dict] = None
    ) -> None:
        """Store a fact entry.

        Because this implementation does not generate actual embeddings,
        *key* is stored as the fact ``id`` and *text* as the fact ``content``
        for substring matching during search.
        """
        items: List[Dict[str, Any]] = list(self._store.get("items", []))
        # Avoid duplicates — overwrite a fact with the same id if present.
        for i, existing in enumerate(items):
            if existing.get("id") == key:
                items[i] = self._build_item(key, text, metadata)
                self._store.set("items", items)
                return

        items.append(self._build_item(key, text, metadata))
        self._store.set("items", items)

    def search(
        self, query: str, top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Search stored facts by simple substring matching.

        Returns up to *top_k* facts whose ``content`` field contains the
        query string (case-insensitive).
        """
        items: List[Dict[str, Any]] = list(self._store.get("items", []))
        q = query.lower()
        matches = [
            item
            for item in items
            if q in str(item.get("content", "")).lower()
        ]
        return matches[:top_k]

    def is_available(self) -> bool:
        """Always returns ``True`` — basic implementation is always ready."""
        return True

    # ------------------------------------------------------------------
    # Convenience methods (high-level API used by the rest of Jarvis)
    # ------------------------------------------------------------------

    def store_fact(
        self,
        content: str,
        *,
        category: str = "general",
        importance: int = 1,
        source: str = "jarvis",
        tags: Optional[List[str]] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Store a fact and return its auto-generated id."""
        fact_id = f"ltm_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        self.store_embedding(
            fact_id,
            content,
            metadata={
                "category": category,
                "importance": importance,
                "source": source,
                "tags": tags or [],
                **(metadata or {}),
            },
        )
        return fact_id

    def recall_fact(self, fact_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific fact by its id, or ``None`` if not found."""
        items: List[Dict[str, Any]] = list(self._store.get("items", []))
        for item in items:
            if item.get("id") == fact_id:
                return item
        return None

    def search_facts(
        self,
        query: str,
        top_k: int = 5,
        *,
        category: Optional[str] = None,
        min_importance: int = 0,
    ) -> List[Dict[str, Any]]:
        """Search facts with optional category / importance filters."""
        items: List[Dict[str, Any]] = list(self._store.get("items", []))
        q = query.lower()
        matches: List[Dict[str, Any]] = []
        for item in items:
            if q and q not in str(item.get("content", "")).lower():
                continue
            if category and item.get("category") != category:
                continue
            if item.get("importance", 0) < min_importance:
                continue
            matches.append(item)
        return matches[:top_k]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_item(
        key: str,
        text: str,
        metadata: Optional[dict] = None,
    ) -> Dict[str, Any]:
        md = metadata or {}
        now = time.time()
        return {
            "id": key,
            "content": text,
            "timestamp": now,
            "category": md.get("category", "general"),
            "importance": md.get("importance", 1),
            "ttl_days": md.get("ttl_days"),
            "source": md.get("source", "jarvis"),
            "correlations": md.get("correlations", []),
            "tags": md.get("tags", []),
            "metadata": md.get("metadata", {}),
        }
