"""Plan validation utilities."""

from __future__ import annotations

import logging
import os
import re
from typing import Dict, List, Optional, Set, Tuple

from .config import (
    CONFIDENCE_THRESHOLD,
    MAX_INPUT_LENGTH,
    MAX_STEPS,
    MAX_LLM_RETRIES,
)

logger = logging.getLogger("jarvis.planner.validation")

# ---------------------------------------------------------------------------
# Required parameters for each action type (top-level)
# ---------------------------------------------------------------------------

_ACTION_REQUIRED_PARAMS: dict[str, list[str]] = {
    "open_app": ["app"],
    "close_app": ["app"],
    "switch_window": ["target"],
    "focus_window": ["title"],
    "web_search": ["query"],
    "search_in_app": ["query", "app"],
    "search_in_app_v2": ["query", "app"],
    "reminder": ["time", "task"],
    "set_reminder": ["time", "task"],
    "calendar_event": ["title", "date", "time"],
    "clipboard": ["op"],
    "email": ["recipient", "subject", "body"],
    "whatsapp": ["contact", "message"],
    "screenshot": [],
    "screen_awareness": ["op"],
    "system_control": ["op"],
    "volume_control": ["op"],
    "memory_store": ["fact"],
    "memory_recall": [],
    "memory_clear": [],
    "time": [],
    "date": [],
    "diagnostics": [],
    "system_stats": [],
    "music": ["op"],
    "file_operation": ["op"],
    "folder_operation": ["op"],
    "pc_control": ["phrase"],
    "click": [],
    "double_click": [],
    "right_click": [],
    "move_mouse": ["x", "y"],
    "type_text": ["text"],
    "press_key": ["key"],
    "hotkey": ["keys"],
    "scroll": ["direction"],
    "browser_open": ["url"],
    "browser_search": ["query"],
    "browser_click": ["element"],
    "run_program": ["program"],
    "run_terminal_command": ["command"],
    "generate_code": ["description"],
    "wait": ["seconds"],
    "wait_for_window": ["title"],
    "wait_for_element": ["selector"],
    "ai_chat": ["text"],
    "identity_response": ["text"],
    "open_folder": ["path"],
    "clarification": ["question"],
}

# Op-specific additional required params (action -> op -> [params])
_OP_REQUIRED_PARAMS: dict[str, dict[str, list[str]]] = {
    "reminder": {
        "list": [],
        "clear": [],
        "remove": ["index"],
        "show": [],
        "": ["time", "task"],
    },
    "clipboard": {
        "write": ["text"],
    },
    "volume_control": {
        "set": ["level"],
    },
    "file_operation": {
        "create_file": ["name"],
        "read_file": ["path"],
        "write_file": ["path", "content"],
        "append_file": ["path", "content"],
        "delete_file": ["path"],
        "rename_file": ["path", "new_name"],
        "move_file": ["path", "dest_folder"],
        "copy_file": ["path", "dest_folder"],
        "open_file": ["path"],
        "search_files": ["query"],
    },
    "folder_operation": {
        "create_folder": ["name"],
        "delete_folder": ["path"],
        "rename_folder": ["path", "new_name"],
        "list_folder": ["path"],
    },
    "music": {
        "play": [],
        "pause": [],
        "stop": [],
        "next": [],
        "previous": [],
        "skip": [],
    },
    "screen_awareness": {
        "describe": [],
        "error": [],
        "code_review": [],
        "summarize_document": [],
    },
    "system_control": {
        "lock": [],
        "shutdown": [],
        "restart": [],
        "sleep": [],
    },
    "pc_control": {
        "lock": [],
        "shutdown": [],
        "restart": [],
        "sleep": [],
        "standby": [],
        "sign out": [],
        "log off": [],
    },
    "memory_store": {
        "": ["fact"],
    },
    "click": {
        "": [],
    },
}

# Dangerous operations that should be flagged (rejected unless confirmed)
_DANGEROUS_OPS: dict[str, set[str]] = {
    "file_operation": {"delete_file"},
    "folder_operation": {"delete_folder"},
    "system_control": {"shutdown", "restart", "lock"},
    "pc_control": {"shutdown", "restart", "lock", "sleep"},
    "memory_clear": set(),
}

# Parameters that must be numeric (non-negative integers)
_NUMERIC_PARAMS: set[str] = {"seconds", "level", "x", "y", "amount", "index"}

# Actions that create a resource (file/folder)
_CREATE_ACTIONS: set[str] = {"create_file", "create_folder"}
# Actions that consume/delete a resource
_DELETE_ACTIONS: set[str] = {
    "delete_file",
    "delete_folder",
    "rename_file",
    "rename_folder",
    "move_file",
    "write_file",
}

# Invalid parameter combinations (action, param1, param2, reason)
_INVALID_COMBOS: list[tuple[str, str, str, str]] = [
    ("volume_control", "op", "level", "volume_control with op='set' requires 'level' parameter"),
    ("reminder", "index", "time", "reminder: 'index' and 'time' cannot both be set"),
]


def _validate_numeric_param(name: str, value: object, index: int, action: str, issues: List[str]) -> bool:
    """Validate that a param is a non-negative integer. Returns True if valid."""
    if not isinstance(value, (int, float)):
        issues.append(
            f"Step {index} ({action}): param '{name}' must be numeric, got {type(value).__name__}"
        )
        return False
    if isinstance(value, (int, float)) and value < 0:
        issues.append(
            f"Step {index} ({action}): param '{name}' must be non-negative, got {value}"
        )
        return False
    return True


def _validate_single_step(step: dict, index: int, issues: List[str]) -> Optional[dict]:
    """Validate a single action step. Returns the step or None if invalid.
    Appends warnings to `issues` for non-fatal problems."""
    action = step.get("action")
    if not action:
        issues.append(f"Step {index}: missing 'action' field")
        return None
    # Note: In the new architecture, we rely on the adapter for action validation.
    # For simplicity, we accept any action string here; the adapter will handle unknown actions.
    # If you want strict validation, check against SUPPORTED_ACTIONS.

    # Check top-level required params
    for param in _ACTION_REQUIRED_PARAMS.get(action, []):
        val = step.get(param)
        if val is None or (isinstance(val, str) and not val.strip()):
            issues.append(
                f"Step {index} ({action}): missing required param '{param}'"
            )
            return None

    # Check op-specific required params
    op = step.get("op", "")
    op_map = _OP_REQUIRED_PARAMS.get(action, {})
    # Try exact op match, then empty-string fallback
    op_params = op_map.get(op) or op_map.get("", [])
    for param in op_params:
        val = step.get(param)
        if val is None or (isinstance(val, str) and not val.strip()):
            issues.append(
                f"Step {index} ({action}/{op}): missing required param '{param}'"
            )
            return None

    # Check dangerous operations
    dangerous_ops = _DANGEROUS_OPS.get(action)
    if dangerous_ops is not None:
        if not dangerous_ops:
            # Empty set means the whole action is dangerous
            issues.append(
                f"Step {index} ({action}): dangerous operation -- requires confirmation"
            )
        elif op in dangerous_ops:
            issues.append(
                f"Step {index} ({action}/{op}): dangerous operation -- requires confirmation"
            )

    # Validate numeric parameters
    for param_name, param_val in step.items():
        if param_name in _NUMERIC_PARAMS and param_val is not None:
            if not _validate_numeric_param(param_name, param_val, index, action, issues):
                return None

    # Check invalid parameter combinations
    for p1, p2, detail in [
        ("op", "level", "volume_control/set requires level"),
        ("index", "time", "reminder: index+time conflict"),
    ]:
        val1 = step.get(p1)
        val2 = step.get(p2)
        if val1 is not None and val2 is not None:
            if action == "volume_control" and step.get("op") != "set":
                continue
            if action == "reminder" and "index" not in step:
                continue
            issues.append(
                f"Step {index} ({action}): conflicting params '{p1}' and '{p2}'"
            )

    return step


def _check_duplicate_steps(steps: List[dict], issues: List[str]) -> None:
    """Detect identical consecutive steps."""
    for i in range(1, len(steps)):
        if steps[i] == steps[i - 1]:
            issues.append(
                f"Steps {i-1} and {i} are identical duplicates: {steps[i]}"
            )


def _check_cross_resource_conflicts(steps: List[dict], issues: List[str]) -> None:
    """Detect steps that create a resource and later delete it, or similar conflicts."""
    created: Dict[str, int] = {}  # resource_name -> step index
    for i, step in enumerate(steps):
        action = step.get("action", "")
        op = step.get("op", "")
        if action == "file_operation" and op in _CREATE_ACTIONS:
            name = step.get("name", "")
            if name:
                # Normalize path for comparison
                norm = os.path.normpath(name)
                created.setdefault(norm, i)
        if action in ("file_operation", "folder_operation") and op in _DELETE_ACTIONS:
            target = step.get("name", "") or step.get("path", "")
            if target:
                norm = os.path.normpath(target)
                if norm in created:
                    issues.append(
                        f"Step {i} ({action}/{op}) deletes/modifies '{target}' "
                        f"created in step {created[norm]}"
                    )


def _check_step_ordering(steps: List[dict], issues: List[str]) -> None:
    """Flag suspicious step ordering (e.g. write to a file before creating it)."""
    # Track created resources
    exists_after: Set[str] = set()
    for i, step in enumerate(steps):
        action = step.get("action", "")
        op = step.get("op", "")
        name = step.get("name", "") or step.get("path", "")
        if action == "file_operation" and op in _CREATE_ACTIONS and name:
            exists_after.add(os.path.normpath(name))
        if action == "file_operation" and op == "write_file" and name:
            if os.path.normpath(name) not in exists_after:
                # Non-fatal -- the file might already exist on disk
                issues.append(
                    f"Step {i} writes to '{name}' but no prior create step was found "
                    f"(file may pre-exist)"
                )


def validate_plan(plan: dict) -> dict:
    """Validate a plan before execution.

    Returns {"valid": True/False, "issues": [str, ...]}.
    Call this before execute_plan() to catch problems early.
    """
    result: dict[str, any] = {"valid": True, "issues": []}
    issues: List[str] = []

    if not isinstance(plan, dict):
        issues.append("Plan is not a dict")
        result["valid"] = False
        result["issues"] = issues
        return result

    if "steps" in plan:
        steps = plan.get("steps", [])
        if not isinstance(steps, list):
            issues.append("'steps' is not a list")
            result["valid"] = False
            result["issues"] = issues
            return result
        if not steps:
            issues.append("'steps' list is empty")
            result["valid"] = False
            result["issues"] = issues
            return result
        if len(steps) > 20:  # MAX_STEPS from config
            issues.append(
                f"Plan exceeds maximum step count ({len(steps)} > 20)"
            )
            result["valid"] = False
            result["issues"] = issues
            return result

        cleaned: List[dict] = []
        for i, step in enumerate(steps):
            v = _validate_single_step(step, i, issues)
            if v is None:
                result["valid"] = False
            else:
                cleaned.append(v)

        _check_duplicate_steps(cleaned, issues)
        _check_cross_resource_conflicts(cleaned, issues)
        _check_step_ordering(cleaned, issues)

        # Cross-step checks: duplicate open_app
        for i in range(len(cleaned)):
            for j in range(i + 1, len(cleaned)):
                if (
                    cleaned[i].get("action") == "open_app"
                    and cleaned[j].get("action") == "open_app"
                    and cleaned[i].get("app") == cleaned[j].get("app")
                ):
                    issues.append(
                        f"Steps {i} and {j}: both open the same app '{cleaned[i].get('app')}'"
                    )

    else:
        v = _validate_single_step(plan, 0, issues)
        if v is None:
            result["valid"] = False

    result["issues"] = issues
    if issues:
        result["valid"] = False
    return result


def _validate_plan(plan: dict) -> Optional[dict]:
    """Internal validator. Returns the plan if valid, None if invalid.
    Logs all issues. Backward-compatible with existing callers."""
    report = validate_plan(plan)
    for issue in report["issues"]:
        logger.warning("Plan validation: %s", issue)
    if not report["valid"]:
        # In a real implementation, we would increment a metric here.
        # For now, we just return None.
        return None
    return plan