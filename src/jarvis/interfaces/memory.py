"""Memory storage interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class MemoryStore(ABC):
    """Persistent memory storage."""

    @abstractmethod
    def load(self) -> Dict[str, Any]:
        """Load all memory data."""

    @abstractmethod
    def save(self, data: Dict[str, Any]) -> None:
        """Persist memory data."""

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Get a specific value from memory."""

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """Set a specific value in memory."""

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a key from memory. Returns True if existed."""

    @abstractmethod
    def clear(self) -> None:
        """Clear all memory data."""


class SemanticMemory(ABC):
    """Vector-based semantic memory for similarity search."""

    @abstractmethod
    def store_embedding(self, key: str, text: str, metadata: Optional[dict] = None) -> None:
        """Store a text entry with its embedding."""

    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search memory by semantic similarity."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if semantic memory is available."""


class ConversationMemory(ABC):
    """Session-based conversation history with rolling window."""

    @abstractmethod
    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation history."""

    @abstractmethod
    def get_history(self, limit: Optional[int] = None) -> List[Dict[str, str]]:
        """Get recent conversation history."""

    @abstractmethod
    def clear(self) -> None:
        """Clear conversation history."""

    @abstractmethod
    def summarize(self) -> str:
        """Get a summary of the conversation so far."""
