"""Memory management package.

Provides persistent key-value storage, conversation history with sliding
windows, semantic (fact-based) long-term memory, and ChromaDB vector search.
"""

from jarvis.memory.store import JsonMemoryStore
from jarvis.memory.conversation import ConversationMemory
from jarvis.memory.semantic import JsonSemanticMemory
from jarvis.memory.chroma_memory import ChromaSemanticMemory

def get_semantic_memory(store: JsonMemoryStore | None = None) -> JsonSemanticMemory | ChromaSemanticMemory:
    """Return a ChromaSemanticMemory if available, else fall back to JsonSemanticMemory."""
    chroma = ChromaSemanticMemory()
    if chroma.is_available():
        return chroma
    if store is None:
        store = JsonMemoryStore()
    return JsonSemanticMemory(store)

__all__ = [
    "JsonMemoryStore",
    "ConversationMemory",
    "JsonSemanticMemory",
    "ChromaSemanticMemory",
    "get_semantic_memory",
]
