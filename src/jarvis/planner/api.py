"""Public API for the JARVIS planner."""

from __future__ import annotations

import logging
import re
from typing import Callable, Optional
from . import config, circuit_breaker, metrics, aliases
from .llm import llm_chat_with_retry, extract_json
from .intent import classify_intent, invoke_capability
from .intent.capabilities import resolve_capability as resolve_intent_to_capability
from .regex.patterns import _try_fast_path
from .context import (
    has_multi_step_intent,
    _resolve_pronouns,
    _update_context_from_plan,
    needs_clarification,
)
from .splitter import split_clauses
from .validation import _validate_plan

logger = logging.getLogger("jarvis.planner.api")

# ---------------------------------------------------------------------------
# Tool registry (moved from planner.py global)
# ---------------------------------------------------------------------------

_TOOL_REGISTRY: dict = {}
_TOOL_REGISTRY_LOCK = __import__("threading").Lock()


def register_tool(name: str, handler: Callable) -> None:
    """Register a handler for an action name."""
    if name not in config.SUPPORTED_ACTIONS:
        logger.warning("Registering tool for unknown action: %s", name)
    with _TOOL_REGISTRY_LOCK:
        _TOOL_REGISTRY[name] = handler


def _dispatch(plan: dict) -> str:
    """Internal dispatcher used by the executor."""
    if not isinstance(plan, dict):
        return "I received an invalid plan, sir."
    action = plan.get("action")
    handler = _TOOL_REGISTRY.get(action) if action else None
    if handler is None:
        return "I do not know how to do that yet, sir."
    try:
        return handler(plan)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Handler for %s failed", action)
        return f"Failed to execute {action}, sir. {exc}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def plan_action(user_text: str, *, use_llm: bool = True) -> dict:
    """Convert a natural-language request into a structured plan.

    Returns either a single-action dict {"action": ..., ...} or
    {"steps": [...]} for multi-step plans. Falls back to
    {"action": "ai_chat", "text": user_text} when nothing else fits.
    Also supports {"action": "clarification", "question": ...} for
    incomplete commands.
    """
    if not user_text or not user_text.strip():
        return {"action": "ai_chat", "text": ""}

    text = user_text.strip()
    if len(text) > config.MAX_INPUT_LENGTH:
        text = text[: config.MAX_INPUT_LENGTH]
        logger.warning("Input truncated to %d characters", config.MAX_INPUT_LENGTH)

    # If circuit breaker is open, skip LLM path entirely
    if circuit_breaker.get_circuit_breaker().is_open():
        logger.info("Circuit breaker open — forcing regex-only path")
        use_llm = False

    # Apply speech correction if available
    try:
        import speech_correction
        corrected = speech_correction.correct(text)
        if corrected != text:
            logger.info("Speech correction: '%s' -> '%s'", text, corrected)
        text = corrected
    except ImportError:
        pass

    # Deterministic creator-identity interception: answers come from trusted
    # application code (jarvis.services.identity), never from the LLM, so the
    # identity cannot be hallucinated or redefined by user prompts.
    try:
        from jarvis.services.identity import get_identity_manager
        identity_response = get_identity_manager().match_query(text)
    except Exception:  # noqa: BLE001 - never break planning over identity
        identity_response = None
    if identity_response:
        logger.info("Identity query intercepted: %s", text[:100])
        return {"action": "identity_response", "text": identity_response}

    # Check for incomplete commands (clarification handler)
    clarification = needs_clarification(text)
    if clarification is not None:
        logger.info("Clarification needed: %s", clarification["question"])
        return clarification

    # Multi-step path: use LLM decomposition for logical task planning,
    # fall back to syntactic clause splitting if LLM unavailable.
    if has_multi_step_intent(text):
        if use_llm:
            decomposed = _decompose_multi_step(text)
            if decomposed is not None and "steps" in decomposed:
                report = _validate_plan(decomposed)
                if report is not None:  # valid
                    logger.info(
                        "LLM-decomposed multi-step plan (%d steps) for: %s",
                        len(decomposed["steps"]),
                        text[:100],
                    )
                    return decomposed
                logger.info(
                    "LLM decomposition invalid, falling back to syntax"
                )
        # Fall back to syntactic splitting
        clauses = split_clauses(text)
        if len(clauses) > 1:
            local_ctx = {
                "last_folder": "",
                "last_file": "",
                "last_clipboard": "",
                "last_search_result": "",
                "last_screenshot": "",
                "current_file": "",
                "current_folder": "",
                "current_app": "",
                "current_window": "",
            }
            # Load current_app from session memory (Issue 7)
            try:
                import session_memory as _sm
                ctx_app = _sm.get("current_app")
                if ctx_app:
                    local_ctx["current_app"] = ctx_app
            except Exception:
                pass
            steps = []
            for clause in clauses:
                resolved = _resolve_pronouns(clause, local_ctx)
                plan = _plan_single(resolved, use_llm=use_llm)
                # Route bare "search X" after open_app to search_in_app_v2,
                # but only if the clause doesn't mention "the web".
                prev_app = (
                    steps[-1].get("app", "")
                    if steps and steps[-1].get("action") == "open_app"
                    else local_ctx.get("current_app", "")
                )
                if (
                    plan.get("action") == "web_search"
                    and prev_app
                    and "search" in clause.lower()[:10]
                    and "web" not in clause.lower()[:20]
                    and not re.search(r"\bin\b", clause.lower())
                ):
                    plan = {
                        "action": "search_in_app_v2",
                        "query": plan.get("query", ""),
                        "app": prev_app,
                    }
                _update_context_from_plan(local_ctx, plan)
                # Deduplicate consecutive identical steps
                if not steps or plan != steps[-1]:
                    steps.append(plan)
            if not steps:
                return {"action": "ai_chat", "text": text}
            logger.info(
                "Multi-step plan (%d steps) generated for: %s",
                len(steps),
                text[:100],
            )
            return {"steps": steps}

    # Single-action path
    plan = _plan_single(text, use_llm=use_llm)
    # Route standalone "search for X" to search_in_app_v2 ONLY when
    # a current_app is active AND the user isn't asking for the web
    # ("search the web for X" should stay as web_search).
    if (
        plan.get("action") == "web_search"
        and "search" in text.lower()[:10]
        and "web" not in text.lower()[:20]
    ):
        try:
            import session_memory as _sm
            ctx_app = _sm.get("current_app")
            if ctx_app and not re.search(r"\bin\b", text.lower()):
                plan = {
                    "action": "search_in_app_v2",
                    "query": plan.get("query", ""),
                    "app": ctx_app,
                }
        except Exception:
            pass
    # Update session memory with the plan
    try:
        import session_memory as _sm
        _sm.update_from_plan(plan)
    except Exception:
        pass
    logger.info("Single-action plan: action=%s  text=%s", plan.get("action"), text[:100])
    return plan


def execute_plan(plan: dict) -> str:
    """Execute a validated plan. Validates before dispatching to the executor."""
    report = _validate_plan(plan)
    if report is None:  # invalid
        # re-run validate_plan to get the issues list for the error message
        from .validation import validate_plan as _vp
        vr = _vp(plan)
        msg = "; ".join(vr["issues"]) if vr["issues"] else "Invalid plan"
        logger.warning("execute_plan rejected: %s", msg)
        return f"I cannot execute that plan, sir. Invalid: {msg}"
    # Lazy import to avoid circular dependency at module load
    try:
        from task_executor import execute_plan as _executor_execute_plan
        return _executor_execute_plan(plan)
    except ImportError as exc:
        logger.error("Failed to import task_executor: %s", exc)
        return "I cannot execute plans right now, sir. The executor is unavailable."


def _plan_single(text: str, use_llm: bool = True) -> dict:
    """Handle a single-action request (no multi-step decomposition)."""
    fast = _try_fast_path(text)
    if fast is not None:
        # Normalize "run <app>" → open_app when program looks like an app name
        if fast.get("action") == "run_program":
            program = fast.get("program", "")
            if (
                program
                and re.match(r"^[a-zA-Z][\w\s.\-]*$", program)
                and "." not in program
                and "/" not in program
                and "\\" not in program
            ):
                return {"action": "open_app", "app": program}
        return fast
    if not use_llm:
        return {"action": "ai_chat", "text": text}

    # Phase 1: Classify intent (NEVER generates actions)
    intent = classify_intent(text, config.get_planner_model())
    if intent is None:
        logger.warning("Intent classification failed (LLM unavailable)")
        return {"action": "ai_chat", "text": text}

    # If confidence is too low, ask for clarification
    if intent.get("confidence", 0) < config.CONFIDENCE_THRESHOLD:
        goal = intent.get("goal", "")
        logger.info("Low confidence intent (%.2f), asking for clarification", intent.get("confidence", 0))
        metrics.record_metric(clarifications=1)
        if goal:
            msg = f"I think you want to {goal}, but I am not entirely sure. Could you please be more specific?"
        else:
            msg = "I am not sure what you want me to do. Could you please rephrase your request?"
        return {"action": "clarification", "question": msg}

    # Phase 2: Resolve intent → capability, then invoke capability handler
    capability = resolve_intent_to_capability(intent)
    logger.info(
        "Intent=%s → Capability=%s (conf=%.2f)",
        intent.get("intent", "?"),
        capability,
        intent.get("confidence", 0),
    )
    plan = invoke_capability(capability, intent, text)
    if plan is not None:
        validated = _validate_plan(plan)
        if validated is not None:
            return validated

    return {"action": "ai_chat", "text": text}




# ---------------------------------------------------------------------------
# Multi-step decomposition
# ---------------------------------------------------------------------------

_MULTI_STEP_DECOMPOSITION_PROMPT = """You are JARVIS, a task decomposition engine.

Your job: take a user's request and break it down into logical, sequential steps based on the OVERALL OBJECTIVE. Do not simply split on conjunctions — understand what the user truly wants to accomplish.

Available actions (use ONLY these):
open_app, close_app, switch_window, focus_window, web_search, search_in_app_v2,
reminder, clipboard, email, whatsapp, screenshot, screen_awareness,
system_control, volume_control, memory_store, memory_recall, time, date,
diagnostics, system_stats, music, ai_chat, file_operation, folder_operation,
pc_control, click, type_text, press_key, scroll, browser_open, browser_search,
run_program, run_terminal_command, generate_code, wait, wait_for_window, open_folder.

Output ONLY a JSON object with a "steps" array.
Each step must have an "action" field and relevant parameters.

EXAMPLES:

User: Find my Jarvis project, open the important files and tell me where to start.
Objective: Analyze a project to understand where to begin working.
{
  "steps":[
    {"action":"file_operation","op":"search_files","query":"Jarvis project"},
    {"action":"file_operation","op":"search_files","query":"Jarvis project main files"},
    {"action":"ai_chat","text":"I found the Jarvis project. Let me identify the most important files to get started."},
    {"action":"file_operation","op":"read_file","path":"main.py"},
    {"action":"file_operation","op":"read_file","path":"planner.py"},
    {"action":"ai_chat","text":"Based on the project structure, I recommend starting with main.py for the entry point..."}
  ]
}

User: Open calculator and create a reminder to stop studying in 2 minutes.
Objective: Set up a study timer.
{
  "steps":[
    {"action":"open_app","app":"calculator"},
    {"action":"reminder","time":"in 2 minutes","task":"stop studying"}
  ]
}

User: Open Chrome, search for weather.
Objective: Check the weather online.
{
  "steps":[
    {"action":"open_app","app":"Chrome"},
    {"action":"web_search","query":"weather"}
  ]
}

User: Remind me about my meeting and send an email to the team.
Objective: Manage a meeting reminder and notify team members.
{
  "steps":[
    {"action":"reminder","time":"","task":"meeting reminder"},
    {"action":"email","recipient":"team","subject":"meeting","body":"Reminder about our meeting"}
  ]
}

User: Search the web for AI news and save the results to a file.
Objective: Gather and store information about AI developments.
{
  "steps":[
    {"action":"web_search","query":"AI news"},
    {"action":"ai_chat","text":"I will save the AI news results to a file for you."}
  ]
}

User: Open Spotify, play some music and set volume to 30.
Objective: Start listening to music at a comfortable volume.
{
  "steps":[
    {"action":"open_app","app":"Spotify"},
    {"action":"music","op":"play"},
    {"action":"volume_control","op":"set","level":30}
  ]
}

CRITICAL RULES:
- Understand the OBJECTIVE, not just split the sentence.
- "Tell me where to start" -> analyze and recommend (ai_chat). NEVER route to whatsapp.
- "Open the important files" -> find them first, then open.
- Decompose into MEANINGFUL sub-tasks that form a coherent workflow.
- Each step must use a valid action from the list above.
- Use ai_chat for analytical, explanatory, or conversational steps.
- Do NOT use whatsapp unless the user explicitly asks to message someone.
- Output ONLY the JSON. No prose, no markdown, no explanation.
"""


def _decompose_multi_step(user_text: str) -> Optional[dict]:
    """Use LLM to decompose a complex request into logical steps."""
    resp = llm_chat_with_retry(
        model=config.get_planner_model(),
        messages=[
            {"role": "system", "content": _MULTI_STEP_DECOMPOSITION_PROMPT},
            {"role": "user", "content": user_text},
        ],
        temperature=0.0,
        num_predict=800,
    )
    if resp is None:
        logger.warning("Multi-step decomposition failed (LLM unavailable)")
        return None
    try:
        raw = resp["message"]["content"]
        parsed = extract_json(raw)
        if parsed and isinstance(parsed, dict):
            steps = parsed.get("steps", [])
            if isinstance(steps, list) and len(steps) >= 2:
                cleaned: list[dict] = []
                for step in steps:
                    if isinstance(step, dict) and step.get("action"):
                        cleaned.append(step)
                if len(cleaned) >= 2:
                    logger.info("LLM-decomposed %d steps for: %s", len(cleaned), user_text[:80])
                    metrics.record_metric(multi_step_plans=1)
                    return {"steps": cleaned}
        logger.warning("Multi-step decomposition returned invalid structure: %.200s", raw)
        return None
    except Exception as exc:
        logger.warning("Multi-step decomposition parsing failed: %s", exc)
        return None