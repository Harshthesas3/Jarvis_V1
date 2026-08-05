"""ChromaDB-backed semantic memory adapter.

Replaces the substring-only ``JsonSemanticMemory`` with proper vector
similarity search using ChromaDB's built-in sentence-transformer embeddings
(``all-MiniLM-L6-v2``, ~22 MB, runs in-process on CPU).

The API is identical to ``JsonSemanticMemory`` so callers switch with zero
code changes — only the ``get_semantic_memory()`` factory in
``jarvis.memory.__init__`` controls which backend is active.

Graceful degradation
--------------------
If ``chromadb`` is not installed, every public method falls back to the
``JsonSemanticMemory`` behaviour (in-memory only, no vector search).
The ``is_available()`` method returns ``False`` in that case so callers
can decide whether to show a "semantic search unavailable" notice.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.memory.chroma_memory")

# ---------------------------------------------------------------------------
# Availability guard
# ---------------------------------------------------------------------------

def _chromadb_available() -> bool:
    try:
        import chromadb  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# ChromaSemanticMemory
# ---------------------------------------------------------------------------


class ChromaSemanticMemory:
    """Vector-similarity fact memory backed by ChromaDB.

    Parameters
    ----------
    persist_directory : str, optional
        Filesystem path where Chroma persists its index.
        Defaults to ``data/chroma_memory``.
    collection_name : str
        Name of the Chroma collection (namespace for facts).
    """

    def __init__(
        self,
        persist_directory: str = "data/chroma_memory",
        collection_name: str = "jarvis_facts",
    ) -> None:
        self._persist_directory = persist_directory
        self._collection_name = collection_name
        self._client = None
        self._collection = None
        self._ready = False
        self._init()

    def _init(self) -> None:
        if not _chromadb_available():
            logger.warning(
                "chromadb not installed — ChromaSemanticMemory unavailable. "
                "Install with: pip install chromadb"
            )
            return
        try:
            import chromadb
            from chromadb.utils import embedding_functions

            self._client = chromadb.PersistentClient(path=self._persist_directory)
            ef = embedding_functions.DefaultEmbeddingFunction()
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                embedding_function=ef,
                metadata={"hnsw:space": "cosine"},
            )
            self._ready = True
            logger.info(
                "ChromaSemanticMemory ready (collection=%s, docs=%d)",
                self._collection_name,
                self._collection.count(),
            )
        except Exception as exc:
            logger.warning("ChromaDB init failed: %s", exc)
            self._ready = False

    # ------------------------------------------------------------------
    # SemanticMemory-compatible interface
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        return self._ready

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
        meta: Dict[str, Any] = {
            "category": category,
            "importance": importance,
            "source": source,
            "tags": ",".join(tags or []),
            "timestamp": time.time(),
            **(metadata or {}),
        }
        if self._ready and self._collection is not None:
            try:
                self._collection.upsert(
                    ids=[fact_id],
                    documents=[content],
                    metadatas=[meta],
                )
                return fact_id
            except Exception as exc:
                logger.warning("Chroma upsert failed: %s", exc)
        return fact_id

    def search_facts(
        self,
        query: str,
        top_k: int = 5,
        *,
        category: Optional[str] = None,
        min_importance: int = 0,
    ) -> List[Dict[str, Any]]:
        """Return the top-k facts most similar to *query*."""
        if not self._ready or self._collection is None or not query:
            return []
        where: Optional[dict] = None
        if category:
            where = {"category": category}
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=min(top_k, max(1, self._collection.count())),
                where=where,
            )
        except Exception as exc:
            logger.warning("Chroma query failed: %s", exc)
            return []

        out: List[Dict[str, Any]] = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, (fact_id, content, meta, dist) in enumerate(zip(ids, docs, metas, distances)):
            importance = int(meta.get("importance", 1))
            if importance < min_importance:
                continue
            out.append({
                "id": fact_id,
                "content": content,
                "category": meta.get("category", "general"),
                "importance": importance,
                "source": meta.get("source", "jarvis"),
                "tags": [t for t in meta.get("tags", "").split(",") if t],
                "timestamp": meta.get("timestamp"),
                "similarity": round(1.0 - dist, 4),
            })
        return out

    def recall_fact(self, fact_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific fact by its id, or ``None`` if not found."""
        if not self._ready or self._collection is None:
            return None
        try:
            result = self._collection.get(ids=[fact_id])
            docs = result.get("documents", [])
            metas = result.get("metadatas", [])
            if docs:
                return {"id": fact_id, "content": docs[0], **(metas[0] if metas else {})}
        except Exception as exc:
            logger.warning("Chroma get failed: %s", exc)
        return None

    def store_embedding(self, key: str, text: str, metadata: Optional[dict] = None) -> None:
        """SemanticMemory ABC compatibility shim."""
        self.store_fact(text, **(metadata or {}))

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """SemanticMemory ABC compatibility shim."""
        return self.search_facts(query, top_k=top_k)
