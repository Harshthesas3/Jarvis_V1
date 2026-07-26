"""Sliding-window conversation history backed by JSON memory store.

Implements :class:`jarvis.interfaces.memory.ConversationMemory` using
:class:`JsonMemoryStore` for persistence.  Old messages beyond a
configurable limit are automatically trimmed.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from jarvis.interfaces.memory import ConversationMemory as ConversationMemoryABC
from jarvis.memory.store import JsonMemoryStore


class ConversationMemory(ConversationMemoryABC):
    """Conversation history with a sliding window.

    Stores messages under the ``"conversation"`` key of the backing
    :class:`JsonMemoryStore`.  Each entry is a dict with keys ``role``,
    ``content``, and ``timestamp``.

    Parameters
    ----------
    store : JsonMemoryStore
        The backing memory store.
    history_limit : int
        Maximum number of messages retained in the window.  Defaults to 100.
        When the limit is exceeded the oldest messages are trimmed on the
        next write.
    storage_key : str
        Key used inside *store* for the conversation list.  Defaults to
        ``"conversation"``.
    """

    def __init__(
        self,
        store: JsonMemoryStore,
        history_limit: int = 100,
        storage_key: str = "conversation",
    ) -> None:
        self._store = store
        self._limit = history_limit
        self._key = storage_key

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_message(self, role: str, content: str) -> None:
        """Append a message to the conversation history.

        Automatically trims the oldest messages when the window exceeds
        ``history_limit``.
        """
        history = self._load_history()
        history.append(
            {
                "role": role,
                "content": content,
                "timestamp": time.time(),
            }
        )
        # Sliding window: keep only the most recent N entries.
        if len(history) > self._limit:
            history = history[-self._limit :]
        self._store.set(self._key, history)

    def get_history(
        self, limit: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """Return recent conversation history.

        Parameters
        ----------
        limit : int, optional
            Maximum number of most recent messages to return.  When omitted
            the full stored history is returned (up to ``history_limit``).
        """
        history = self._load_history()
        if limit is not None and limit > 0:
            return history[-limit:]
        return list(history)

    def clear(self) -> None:
        """Remove all conversation history."""
        self._store.set(self._key, [])

    # Alias for API compatibility.
    clear_history = clear

    def summarize(self) -> str:
        """Return a short summary describing the conversation.

        .. note::
            This is a basic implementation that reports message counts.
            A production version should use an LLM call for true
            summarization.
        """
        history = self._load_history()
        if not history:
            return "No conversation history."

        user_msgs = sum(1 for m in history if m.get("role") == "user")
        asst_msgs = sum(1 for m in history if m.get("role") in ("assistant", "system"))
        total_chars = sum(len(m.get("content", "")) for m in history)

        return (
            f"Conversation: {len(history)} messages "
            f"({user_msgs} user, {asst_msgs} assistant), "
            f"{total_chars} characters."
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_history(self) -> List[Dict[str, Any]]:
        """Load the conversation list from the store, returning [] if empty."""
        return list(self._store.get(self._key, []))
