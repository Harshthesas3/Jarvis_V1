"""JSON-file-backed persistent key-value store.

Implements :class:`jarvis.interfaces.memory.MemoryStore` with thread-safe
read/write and backward compatibility with the legacy ``memory.json``
format used by ``memory_v2.py``.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from jarvis.interfaces.memory import MemoryStore


class JsonMemoryStore(MemoryStore):
    """Thread-safe, JSON-file-backed key-value memory store.

    The entire store is kept in memory as a plain ``dict`` and persisted to a
    single JSON file on every write.  The file format is backward-compatible
    with the legacy ``memory.json`` layout (a top-level ``"items"`` list of
    fact objects) so that existing on-disk state is preserved.

    Parameters
    ----------
    file_path : str or Path
        Path to the JSON file used for persistence.  Defaults to
        ``memory.json`` in the current working directory.
    """

    def __init__(self, file_path: os.PathLike | str = "memory.json") -> None:
        self._path = Path(file_path)
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> Dict[str, Any]:
        """Load all memory data from the JSON file.

        If the file does not exist an empty dict is returned.
        """
        with self._lock:
            if not self._path.exists():
                self._data = {}
                self._loaded = True
                return self._data

            raw = self._path.read_text(encoding="utf-8")
            parsed = json.loads(raw)

            # Backward compatibility: if the file is a list, wrap it under
            # an ``"items"`` key (legacy memory_v2.py format).
            if isinstance(parsed, list):
                parsed = {"items": parsed}

            # Backward compatibility: the legacy file has only ``"items"``
            # at the top level – we keep that key intact and extend the
            # dict with any additional keys.
            self._data = parsed
            self._loaded = True
            return self._data

    def save(self, data: Dict[str, Any]) -> None:
        """Persist *data* to the JSON file atomically.

        Uses a write-to-temp-then-rename strategy to avoid partial writes.
        """
        with self._lock:
            self._data = data
            self._flush()

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value for *key*, or *default* if missing."""
        with self._lock:
            self._ensure_loaded()
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set *key* to *value* and persist immediately."""
        with self._lock:
            self._ensure_loaded()
            self._data[key] = value
            self._flush()

    def delete(self, key: str) -> bool:
        """Remove *key* from the store.

        Returns ``True`` if the key existed, ``False`` otherwise.
        """
        with self._lock:
            self._ensure_loaded()
            existed = key in self._data
            if existed:
                del self._data[key]
                self._flush()
            return existed

    def clear(self) -> None:
        """Remove all data from the store and persist the empty state."""
        with self._lock:
            self._data = {}
            self._flush()

    def get_all(self) -> Dict[str, Any]:
        """Return a shallow copy of the entire store dict."""
        with self._lock:
            self._ensure_loaded()
            return dict(self._data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """Lazy-load data on first access if not already loaded."""
        if not self._loaded:
            self.load()

    def _flush(self) -> None:
        """Atomically write ``_data`` to disk."""
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        tmp.replace(self._path)
