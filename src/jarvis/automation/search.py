"""SearchInApp implementation for in-application text search.

Implements the SearchInApp interface from jarvis.interfaces.automation by
delegating to the existing ``PrioritizedSearchAgent`` from ``search_agent``.
"""

from __future__ import annotations

import logging
from typing import Optional

from jarvis.interfaces.automation import SearchInApp as SearchInAppInterface

logger = logging.getLogger("jarvis.automation.search")

# Lazy-loaded search agent
_search_agent = None


def _get_search_agent():
    """Lazily import and return the ``PrioritizedSearchAgent`` singleton."""
    global _search_agent
    if _search_agent is None:
        try:
            import sys, os

            root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
            )
            if root not in sys.path:
                sys.path.insert(0, root)

            from search_agent import search_agent  # type: ignore[import-untyped]

            _search_agent = search_agent
        except ImportError as exc:
            logger.warning("Could not load search agent: %s", exc)
    return _search_agent


class SearchInApp(SearchInAppInterface):
    """Search for text inside an application window.

    Uses the existing ``PrioritizedSearchAgent`` which tries keyboard
    shortcuts first (e.g. Ctrl+F), then falls back to accessibility APIs
    (pywinauto).  The caller must supply a valid window handle (``hwnd``)
    to scope the search.
    """

    def search(self, query: str, app: str, hwnd: int) -> dict:
        """Search for *query* in the given *app* window.

        Args:
            query: The text to search for.
            app:   Application name (e.g. ``"chrome"``, ``"vs code"``).
            hwnd:  Window handle of the target application window.

        Returns:
            A dict with keys ``"success"`` (bool) and ``"message"`` (str).
        """
        agent = _get_search_agent()
        if agent is None:
            return {
                "success": False,
                "message": "Search agent is not available.",
            }

        try:
            result = agent.search(query, app, hwnd)
            return {
                "success": result.success,
                "message": result.message,
                "method": result.method.name if result.method else None,
                "confidence": result.confidence,
            }
        except Exception as exc:
            logger.exception("Search in '%s' failed", app)
            return {
                "success": False,
                "message": f"Search failed: {exc}",
            }

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------
    def search_in_app(self, app: str, query: str) -> dict:
        """Convenience wrapper that looks up the active window for *app*.

        Uses ``WindowManager.find_window_for_app`` to auto-discover the
        correct window handle before searching.

        Args:
            app:   Application name.
            query: Text to search for.

        Returns:
            Same dict format as :meth:`search`.
        """
        from jarvis.automation.window import _get_core_wm

        wm = _get_core_wm()
        if wm is None:
            return {"success": False, "message": "Window manager unavailable."}

        window_info = None
        if hasattr(wm, "find_window_for_app"):
            window_info = wm.find_window_for_app(app)

        if window_info is None:
            return {
                "success": False,
                "message": f"Could not find a window for '{app}'.",
            }

        return self.search(query, app, window_info["hwnd"])
