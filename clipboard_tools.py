"""
clipboard_tools.py
------------------
Tkinter-backed clipboard access for JARVIS.

Public API:
    read() -> str                    # returns "" if clipboard is empty
    write(text: str) -> bool         # copies text to the OS clipboard
    clear() -> bool                  # empties the clipboard
    summarize(query_chat_fn=None) -> str   # reads + summarizes via LLM

Design notes:
- A SINGLE persistent Tk root is created the first time the module is used
  and reused for every operation. We never call tk.Tk() per-call.
- All Tk operations happen on the main thread. In the JARVIS voice loop the
  executor is already on the main thread, so this is safe.
- Every Tk call site is wrapped in try/finally and the root is never
  destroyed — it's a process-lifetime root. A clipboard_get() failure
  (empty clipboard, or Windows returning ERROR_CLIPBOARD_NOT_AVAILABLE in
  some headless sessions) is logged and returns "" / False gracefully.
- All access logs to the "jarvis.clipboard" logger.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger("jarvis.clipboard")

# Lazy import — Tkinter is heavy and not needed for non-clipboard commands.
# We also tolerate the import failure so the rest of JARVIS can still
# import this module (e.g. for tests on Linux CI).
try:  # pragma: no cover - Tk presence is platform-dependent
    import tkinter as tk
    _TK_AVAILABLE = True
except Exception as exc:  # noqa: BLE001
    tk = None  # type: ignore[assignment]
    _TK_AVAILABLE = False
    logger.warning("tkinter not available: %s", exc)


# ---------------------------------------------------------------------------
# Process-lifetime Tk root
# ---------------------------------------------------------------------------
_root: Optional["tk.Tk"] = None
_root_lock = threading.Lock()
_CLIPBOARD_POLL_MS = 50  # How long to give the OS to populate the clipboard


def _get_root():
    """Return the process-lifetime Tk root, creating it on first use.
    Never destroys the root — Tk is finicky about repeated create/destroy
    cycles on Windows and we want a stable home for clipboard operations."""
    global _root
    if not _TK_AVAILABLE:
        return None
    if _root is not None:
        return _root
    with _root_lock:
        if _root is not None:
            return _root
        try:
            _root = tk.Tk()
            _root.withdraw()
            # Keep the root responsive without showing a window.
            try:
                _root.wm_attributes("-topmost", False)
            except Exception:
                pass
            logger.info("clipboard_tools: Tk root created.")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to create Tk root")
            _root = None
    return _root


def _shutdown() -> None:
    """Destroy the persistent root. Call this from interpreter shutdown
    if you care about clean teardown. Not required for normal use."""
    global _root
    with _root_lock:
        if _root is not None:
            try:
                _root.destroy()
            except Exception:
                pass
            _root = None
            logger.info("clipboard_tools: Tk root destroyed.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def read() -> str:
    """Return the current clipboard text, or '' if empty / unavailable."""
    root = _get_root()
    if root is None:
        logger.warning("clipboard.read: no Tk root available")
        return ""
    try:
        root.clipboard_clear()
        # update() flushes pending events so the OS can deliver clipboard data.
        root.update()
        text = root.clipboard_get()
    except Exception as exc:  # noqa: BLE001
        # tk.TclError: "CLIPBOARD selection doesn't exist" or similar.
        # On Windows the OS sometimes returns '' rather than erroring, but
        # be defensive either way.
        logger.info("clipboard.read: nothing on clipboard (%s)", exc.__class__.__name__)
        return ""
    if text is None:
        return ""
    return str(text)


def write(text: str) -> bool:
    """Copy `text` to the OS clipboard. Returns True on success."""
    if text is None:
        text = ""
    root = _get_root()
    if root is None:
        logger.warning("clipboard.write: no Tk root available")
        return False
    try:
        root.clipboard_clear()
        root.clipboard_append(text)
        # update_idletasks is enough — we don't need a full event loop tick.
        # We do need *some* flush so Windows pushes the data to the OS clipboard.
        root.update_idletasks()
        root.update()
    except Exception as exc:  # noqa: BLE001
        logger.exception("clipboard.write failed: %s", exc)
        return False
    logger.info("clipboard.write: copied %d chars", len(text))
    return True


def clear() -> bool:
    """Empty the clipboard. Returns True on success."""
    root = _get_root()
    if root is None:
        return False
    try:
        root.clipboard_clear()
        root.update_idletasks()
        root.update()
    except Exception as exc:  # noqa: BLE001
        logger.warning("clipboard.clear failed: %s", exc)
        return False
    logger.info("clipboard.clear: cleared clipboard")
    return True


def summarize(chat_fn: Optional[Callable[[str], str]] = None) -> str:
    """Read the clipboard and (if `chat_fn` is provided) ask the LLM to
    summarize it in 1-2 sentences. If no chat_fn is supplied, return the
    first 200 characters verbatim."""
    text = read()
    if not text.strip():
        return "Your clipboard is empty, sir."
    if chat_fn is None:
        snippet = text.strip()[:200]
        return f"Clipboard contents: {snippet}"
    try:
        return chat_fn(
            f"Summarize the following clipboard text in 1-2 concise "
            f"sentences, suitable for speech:\n{text}"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("clipboard.summarize: chat_fn failed: %s", exc)
        return f"Clipboard summary failed, sir. Contents start with: {text[:120]}"
