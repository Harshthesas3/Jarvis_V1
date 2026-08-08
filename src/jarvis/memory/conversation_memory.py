"""Conversation Memory Wrapper.

Wraps the existing ConversationMemory to provide a consistent interface
with the memory manager architecture.
"""

from __future__ import annotations

from typing import Any, List, Optional

from jarvis.memory.conversation import ConversationMemory
from jarvis.memory.store import JsonMemoryStore


class ConversationMemoryWrapper:
    """Wrapper around ConversationMemory for consistent memory manager interface.

    Provides the same interface as ConversationMemory but initialized
    with the JSON store from the memory manager.
    """

    def __init__(self, store: JsonMemoryStore) -> None:
        """Initialize conversation memory wrapper.

        Args:
            store: JSON memory store for persistence
        """
        self._memory = ConversationMemory(store)

    def add_message(self, role: str, content: str) -> None:
        """Add a message to conversation history.

        Args:
            role: Message role (user, assistant, system)
            content: Message content
        """
        self._memory.add_message(role, content)

    def get_history(self, limit: Optional[int] = None) -> List[dict[str, Any]]:
        """Get conversation history.

        Args:
            limit: Maximum number of messages to return (None for all)

        Returns:
            List of message dictionaries
        """
        return self._memory.get_history(limit)

    def clear(self) -> None:
        """Clear conversation history."""
        self._memory.clear()

    def summarize(self) -> str:
        """Get conversation summary.

        Returns:
            Summary string of conversation
        """
        return self._memory.summarize()
