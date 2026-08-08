"""Compatibility shim — re-exports ``jarvis.planner`` for legacy scripts."""

from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent
_src = str(_root / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from jarvis.planner import (  # noqa: E402
    SUPPORTED_ACTIONS,
    _FAST_PATH_TRIGGERS,
    _TOOL_REGISTRY,
    _dispatch,
    execute_plan,
    get_metrics,
    get_metrics_snapshot,
    plan_action,
    register_tool,
    validate_plan,
)
from jarvis.planner.api import _plan_single  # noqa: E402
from jarvis.planner.context import (  # noqa: E402
    _INITIAL_CONTEXT,
    _resolve_pronouns,
    _update_context_from_plan,
    needs_clarification as _needs_clarification,
)
from jarvis.planner.regex.patterns import _resolve_path, _try_fast_path  # noqa: E402

__all__ = [
    "SUPPORTED_ACTIONS",
    "_FAST_PATH_TRIGGERS",
    "_INITIAL_CONTEXT",
    "_TOOL_REGISTRY",
    "_dispatch",
    "_needs_clarification",
    "_plan_single",
    "_resolve_path",
    "_resolve_pronouns",
    "_try_fast_path",
    "_update_context_from_plan",
    "execute_plan",
    "get_metrics",
    "get_metrics_snapshot",
    "plan_action",
    "register_tool",
    "validate_plan",
]
