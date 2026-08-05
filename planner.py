"""
planner.py
----------
Intent → structured action plan.

Public API:
    plan_action(user_text: str) -> dict
    execute_plan(plan: dict) -> str
    validate_plan(plan: dict) -> dict
    register_tool(name: str, handler: callable) -> None
    SUPPORTED_ACTIONS: set[str]

Design notes:
- The planner prefers a deterministic regex fast-path for trivial commands
  (open, time, date, screenshot, volume, system control, clipboard, web search,
  websites, music, memory). This keeps latency low and works if Ollama is
  unavailable.
- For ambiguous / multi-step requests it calls Qwen 3.5:4b through Ollama with
  a strict system prompt and asks for a single JSON object.
- The JSON output is validated against an action whitelist. Unknown actions
  fall back to the AI chat handler.
- Plans can be single-action dicts OR {"steps": [...]} for multi-step work.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

# Lazy import heavy modules to reduce startup time
_ollama_client = None
_speech_correction_module = None
_settings_module = None
_SPEECH_CORRECTION_AVAILABLE = False

def _get_ollama_client():
    """Get or create a persistent ollama.Client (reuses httpx connection pool).
    This eliminates ~3.2s connection overhead per LLM call."""
    global _ollama_client
    if _ollama_client is None:
        import ollama as _ollama_mod
        _ollama_client = _ollama_mod.Client()
    return _ollama_client


def _get_speech_correction():
    """Lazy-load speech_correction module."""
    global _speech_correction_module, _SPEECH_CORRECTION_AVAILABLE
    if _speech_correction_module is None:
        try:
            import speech_correction as _sc
            _speech_correction_module = _sc
            _SPEECH_CORRECTION_AVAILABLE = True
        except ImportError:
            pass
    return _speech_correction_module

logger = logging.getLogger("jarvis.planner")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Model name — try config first, fall back to hardcoded default. (lazy-loaded)
def _get_planner_model() -> str:
    try:
        from settings_manager import get_settings
        _s = get_settings()
        if _s is not None:
            return _s.get("models.planner_model", "qwen3.5:4b")
    except Exception:
        pass
    return "qwen3.5:4b"

_PLANNER_MODEL: str = "qwen3.5:4b"  # will be resolved lazily

# Maximum input length in characters to prevent abuse / prompt injection
_MAX_INPUT_LENGTH: int = 2000

# Confidence threshold below which the planner asks for clarification
_CONFIDENCE_THRESHOLD: float = 0.70

# Maximum steps allowed in a single plan
_MAX_STEPS: int = 20

# Retry / circuit-breaker settings
_MAX_LLM_RETRIES: int = 2
_LLM_RETRY_DELAY_MS: int = 500
_LLM_TIMEOUT_SECONDS: int = 30
_CIRCUIT_BREAKER_MAX_FAILURES: int = 5
_CIRCUIT_BREAKER_RESET_SECONDS: int = 60

# ---------------------------------------------------------------------------
# Circuit breaker for LLM failures
# ---------------------------------------------------------------------------
class _CircuitBreaker:
    """Prevents repeated LLM calls after consecutive failures."""
    def __init__(self, max_failures: int, reset_seconds: float) -> None:
        self._max_failures = max_failures
        self._reset_seconds = reset_seconds
        self._failures: int = 0
        self._last_failure_time: float = 0.0
        self._open: bool = False
        self._lock = threading.Lock()

    def record_failure(self) -> None:
        now = time.monotonic()
        with self._lock:
            self._failures += 1
            self._last_failure_time = now
            if self._failures >= self._max_failures:
                self._open = True
                logger.warning(
                    "LLM circuit breaker OPEN after %d failures (resets in %ss)",
                    self._failures, self._reset_seconds,
                )

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            if self._open:
                self._open = False
                logger.info("LLM circuit breaker CLOSED (success)")

    @property
    def is_open(self) -> bool:
        now = time.monotonic()
        with self._lock:
            if self._open and (now - self._last_failure_time) > self._reset_seconds:
                self._open = False
                self._failures = 0
                logger.info("LLM circuit breaker auto-reset after %.1fs", self._reset_seconds)
            return self._open

_CIRCUIT_BREAKER = _CircuitBreaker(
    max_failures=_CIRCUIT_BREAKER_MAX_FAILURES,
    reset_seconds=_CIRCUIT_BREAKER_RESET_SECONDS,
)

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
class _PlannerMetrics:
    """Lightweight metrics for planner observability."""
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.fast_path_hits: int = 0
        self.fast_path_misses: int = 0
        self.llm_calls: int = 0
        self.llm_failures: int = 0
        self.llm_retries: int = 0
        self.multi_step_plans: int = 0
        self.validation_failures: int = 0
        self.circuit_breaker_hits: int = 0
        self.clarifications: int = 0
        self._total_duration_ms: float = 0.0

    def record_llm_call(self, duration_ms: float) -> None:
        with self._lock:
            self.llm_calls += 1
            self._total_duration_ms += duration_ms

    def record(self, **kwargs: int) -> None:
        with self._lock:
            for k, v in kwargs.items():
                if hasattr(self, k):
                    setattr(self, k, getattr(self, k) + v)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "fast_path_hits": self.fast_path_hits,
                "fast_path_misses": self.fast_path_misses,
                "llm_calls": self.llm_calls,
                "llm_failures": self.llm_failures,
                "llm_retries": self.llm_retries,
                "multi_step_plans": self.multi_step_plans,
                "validation_failures": self.validation_failures,
                "circuit_breaker_hits": self.circuit_breaker_hits,
                "clarifications": self.clarifications,
                "total_duration_ms": round(self._total_duration_ms, 1),
            }

_METRICS = _PlannerMetrics()


def get_metrics() -> dict:
    """Return a snapshot of planner metrics for observability."""
    return _METRICS.snapshot()

# ---------------------------------------------------------------------------
# Folder alias resolution
# ---------------------------------------------------------------------------
_KNOWN_ALIASES: dict[str, str] = {}


def register_folder_alias(name: str, path: str) -> None:
    _KNOWN_ALIASES[name.lower().strip()] = path


def _resolve_path(text: str) -> str:
    """Resolve folder aliases in a path string. Returns the resolved path."""
    if not text:
        return text
    result = text
    home = os.path.expanduser("~")
    alias_map = {
        "downloads": os.path.join(home, "Downloads"),
        "download": os.path.join(home, "Downloads"),
        "desktop": os.path.join(home, "Desktop"),
        "documents": os.path.join(home, "Documents"),
        "document": os.path.join(home, "Documents"),
        "pictures": os.path.join(home, "Pictures"),
        "music": os.path.join(home, "Music"),
        "videos": os.path.join(home, "Videos"),
        "home": home,
        "root": os.path.splitdrive(home)[0] + os.sep,
        "temp": os.environ.get("TEMP", os.path.join(home, "AppData", "Local", "Temp")),
    }
    def _replacer(alias: str, resolved: str) -> None:
        nonlocal result
        pattern = re.compile(
            r"(?<![\\/.\w])" + re.escape(alias) + r"(?![\\/.\w])",
            re.IGNORECASE,
        )
        result = pattern.sub(lambda m: resolved, result)

    for alias, resolved in alias_map.items():
        _replacer(alias, resolved)
    for alias, resolved in _KNOWN_ALIASES.items():
        _replacer(alias, resolved)
    return result


# ---------------------------------------------------------------------------
# Input sanitisation
# ---------------------------------------------------------------------------
def _sanitise_input(text: str) -> str:
    """Truncate and strip dangerous content from user input."""
    if not text:
        return ""
    t = text.strip()
    # Truncate to max length on code-point boundary
    if len(t) > _MAX_INPUT_LENGTH:
        t = t[:_MAX_INPUT_LENGTH]
        logger.warning("Input truncated to %d characters", _MAX_INPUT_LENGTH)
    return t


# ---------------------------------------------------------------------------
# Retry-capable LLM caller with timeout
# ---------------------------------------------------------------------------
def _ollama_chat_with_retry(
    model: str,
    messages: list,
    *,
    temperature: float = 0.0,
    num_predict: int = 400,
    timeout: int | None = None,
) -> dict | None:
    """Call ollama.chat with retry, timeout, and circuit-breaker support.
    Returns the response dict or None on failure."""
    if _CIRCUIT_BREAKER.is_open:
        _METRICS.record(circuit_breaker_hits=1)
        logger.warning("LLM circuit breaker is open — skipping LLM call")
        return None

    if timeout is None:
        timeout = _LLM_TIMEOUT_SECONDS

    options = {"temperature": temperature, "num_predict": num_predict}
    last_exc: Exception | None = None

    for attempt in range(_MAX_LLM_RETRIES + 1):
        try:
            start = time.monotonic()
            resp = _get_ollama_client().chat(
                model=model,
                messages=messages,
                options=options,
                think=False,     # qwen3.x streams ~300+ chars of 'thinking' first
                keep_alive=-1,   # pin the model in memory: ~1.3s reload per call otherwise
            )
            elapsed = (time.monotonic() - start) * 1000.0
            _METRICS.record_llm_call(elapsed)

            _CIRCUIT_BREAKER.record_success()
            return resp
        except Exception as exc:
            last_exc = exc
            if attempt < _MAX_LLM_RETRIES:
                _METRICS.record(llm_retries=1)
                logger.warning(
                    "LLM call attempt %d/%d failed: %s. Retrying in %dms...",
                    attempt + 1, _MAX_LLM_RETRIES + 1, exc, _LLM_RETRY_DELAY_MS,
                )
                time.sleep(_LLM_RETRY_DELAY_MS / 1000.0)

    _METRICS.record(llm_failures=1)
    _CIRCUIT_BREAKER.record_failure()
    logger.error("All %d LLM retries exhausted: %s", _MAX_LLM_RETRIES + 1, last_exc)
    return None


# ---------------------------------------------------------------------------
# Regex conflict detection (run at module load)
# ---------------------------------------------------------------------------
def _detect_regex_conflicts(triggers: list) -> None:
    """Log warnings for overlapping regex patterns that might shadow each other."""
    for i, (p1, _) in enumerate(triggers):
        for j, (p2, _) in enumerate(triggers):
            if i >= j:
                continue
            # Check if p1's match region could overlap p2's on synthetic inputs
            s1, s2 = p1.pattern[:60], p2.pattern[:60]
            try:
                test = "open calculator and open notepad"
                m1 = p1.match(test)
                m2 = p2.match(test)
                if m1 and m2 and m1.group(0) != m2.group(0):
                    logger.debug("Potential overlap #%d <-> #%d: %s | %s", i, j, s1, s2)
            except Exception:
                pass


def _needs_clarification(text: str) -> dict | None:
    """Check if the user's request is incomplete and return a clarification
    prompt if so. Returns None if the request seems complete."""
    t = text.strip().lower()

    # Bare file creation
    if re.match(r"^(?:please\s+)?(?:create|make)\s+(?:a\s+|an\s+)?(?:file\s*)?(?:called\s+|named\s+)?\s*$", t):
        return {
            "action": "clarification",
            "question": "What should the file be named?",
            "hints": ["test.txt", "notes.txt", "main.py"],
        }

    # Bare folder creation
    if re.match(r"^(?:please\s+)?(?:create|make)\s+(?:a\s+|an\s+)?folder\s*$", t):
        return {
            "action": "clarification",
            "question": "What should the folder be named?",
            "hints": ["Python Projects", "Documents", "Test"],
        }

    # Bare reminder
    if re.match(r"^(?:please\s+)?(?:remind(?:\s+me)?|set\s+reminder|create\s+reminder)\s*$", t):
        return {
            "action": "clarification",
            "question": "What should I remind you about and when?",
            "hints": ["remind me in 5 minutes to check the oven", "remind me tomorrow at 9 am to buy groceries"],
        }

    # Bare search
    if re.match(r"^(?:please\s+)?(?:search|look\s+up|find)\s*$", t):
        return {
            "action": "clarification",
            "question": "What would you like me to search for?",
            "hints": ["search for Python tutorials", "search for weather in London"],
        }

    return None

SUPPORTED_ACTIONS: set[str] = {
    "open_app",
    "close_app",
    "switch_window",
    "focus_window",
    "web_search",
    "search_in_app",
    "search_in_app_v2",
    "reminder",
    "set_reminder",
    "calendar_event",
    "clipboard",
    "file_operation",
    "folder_operation",
    "pc_control",
    "email",
    "whatsapp",
    "screenshot",
    "screen_awareness",
    "system_control",
    "volume_control",
    "memory_store",
    "memory_recall",
    "memory_clear",
    "time",
    "date",
    "diagnostics",
    "system_stats",
    "music",
    "click",
    "double_click",
    "right_click",
    "move_mouse",
    "type_text",
    "press_key",
    "hotkey",
    "scroll",
    "browser_open",
    "browser_search",
    "browser_click",
    "run_program",
    "run_terminal_command",
    "generate_code",
    "wait",
    "wait_for_window",
    "wait_for_element",
    "ai_chat",
    "open_folder",
}

# ---------------------------------------------------------------------------
# Tool registry (thread-safe)
# ---------------------------------------------------------------------------
_TOOL_REGISTRY: Dict[str, Callable[[dict], str]] = {}
_TOOL_REGISTRY_LOCK = threading.Lock()


def register_tool(name: str, handler: Callable[[dict], str]) -> None:
    """Register a handler for an action name. Handler receives the plan dict
    and must return a short status string suitable for TTS."""
    if name not in SUPPORTED_ACTIONS:
        logger.warning("Registering tool for unknown action: %s", name)
    with _TOOL_REGISTRY_LOCK:
        _TOOL_REGISTRY[name] = handler


def _log_handler_coverage() -> None:
    """Log which supported actions have no registered handler yet."""
    with _TOOL_REGISTRY_LOCK:
        registered = set(_TOOL_REGISTRY.keys())
    uncovered = SUPPORTED_ACTIONS - registered - {"clarification"}
    if uncovered:
        logger.info("Actions without handlers: %s", sorted(uncovered))


def _get_handler(action: str) -> Callable[[dict], str] | None:
    """Thread-safe handler lookup."""
    with _TOOL_REGISTRY_LOCK:
        return _TOOL_REGISTRY.get(action)


def _dispatch(plan: dict) -> str:
    action = plan.get("action")
    handler = _get_handler(action) if action else None
    if handler is None:
        return "I do not know how to do that yet, sir."
    try:
        return handler(plan)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Handler for %s failed", action)
        return f"Failed to execute {action}, sir. {exc}"


# ---------------------------------------------------------------------------
# Deterministic fast-path
# ---------------------------------------------------------------------------
_FAST_PATH_TRIGGERS: List[Tuple[re.Pattern, Callable]] = [
    # ---------------------------------------------------------------
    # Close app — "close <app>" or "quit <app>"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?(?:close|quit|exit)\s+(?P<app>.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "close_app", "app": m.group("app").strip()},
    ),
    # ---------------------------------------------------------------
    # Browser open — "open browser to <url>" or "go to <url>".
    # Must come BEFORE switch_window so URLs are not misrouted.
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?(?:open\s+browser\s+(?:to|at)\s+|go\s+to\s+)"
            r"(?P<url>https?://\S+|www\.\S+|\S+\.\w{2,}(?:/\S*)?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "browser_open", "url": m.group("url").strip()},
    ),
    # ---------------------------------------------------------------
    # Switch window — "switch to <window/app>". "go to" non-URLs
    # falls through to here.
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?(?:switch|go)\s+to\s+(?P<target>.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "switch_window", "target": m.group("target").strip()},
    ),
    # ---------------------------------------------------------------
    # Open folder — "open folder <path>"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?open\s+folder\s+(?P<path>.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "open_folder", "path": m.group("path").strip()},
    ),
    # ---------------------------------------------------------------
    # Rename folder
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?rename\s+(?:the\s+)?folder\s+"
            r"(?P<path>[\w.\- /\\:]+?)\s+to\s+(?P<new_name>[\w.\- ]+)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "folder_operation",
            "op": "rename_folder",
            "path": m.group("path").strip(),
            "new_name": m.group("new_name").strip(),
        },
    ),
    # ---------------------------------------------------------------
    # Append to file
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?(?:append|add)\s+(?P<content>.+?)\s+to\s+(?:the\s+)?(?:file\s+)?(?P<path>.+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "append_file",
            "path": m.group("path").strip(),
            "content": m.group("content").strip(),
        },
    ),
    # ---------------------------------------------------------------
    # Search in app — "search for X in Y". Negative lookahead for
    # "files"/"the files" so those route to file_operation/search_files.
    # Routes to search_in_app_v2 (universal search engine).
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?search\s+(?:for\s+)?(?P<query>.+?)\s+in\s+(?!files?\s*$)(?P<app>.+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "search_in_app_v2",
            "query": _strip_query_punctuation(m.group("query")),
            "app": m.group("app").strip(),
        },
    ),
    # ---------------------------------------------------------------
    # Click — "click [at] (x, y)" or "click [button]"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?click\s+"
            r"(?:(?:at\s+)?\(?\s*(?P<x>\d+)\s*(?:,\s*|\s+)(?P<y>\d+)\s*\)?)?"
            r"(?:\s*(?P<button>left|right|middle))?\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "click",
            "x": int(m.group("x")) if m.group("x") else None,
            "y": int(m.group("y")) if m.group("y") else None,
            "button": (m.group("button") or "left").lower(),
        },
    ),
    # ---------------------------------------------------------------
    # Double-click
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?double\s*click\s+"
            r"(?:at\s+)?\(?\s*(?P<x>\d+)\s*(?:,\s*|\s+)(?P<y>\d+)\s*\)?\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "double_click",
            "x": int(m.group("x")) if m.group("x") else None,
            "y": int(m.group("y")) if m.group("y") else None,
        },
    ),
    # ---------------------------------------------------------------
    # Right-click
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?right\s*click\s+"
            r"(?:at\s+)?\(?\s*(?P<x>\d+)\s*(?:,\s*|\s+)(?P<y>\d+)\s*\)?\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "right_click",
            "x": int(m.group("x")) if m.group("x") else None,
            "y": int(m.group("y")) if m.group("y") else None,
        },
    ),
    # ---------------------------------------------------------------
    # Type text — "type <text>"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?type\s+(?P<text>.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "type_text", "text": m.group("text").strip()},
    ),
    # ---------------------------------------------------------------
    # Press key — "press <key>"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?press\s+(?P<key>.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "press_key", "key": m.group("key").strip()},
    ),
    # ---------------------------------------------------------------
    # Scroll — "scroll up/down" or "scroll <n>"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?scroll\s+"
            r"(?P<dir>up|down|left|right)?\s*"
            r"(?P<amount>\d+)?\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "scroll",
            "direction": (m.group("dir") or "down").lower(),
            "amount": int(m.group("amount")) if m.group("amount") else 3,
        },
    ),
    # ---------------------------------------------------------------
    # Browser search — "search in browser for X"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?search\s+in\s+(?:the\s+)?browser\s+for\s+(?P<query>.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "browser_search", "query": _strip_query_punctuation(m.group("query"))},
    ),
    # ---------------------------------------------------------------
    # Browser click — "click on <element> in browser"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?click\s+on\s+(?P<element>.+?)\s+in\s+(?:the\s+)?browser\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "browser_click",
            "element": m.group("element").strip(),
        },
    ),
    # ---------------------------------------------------------------
    # Diagnostics — "run diagnostics" or just "diagnostics"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:run\s+)?diagnostics\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "diagnostics"},
    ),
    # ---------------------------------------------------------------
    # Run program — "run <program>" (not "run command <...>").
    # Must come AFTER run_terminal_command to avoid stealing its input.
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?run\s+(?!command\s)(?P<program>.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "run_program", "program": m.group("program").strip()},
    ),
    # ---------------------------------------------------------------
    # Run terminal command — "run command <cmd>" or "execute <cmd>"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?(?:run\s+command|execute)\s+(?P<command>.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "run_terminal_command",
            "command": m.group("command").strip(),
        },
    ),
    # ---------------------------------------------------------------
    # Generate code — "generate code for X" or "write code for X"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?(?:generate|write)\s+code\s+(?:for|to)\s+(?P<description>.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "generate_code",
            "description": m.group("description").strip(),
        },
    ),
    # ---------------------------------------------------------------
    # Wait — "wait <n> seconds" or "wait for <n> seconds"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?wait\s+(?:for\s+)?(?P<seconds>\d+)\s*"
            r"(?:seconds?|secs?)?\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "wait", "seconds": int(m.group("seconds"))},
    ),
    # ---------------------------------------------------------------

    # ---------------------------------------------------------------
        # PC control: many phrases. `phrase` carries the user's words so
    # pc_control.resolve() can fuzzy-match the alias map.
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?"
            r"(?P<phrase>"
            r"lock(?:\s+(?:the\s+)?(?:computer|pc|workstation))?"
            r"|put\s+(?:the\s+)?(?:computer|pc)\s+to\s+sleep"
            r"|sleep(?:\s+(?:the\s+)?(?:computer|pc|mode))?"
            r"|standby"
            r"|log\s*(?:out|off)"
            r"|sign\s+out"
            r"|shutdown(?:\s+(?:the\s+)?(?:computer|pc))?"
            r"|shut\s+down(?:\s+(?:the\s+)?(?:computer|pc))?"
            r"|power\s+off"
            r"|restart(?:\s+(?:the\s+)?(?:computer|pc))?"
            r"|reboot"
            r"|open\s+task\s+manager"
            r"|open\s+(?:the\s+)?control\s+panel"
            r"|open\s+(?:the\s+)?settings"
            r"|open\s+(?:the\s+)?device\s+manager"
            r"|open\s+services"
            r"|open\s+(?:the\s+)?registry(?:\s+editor)?"
            r"|open\s+downloads?(?:\s+folder)?"
            r"|open\s+documents?(?:\s+folder)?"
            r"|open\s+(?:my\s+)?desktop"
            r"|open\s+(?:the\s+)?recycle\s+bin"
            r"|open\s+(?:the\s+)?recycle"
            r")\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "pc_control",
            "phrase": m.group("phrase").strip().lower(),
        },
    ),
    # Standalone noun phrases that should also hit pc_control.
    (
        re.compile(
            r"^(?P<phrase>downloads?|downloads?\s+folder|"
            r"documents?|documents?\s+folder|"
            r"desktop|recycle\s+bin|recycle|"
            r"task\s+manager|control\s+panel|"
            r"device\s+manager|services|registry(?:\s+editor)?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "pc_control",
            "phrase": m.group("phrase").strip().lower(),
        },
    ),
    # ---------------------------------------------------------------
    # File open — "open file <path>" or "open <path.ext>". Must come
    # BEFORE the generic open_app pattern so extensions route correctly.
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?(?:open|launch|show)\s+(?:the\s+)?(?:file\s+)?(?P<path>[\w.\- /\\:]+?\.[a-zA-Z0-9]{1,5})$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "open_file",
            "path": m.group("path").strip(),
        },
    ),
    # ---------------------------------------------------------------
    # Clipboard read — "what's on my clipboard" etc. Must come BEFORE
    # the generic web_search "what is" pattern so clipboard queries
    # are not misrouted to the web.
    # ---------------------------------------------------------------
    (
        re.compile(r"^read\s+my\s+clipboard$|^what(?:'s|\s+is)\s+on\s+my\s+clipboard$",
                   re.IGNORECASE),
        lambda m, src: {"action": "clipboard", "op": "read"},
    ),
    (
        re.compile(r"^read\s+(?:the\s+)?clipboard$", re.IGNORECASE),
        lambda m, src: {"action": "clipboard", "op": "read"},
    ),
    (
        re.compile(r"^what(?:'s|\s+is)\s+on\s+(?:the\s+)?clipboard$",
                   re.IGNORECASE),
        lambda m, src: {"action": "clipboard", "op": "read"},
    ),
    (
        re.compile(r"^(?:summarize|explain)\s+(?:my\s+)?clipboard$",
                   re.IGNORECASE),
        lambda m, src: {"action": "clipboard", "op": "summarize"},
    ),
    (
        re.compile(
            r"^(?:copy|put|write)\s+(?P<text>.+?)\s+(?:to|on)\s+(?:my\s+)?clipboard$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "clipboard", "op": "write", "text": m.group("text").strip()},
    ),
    # ---------------------------------------------------------------
    # Time / date — must come BEFORE the web_search "what is" pattern.
    # ---------------------------------------------------------------
    (
        re.compile(r"^what(?:'s|\s+is)\s+the\s+time(?:\s+now)?$", re.IGNORECASE),
        lambda m, src: {"action": "time"},
    ),
    (
        re.compile(r"^what\s+time\s+is\s+it(?:\s+now)?$", re.IGNORECASE),
        lambda m, src: {"action": "time"},
    ),
    (
        re.compile(r"^what(?:'s|\s+is)\s+(?:the\s+)?(?:today(?:'s)?\s+)?date$", re.IGNORECASE),
        lambda m, src: {"action": "date"},
    ),
    (
        re.compile(r"^what\s+(?:day|date)\s+is\s+(?:it|today)$", re.IGNORECASE),
        lambda m, src: {"action": "date"},
    ),
    (
        re.compile(r"^(?:battery|cpu|ram|memory(?:\s+usage)?|system\s+stats?)$",
                   re.IGNORECASE),
        lambda m, src: {"action": "system_stats", "metric": m.group(0).lower()},
    ),
    # ---------------------------------------------------------------
    # File search — "search for X in files". Must come BEFORE the
    # generic web_search "search for X" pattern.
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?search\s+(?:for\s+)?files?\s+"
            r"(?:containing|matching|named)\s+(?P<query>.+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "search_files",
            "query": m.group("query").strip(),
        },
    ),
    (
        re.compile(
            r"^(?:please\s+)?search\s+(?:for\s+)?(?P<query>.+?)\s+"
            r"(?:in\s+files?|across\s+files?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "search_files",
            "query": m.group("query").strip(),
        },
    ),
    # "open <app>" — single-app launch. Only matches if the argument
    # looks like a real app name (not a descriptive phrase). Rejects
    # "open the most important files", "open my project", "open this file".
    # Allows "open calculator", "open visual studio code", "open the
    # calculator" (single article prefix with a concrete app name).
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^open\s+(?P<app>[a-zA-Z][\w\s.\-]*?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: (
            None
            if re.search(
                r"\b(?:and|then|after\s+that|also|plus)\b",
                m.group("app"), re.IGNORECASE,
            )
            or (
                len(m.group("app").split()) >= 3
                and re.search(
                    r"\b(?:my|a|an|this|that|most|all|these|those|"
                    r"some|any|every|each|important|main|current|recent|"
                    r"previous|next|first|last|second)\b",
                    m.group("app"), re.IGNORECASE,
                )
            )
            else {"action": "open_app", "app": m.group("app").strip()}
        ),
    ),
    # "launch <app>" / "start <app>" / "run <app>"
    (
        re.compile(
            r"^(?:launch|start|run)\s+(?P<app>[a-zA-Z][\w\s.\-]*?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: (
            None
            if re.search(
                r"\b(?:and|then|after\s+that|also|plus)\b",
                m.group("app"), re.IGNORECASE,
            )
            else {"action": "open_app", "app": m.group("app").strip()}
        ),
    ),
    (
        re.compile(
            r"^(?:remind\s+me\s+)?(?:at|on)?\s*"
            r"(?P<time>tomorrow\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?|"
            r"today\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?|"
            r"\d{1,2}(?::\d{2})?\s*(?:am|pm)|"
            r"tomorrow|tonight|tonight\s+at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+"
            r"to\s+(?P<task>.+)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "reminder",
            "time": m.group("time").strip(),
            "task": m.group("task").strip(),
        },
    ),
    (
        re.compile(
            r"^remind\s+me\s+(?P<time>.+?)\s+to\s+(?P<task>.+)$", re.IGNORECASE
        ),
        lambda m, src: {
            "action": "reminder",
            "time": m.group("time").strip(),
            "task": m.group("task").strip(),
        },
    ),
    # "set a reminder in <time> to <task>" — catch-all reminder pattern.
    (
        re.compile(
            r"^(?:set|create|add)\s+(?:a\s+)?reminder\s+"
            r"(?:in\s+)?(?P<time>.+?)\s+to\s+(?P<task>.+)$", re.IGNORECASE
        ),
        lambda m, src: {
            "action": "reminder",
            "time": m.group("time").strip(),
            "task": m.group("task").strip(),
        },
    ),
    # "set a reminder in <time>" (no task specified) — default to a generic reminder.
    (
        re.compile(
            r"^(?:set|create|add)\s+(?:a\s+)?reminder\s+(?:in\s+)?(?P<time>.+)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "reminder",
            "time": m.group("time").strip(),
            "task": "the reminder",
        },
    ),
    (
        re.compile(r"^show\s+reminders?$|^list\s+reminders?$", re.IGNORECASE),
        lambda m, src: {"action": "reminder", "op": "list"},
    ),
    (
        re.compile(r"^clear\s+reminders?$", re.IGNORECASE),
        lambda m, src: {"action": "reminder", "op": "clear"},
    ),
    (
        re.compile(
            r"^(?:delete|remove)\s+reminder\s+(?P<idx>\d+)$", re.IGNORECASE
        ),
        lambda m, src: {
            "action": "reminder",
            "op": "remove",
            "index": int(m.group("idx")),
        },
    ),
    (
        re.compile(
            r"^(?:create|add|schedule)\s+(?:a\s+)?"
            r"(?P<title>.+?)\s+(?P<date>tomorrow|today|monday|tuesday|"
            r"wednesday|thursday|friday|saturday|sunday|\d{1,2}(?:st|nd|rd|th)?"
            r"\s+\w+|\d{4}-\d{2}-\d{2})\s+at\s+"
            r"(?P<time>\d{1,2}(?::\d{2})?\s*(?:am|pm))$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "calendar_event",
            "title": m.group("title").strip(),
            "date": m.group("date").strip(),
            "time": m.group("time").strip(),
        },
    ),
    (
        re.compile(
            r"^(?:message|whatsapp|send\s+whatsapp(?:\s+message)?\s+to)\s+"
            r"(?P<contact>[a-zA-Z][\w\s]{0,40}?)\s+"
            r"(?:that\s+)?(?P<message>.+)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "whatsapp",
            "contact": m.group("contact").strip(),
            "message": m.group("message").strip(),
        },
    ),
    # "tell <name> <message>" — WhatsApp to a known contact.
    # Only matches explicit names (capitalized words that are not pronouns).
    # Does NOT match "tell me", "tell him", "tell her", "tell them".
    (
        re.compile(
            r"\btell\s+(?P<contact>"
            r"mom|dad|brother|sister|friend|bhajan|"
            r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?"
            r")\s+"
            r"(?:that\s+)?(?P<message>.+?)$",
        ),
        lambda m, src: {
            "action": "whatsapp",
            "contact": m.group("contact").strip(),
            "message": m.group("message").strip(),
        },
    ),
    (
        re.compile(
            r"^(?:email|draft\s+(?:an\s+)?email(?:\s+to)?)\s+"
            r"(?P<recipient>[a-zA-Z][\w\s]{0,40}?)\s+"
            r"(?:about|with|re:)?\s*(?P<subject>.+?)\s+"
            r"saying\s+(?P<body>.+)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "email",
            "recipient": m.group("recipient").strip(),
            "subject": m.group("subject").strip(),
            "body": m.group("body").strip(),
        },
    ),
    (
        re.compile(
            r"^(?:email|draft\s+(?:an\s+)?email(?:\s+to)?)\s+"
            r"(?P<recipient>[a-zA-Z][\w\s]{0,40}?)\s+"
            r"(?:about|with|re:)?\s*(?P<subject>.+)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "email",
            "recipient": m.group("recipient").strip(),
            "subject": m.group("subject").strip(),
            "body": "",
        },
    ),
    # ---------------------------------------------------------------
    # Screen awareness — capture + analyze a screenshot via the
    # configured vision model. A few common phrasings get the fast
    # path; the LLM planner picks up the rest (e.g. "summarize this
    # page", "help me fix this"). Defined BEFORE the web_search /
    # "what is" patterns so phrases like "what's on my screen" route
    # to vision rather than DuckDuckGo.
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^what(?:'s|\s+is)\s+on\s+my\s+screen$|^read\s+my\s+screen$|"
            r"^describe\s+(?:my\s+)?screen$|^describe\s+this\s+page$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "screen_awareness",
            "op": "describe",
        },
    ),
    (
        re.compile(
            r"^(?:analyze|explain)\s+this\s+error$|"
            r"^what\s+error(?:\s+is\s+(?:this|shown))?$|"
            r"^help\s+me\s+(?:fix|solve)\s+this(?:\s+error)?$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "screen_awareness",
            "op": "error",
        },
    ),
    (
        re.compile(
            r"^(?:explain|review)\s+this\s+code$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "screen_awareness",
            "op": "code_review",
        },
    ),
    (
        re.compile(
            r"^(?:read|summarize)\s+this\s+(?:page|document)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "screen_awareness",
            "op": "summarize_document",
        },
    ),
    (
        re.compile(
            r"^(?:search(?:\s+the\s+web)?(?:\s+for)?|look\s+up|"
            r"ask\s+the\s+web|tell\s+me\s+about)\s+(?P<query>.+)$",
            re.IGNORECASE,
        ),
        lambda m, src: (
            None
            if re.search(
                r"\b(?:and|then|after\s+that|also|plus)\s+"
                r"(?:save|open|create|send|remind|search|launch|start)\b",
                m.group("query"), re.IGNORECASE,
            )
            else {"action": "web_search", "query": _strip_query_punctuation(m.group("query"))}
        ),
    ),
    (
        re.compile(
            r"^(?:what\s+is|who\s+is|whats|what's)\s+(?P<query>.+?)\??$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "web_search",
            "query": _strip_query_punctuation(m.group("query")),
        },
    ),
    (
        re.compile(r"^remember\s+that\s+(?P<fact>.+)$", re.IGNORECASE),
        lambda m, src: {"action": "memory_store", "fact": m.group("fact").strip()},
    ),
    (
        re.compile(r"^remember\s+(?P<fact>.+)$", re.IGNORECASE),
        lambda m, src: {"action": "memory_store", "fact": m.group("fact").strip()},
    ),
    (
        re.compile(
            r"^what\s+do\s+you\s+remember$|^recall(?:\s+memory)?$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "memory_recall"},
    ),
    (
        re.compile(
            r"^forget\s+everything$|^clear\s+(?:your\s+)?memory$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "memory_clear"},
    ),

    (
        re.compile(r"^(?:screenshot|take\s+a\s+screenshot|capture\s+screen)$",
                   re.IGNORECASE),
        lambda m, src: {"action": "screenshot"},
    ),

    (
        re.compile(
            r"^volume\s+(?P<dir>up|down|mute|unmute)$", re.IGNORECASE
        ),
        lambda m, src: {"action": "volume_control", "op": m.group("dir").lower()},
    ),
    (
        re.compile(
            r"^set\s+volume\s+to\s+(?P<level>\d+)\s*(?:percent)?%?$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "volume_control",
            "op": "set",
            "level": int(m.group("level")),
        },
    ),
    (
        re.compile(
            r"^(?P<op>play|pause|stop|next|previous|skip)\s+(?:music|song|track)$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "music", "op": m.group("op").lower()},
    ),
    # "play <query> in <app>" — play a specific song/album in a music app.
    (
        re.compile(
            r"^(?:play|search\s+for|find)\s+(?P<query>.+?)\s+"
            r"in\s+(?P<app>apple\s*music|spotify|youtube\s*music|amazon\s*music)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "search_in_app_v2",
            "app": m.group("app").strip(),
            "query": m.group("query").strip(),
            "mode": "click",
        },
    ),
    # "play <query>" (no app specified) — play a specific song via media key.
    (
        re.compile(
            r"^play\s+(?P<query>.+)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "music",
            "op": "play",
            "query": m.group("query").strip(),
        },
    ),
    (
        re.compile(
            r"^(?:lock(?:\s+computer)?|shutdown(?:\s+computer)?|"
            r"restart(?:\s+computer)?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "system_control", "op": m.group(0).lower().split()[0]},
    ),
    # ---------------------------------------------------------------
    # Clipboard: clear (the read/summarize/write patterns are above).
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:clear|empty|wipe)\s+(?:my\s+)?clipboard$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "clipboard", "op": "clear"},
    ),
    # ---------------------------------------------------------------
    # Create file — "create <name>" or "create a file called <name>"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?create\s+(?:a\s+|an\s+)?(?:file\s+)?"
            r"(?:called\s+|named\s+)?(?P<name>[\w.\- ]+?\.\w+)"
            r"(?:\s+(?:in|inside|under)\s+(?P<folder>.+?))?\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: _build_create_file(m),
    ),
    (
        re.compile(
            r"^(?:please\s+)?make\s+(?:a\s+|an\s+)?(?:file\s+)?"
            r"(?:called\s+|named\s+)?(?P<name>[\w.\- ]+?\.\w+)"
            r"(?:\s+(?:in|inside|under)\s+(?P<folder>.+?))?\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: _build_create_file(m),
    ),
    (
        re.compile(
            r"^(?:please\s+)?create\s+(?:a\s+|an\s+)?(?:file\s+)?"
            r"(?:called\s+|named\s+)?(?P<name>[\w.\- ]+?\.\w+)"
            r"\s+(?:with|containing)\s+(?P<content>.+)"
            r"(?:\s+(?:in|inside|under)\s+(?P<folder>.+?))?\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: _build_create_file_with_content(m),
    ),
    # "write a <lang> program that <task>" -> code generation
    (
        re.compile(
            r"^(?:please\s+)?(?:write|create|make)\s+(?:a\s+|an\s+)?"
            r"(?P<name>[\w.\- ]+?\.\w+)"
            r"\s+(?:with|that)\s+(?P<content>.+?)(?:\s+(?:in|inside|under)\s+(?P<folder>.+?))?\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: _build_codegen_from_file(m, src),
    ),
    # ---------------------------------------------------------------

    (
        re.compile(
            r"^(?:please\s+)?read\s+(?:the\s+)?(?:file\s+)?(?P<path>.+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "read_file",
            "path": _strip_file_name(m.group("path")),
        },
    ),

    (
        re.compile(
            r"^(?:please\s+)?delete\s+(?:the\s+)?(?:file\s+)?(?P<path>(?!folder\b)(?!the\s+folder\b).+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "delete_file",
            "path": _strip_file_name(m.group("path")),
        },
    ),
    (
        re.compile(
            r"^(?:please\s+)?rename\s+(?:the\s+)?(?:file\s+)?"
            r"(?P<path>[\w.\- /\\:]+?)\s+to\s+(?P<new_name>[\w.\- ]+)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "rename_file",
            "path": _strip_file_name(m.group("path")),
            "new_name": _strip_file_name(m.group("new_name")),
        },
    ),
    (
        re.compile(
            r"^(?:please\s+)?move\s+(?:the\s+)?(?:file\s+)?"
            r"(?P<path>[\w.\- /\\:]+?)\s+to\s+(?P<dest>.+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "move_file",
            "path": _strip_file_name(m.group("path")),
            "dest_folder": m.group("dest").strip(),
        },
    ),
    (
        re.compile(
            r"^(?:please\s+)?copy\s+(?:the\s+)?(?:file\s+)?"
            r"(?P<path>[\w.\- /\\:]+?)\s+to\s+(?P<dest>.+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "copy_file",
            "path": _strip_file_name(m.group("path")),
            "dest_folder": m.group("dest").strip(),
        },
    ),

    # "write <content> into <path>" — used with pronoun resolution
    (
        re.compile(
            r"^(?:please\s+)?write\s+(?P<content>.+?)\s+into\s+(?P<path>.+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "write_file",
            "path": _strip_file_name(m.group("path")),
            "content": m.group("content").strip(),
        },
    ),
    # "write <content> to <path>" — alternative phrasing
    (
        re.compile(
            r"^(?:please\s+)?write\s+(?P<content>.+?)\s+to\s+(?:the\s+)?(?:file\s+)?(?P<path>.+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "write_file",
            "path": _strip_file_name(m.group("path")),
            "content": m.group("content").strip(),
        },
    ),
    # "write <content> in(to) <path>" — broader match
    (
        re.compile(
            r"^(?:please\s+)?(?:write|put|add)\s+(?P<content>.+?)\s+"
            r"(?:in|into|inside|to)\s+(?:the\s+)?(?:file\s+)?(?P<path>.+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "file_operation",
            "op": "write_file",
            "path": _strip_file_name(m.group("path")),
            "content": m.group("content").strip(),
        },
    ),

    # ---------------------------------------------------------------
    # Folder operations
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?create\s+(?:a\s+|an\s+)?folder\s+(?:called\s+|named\s+)?(?P<name>[\w.\- ]+)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "folder_operation",
            "op": "create_folder",
            "name": m.group("name").strip(),
        },
    ),
    (
        re.compile(
            r"^(?:please\s+)?delete\s+(?:the\s+)?folder\s+(?P<path>.+?)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "folder_operation",
            "op": "delete_folder",
            "path": m.group("path").strip(),
        },
    ),
    (
        re.compile(
            r"^(?:please\s+)?list\s+(?:the\s+)?(?P<path>.+?)\s+folder$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "folder_operation",
            "op": "list_folder",
            "path": m.group("path").strip(),
        },
    ),
    (
        re.compile(
            r"^(?:please\s+)?list\s+(?:my\s+|the\s+)?(?P<path>downloads?|documents?|desktop|home|pictures|videos|music)$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "folder_operation",
            "op": "list_folder",
            "path": m.group("path").strip(),
        },
    ),
    # ---------------------------------------------------------------
    # Focus window — "focus <window>"
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?focus\s+(?:on\s+)?(?:the\s+)?(?P<title>.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {"action": "focus_window", "title": m.group("title").strip()},
    ),
    # ---------------------------------------------------------------
    # Wait for window — "wait for <window>" or "wait for <n> seconds"
    # Must come after the generic "wait <n> seconds" pattern (line ~450).
    # This pattern matches non-numeric targets so it won't steal seconds.
    # ---------------------------------------------------------------
    (
        # This is intentionally after wait <seconds>; this catches
        # non-numeric "wait for <window>" phrases.
        re.compile(
            r"^(?:please\s+)?wait\s+for\s+(?:the\s+)?(?P<title>(?!\d+)\D.+?)\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "wait_for_window",
            "title": m.group("title").strip(),
        },
    ),
    # ---------------------------------------------------------------
    # Hotkey — "press ctrl+s", "press ctrl shift f", "press ctrl+l"
    # Must come AFTER the generic "press <key>" pattern.
    # We detect multi-key combos (2+ words).
    # ---------------------------------------------------------------
    (
        re.compile(
            r"^(?:please\s+)?(?:press|hit)\s+"
            r"(?P<keys>(?:ctrl|alt|shift|win|cmd|meta)[\s+]+[a-z0-9]+)"
            r"(?:\s+(?:and\s+)?(?:then\s+)?(?:press\s+)?(?P<key2>[a-z0-9]+))?"
            r"\s*$",
            re.IGNORECASE,
        ),
        lambda m, src: {
            "action": "hotkey",
            "keys": re.split(r"\s*[\s+]\s*", m.group("keys").strip().lower()),
        },
    ),
]

# Detect overlapping fast-path patterns at module load
_detect_regex_conflicts(_FAST_PATH_TRIGGERS)

# Build keyword index for fast-path pre-filtering
# Extracts the first keyword from each pattern to enable O(1) skip
_FAST_PATH_KEYWORDS: set[str] = set()
for _p, _ in _FAST_PATH_TRIGGERS:
    # Extract first meaningful word from pattern
    pat = _p.pattern
    # Look for literal words at the start (skip non-capturing groups)
    for _m in re.finditer(r"[a-z]{2,}", pat):
        _word = _m.group(0)
        if _word not in ("?:", "please", "s+", "the"):
            _FAST_PATH_KEYWORDS.add(_word)
            break
# Add all known trigger words
_FAST_PATH_KEYWORDS.update({
    "open", "close", "quit", "exit", "go", "switch", "launch", "start",
    "run", "create", "make", "rename", "delete", "remove", "move", "copy",
    "read", "write", "append", "search", "look", "find", "remind", "set",
    "play", "pause", "stop", "next", "previous", "skip", "lock", "shutdown",
    "restart", "take", "capture", "describe", "analyze", "explain", "summarize",
    "remember", "recall", "forget", "clear", "show", "list", "schedule",
    "tell", "message", "email", "draft", "send", "volume", "save", "put",
    "log", "sign", "power", "reboot", "type", "press", "scroll", "click",
    "double", "right", "execute", "generate", "wait", "what", "time",
    "date", "how", "who", "where", "when", "why", "battery", "screenshot",
    "grab", "diagnostics", "stats", "system", "help",
})


def _build_create_file(m: re.Match) -> dict:
    name = _strip_file_name(m.group("name"))
    folder = m.group("folder").strip() if m.group("folder") else ""
    plan = {"action": "file_operation", "op": "create_file", "name": name}
    if folder:
        plan["folder"] = _resolve_path(folder)
    return plan


def _build_create_file_with_content(m: re.Match) -> dict:
    name = _strip_file_name(m.group("name"))
    content = m.group("content").strip()
    folder = m.group("folder").strip() if m.group("folder") else ""
    plan = {"action": "file_operation", "op": "create_file", "name": name, "content": content}
    if folder:
        plan["folder"] = _resolve_path(folder)
    return plan


def _build_codegen_from_file(m: re.Match, src: str) -> dict:
    name = _strip_file_name(m.group("name"))
    content = m.group("content").strip()
    folder = m.group("folder").strip() if m.group("folder") else ""
    ext = os.path.splitext(name)[1].lower()
    lang_map = {".py": "python", ".js": "javascript", ".ts": "typescript",
                 ".cpp": "cpp", ".c": "c", ".java": "java", ".go": "go",
                 ".rs": "rust", ".rb": "ruby", ".php": "php", ".swift": "swift",
                 ".kt": "kotlin", ".sh": "bash", ".bat": "batch", ".ps1": "powershell",
                 ".html": "html", ".css": "css", ".json": "json", ".yaml": "yaml",
                 ".xml": "xml", ".sql": "sql", ".r": "r", ".lua": "lua",
                 ".pl": "perl", ".hs": "haskell", ".ex": "elixir"}
    language = lang_map.get(ext, "")
    steps = [
        {"action": "file_operation", "op": "create_file", "name": name},
        {"action": "generate_code", "description": content, "language": language, "target_file": name},
    ]
    if folder:
        resolved = _resolve_path(folder)
        steps[0]["folder"] = resolved
    return {"steps": steps}


_TRAILING_PUNCTUATION_RE = re.compile(r"[.,!?;:]+$")


def _strip_query_punctuation(query: str) -> str:
    """Remove trailing punctuation from a search query."""
    return _TRAILING_PUNCTUATION_RE.sub("", query).strip()


def _strip_file_name(name: str) -> str:
    """Strip trailing punctuation from a file name (but preserve extension)."""
    name = name.strip()
    # Strip trailing punctuation that isn't part of the extension
    if "." in name:
        base, ext = name.rsplit(".", 1)
        base = _TRAILING_PUNCTUATION_RE.sub("", base).strip()
        ext = _TRAILING_PUNCTUATION_RE.sub("", ext).strip()
        if ext:
            return f"{base}.{ext}"
    return _TRAILING_PUNCTUATION_RE.sub("", name).strip()


def _try_fast_path(user_text: str) -> Optional[dict]:
    src = user_text.strip()
    # Quick keyword pre-filter: check first word against known trigger words
    # This avoids trying all 85 patterns for unrelated inputs
    first_word = src.split()[0].lower() if src.split() else ""
    if first_word and first_word not in _FAST_PATH_KEYWORDS:
        # Still try patterns but skip the expensive ones
        for pattern, builder in _FAST_PATH_TRIGGERS:
            m = pattern.match(src)
            if m:
                result = builder(m, src)
                if result is not None:
                    _METRICS.record(fast_path_hits=1)
                    return result
        _METRICS.record(fast_path_misses=1)
        return None
    for pattern, builder in _FAST_PATH_TRIGGERS:
        m = pattern.match(src)
        if m:
            result = builder(m, src)
            if result is not None:
                _METRICS.record(fast_path_hits=1)
                return result
    _METRICS.record(fast_path_misses=1)
    return None


# ---------------------------------------------------------------------------
# Multi-step infrastructure
# ---------------------------------------------------------------------------
# Context for pronoun resolution within a single plan_action call.
_INITIAL_CONTEXT: dict = {
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

_MULTI_STEP_DETECT_RE = re.compile(
    r"[,;]"
    r"|\b(?:and\s+then|then\s+after\s+that|after\s+that|next|also|finally|followed\s+by|plus)\b"
    r"|\b(?:and|then)\b\s*"
    r"(?=\s*(?:please\s+)?(?:open|launch|start|run|close|quit|exit|switch|go|create|make"
    r"|read|write|append|add|delete|rename|move|copy|search|remind|set|play|pause"
    r"|stop|next|previous|skip|lock|shutdown|restart|take|capture|describe|analyze"
    r"|explain|summarize|remember|recall|forget|clear|show|list|add|schedule|tell"
    r"|message|email|draft|send|volume|save|put|log|sign|power|reboot|type|press"
    r"|scroll|click|double|right|run|execute|generate|wait))"
    # "after X, do Y" patterns
    r"|\bafter\s+.+?(?:,\s*)?(?:please\s+)?(?:open|launch|start|run|close|quit|exit|switch|go|create|make"
    r"|read|write|append|add|delete|rename|move|copy|search|remind|set|play|pause"
    r"|stop|next|previous|skip|lock|shutdown|restart|take|capture|describe|analyze"
    r"|explain|summarize|remember|recall|forget|clear|show|list|add|schedule|tell"
    r"|message|email|draft|send|volume|save|put|log|sign|power|reboot|type|press"
    r"|scroll|click|double|right|run|execute|generate|wait)",
    re.IGNORECASE,
)


def _has_multi_step_intent(text: str) -> bool:
    return bool(_MULTI_STEP_DETECT_RE.search(text))


def _split_clauses(text: str) -> list[str]:
    DELIM = "\x00"

    _VERB_PREFIX = (
        r"(?:please\s+)?"
        r"(?:open|launch|start|run|close|quit|exit|switch|go|create|make|"
        r"read|write|append|add|delete|rename|move|copy|search|remind|set|"
        r"play|pause|stop|next|previous|skip|lock|shutdown|restart|take|"
        r"capture|describe|analyze|explain|summarize|remember|recall|forget|"
        r"clear|show|list|add|schedule|tell|message|email|draft|send|volume|"
        r"save|put|log|sign|power|reboot|type|press|scroll|click|double|"
        r"right|run|execute|generate|wait)"
    )

    def _split_on_boundary_words(t: str) -> list[str]:
        for pat in [
            r"\band\s+then\b",
            r"\bthen\s+after\s+that\b",
            r"\bafter\s+that\b",
            r"\bnext\b",
            r"\balso\b",
            r"\bfinally\b",
            r"\bfollowed\s+by\b",
            r"\bplus\b",
        ]:
            t = re.sub(pat, DELIM, t, flags=re.IGNORECASE)
        for pat in [
            r"\band\b(?=\s*(?:please\s+)?(?:open|launch|start|run|close|quit|exit|switch|go|create|make|read|write|append|add|delete|rename|move|copy|search|remind|set|play|pause|stop|next|previous|skip|lock|shutdown|restart|take|capture|describe|analyze|explain|summarize|remember|recall|forget|clear|show|list|add|schedule|tell|message|email|draft|send|volume|save|put|log|sign|power|reboot|type|press|scroll|click|double|right|run|execute|generate|wait))",
            r"\bthen\b(?=\s*(?:please\s+)?(?:open|launch|start|run|close|quit|exit|switch|go|create|make|read|write|append|add|delete|rename|move|copy|search|remind|set|play|pause|stop|next|previous|skip|lock|shutdown|restart|take|capture|describe|analyze|explain|summarize|remember|recall|forget|clear|show|list|add|schedule|tell|message|email|draft|send|volume|save|put|log|sign|power|reboot|type|press|scroll|click|double|right|run|execute|generate|wait))",
        ]:
            t = re.sub(pat, DELIM, t, flags=re.IGNORECASE)
        return [c.strip() for c in t.split(DELIM) if c.strip()]

    # Phase 1: split on commas / semicolons, but only if the part after
    # the comma looks like a standalone command (starts with a verb).
    raw_parts = re.split(r"\s*[,;]\s*", text)
    parts: list[str] = []
    for i, part in enumerate(raw_parts):
        if i == 0:
            parts.append(part)
        else:
            # Check if this part starts like a command
            if re.match(_VERB_PREFIX, part.strip(), re.IGNORECASE):
                parts.append(part)
            else:
                # Not a command — merge with previous part
                parts[-1] = parts[-1] + ", " + part
    # Phase 2: split each part on boundary words
    result: list[str] = []
    for part in parts:
        result.extend(_split_on_boundary_words(part))
    # Phase 3: clean leading boundary words from each clause
    cleaned: list[str] = []
    for clause in result:
        c = re.sub(
            r"^(?:\s*(?:and\s+then|then\s+after\s+that|after\s+that|then|and|also|finally|next|plus)\s+)+",
            "", clause, flags=re.IGNORECASE,
        ).strip()
        if c:
            cleaned.append(c)
    return cleaned


def _resolve_pronouns(text: str, ctx: dict) -> str:
    result = text
    file_ref = ctx.get("current_file") or ctx.get("last_file", "")
    folder_ref = ctx.get("current_folder") or ctx.get("last_folder", "")
    # Build combined path for "it" when both file and folder are known
    combined_ref: str = file_ref or folder_ref
    if folder_ref and file_ref and "/" not in file_ref and "\\" not in file_ref:
        combined_ref = folder_ref.rstrip("/\\") + "/" + file_ref
    # Resolve "it" — only when not part of a larger word
    if combined_ref:
        result = re.sub(r"(?<![a-zA-Z])it(?![a-zA-Z])", combined_ref, result)
    # Resolve "there" to the current folder
    if folder_ref:
        result = re.sub(r"(?<![a-zA-Z])there(?![a-zA-Z])", folder_ref, result)
    # Resolve "this" to clipboard or screenshot content
    this_val = ctx.get("last_clipboard") or ctx.get("last_screenshot") or ""
    if this_val:
        result = re.sub(r"(?<![a-zA-Z])this(?![a-zA-Z])", this_val, result)
    # Resolve "that" to last search result
    if ctx.get("last_search_result"):
        result = re.sub(r"(?<![a-zA-Z])that(?![a-zA-Z])", ctx["last_search_result"], result)
    # Additional pronoun support
    if combined_ref:
        result = re.sub(r"(?<![a-zA-Z])them(?![a-zA-Z])", combined_ref, result)
    return result


def _update_context_from_plan(ctx: dict, plan: dict) -> None:
    action = plan.get("action", "")
    op = plan.get("op", "")
    folder = plan.get("folder", "")
    if action == "folder_operation":
        if op == "create_folder":
            name = plan.get("name", "")
            ctx["last_folder"] = name
            ctx["current_folder"] = name
        elif op == "rename_folder":
            ctx["last_folder"] = plan.get("new_name", "")
            ctx["current_folder"] = plan.get("new_name", "")
    if action == "file_operation":
        pname = plan.get("name", "")
        ppath = plan.get("path", "")
        if op == "create_file":
            ctx["last_file"] = pname
            ctx["current_file"] = pname
            if folder:
                ctx["current_folder"] = os.path.basename(folder.rstrip("/\\"))
        elif op in ("open_file", "write_file", "append_file", "read_file"):
            ctx["last_file"] = ppath or pname
            ctx["current_file"] = ppath or pname
    if action == "clipboard" and op == "write":
        ctx["last_clipboard"] = plan.get("text", "")
    if action == "open_app":
        app = plan.get("app", "")
        ctx["last_app"] = app
        ctx["current_app"] = app
    if action in ("switch_window",):
        target = plan.get("target", "")
        if target:
            ctx["current_app"] = target
            ctx["current_window"] = target
    if action == "web_search":
        ctx["last_search_result"] = plan.get("query", "")
    if action in ("focus_window", "wait_for_window"):
        title = plan.get("title", "") or plan.get("target", "")
        if title:
            ctx["current_window"] = title
    if action in ("search_in_app", "search_in_app_v2"):
        ctx["current_app"] = plan.get("app", "")
        ctx["current_window"] = plan.get("app", "")


def _plan_single(text: str, use_llm: bool = True) -> dict:
    fast = _try_fast_path(text)
    if fast is not None:
        # Normalize "run <app>" → open_app when program looks like an app name
        if fast.get("action") == "run_program":
            program = fast.get("program", "")
            if (program and re.match(r"^[a-zA-Z][\w\s.\-]*$", program)
                    and "." not in program
                    and "/" not in program and "\\" not in program):
                return {"action": "open_app", "app": program}
        return fast
    if not use_llm:
        return {"action": "ai_chat", "text": text}

    # Phase 1: Classify intent (NEVER generates actions)
    intent = _classify_intent(text)

    # If confidence is too low, ask for clarification
    if intent and intent.get("confidence", 0) < _CONFIDENCE_THRESHOLD:
        goal = intent.get("goal", "")
        logger.info("Low confidence intent (%.2f), asking for clarification",
                     intent.get("confidence", 0))
        _METRICS.record(clarifications=1)
        if goal:
            msg = f"I think you want to {goal}, but I am not entirely sure. Could you please be more specific?"
        else:
            msg = "I am not sure what you want me to do. Could you please rephrase your request?"
        return {"action": "clarification", "question": msg}

    # Phase 2: Resolve intent → capability, then invoke capability handler
    if intent:
        capability = _resolve_capability(intent)
        logger.info("Intent=%s → Capability=%s (conf=%.2f)",
                     intent.get("intent", "?"), capability,
                     intent.get("confidence", 0))
        # Phase 3: Capability handler generates action plan
        plan = _invoke_capability(capability, intent, text)
        if plan:
            validated = _validate_plan(plan)
            if validated is not None:
                return validated

    return {"action": "ai_chat", "text": text}


# ---------------------------------------------------------------------------
# Phase 1: Intent Classification — ONLY classifies, NEVER generates actions
# ---------------------------------------------------------------------------
_INTENT_CLASSIFIER_PROMPT = """You are JARVIS, an intent classifier.

Your ONLY job: identify what the user wants to accomplish.

Output a JSON object with exactly these four fields:
- "intent": one of the following categories:
    "scheduling" — planning schedules, timetables, routines, organizing time
    "project_analysis" — analyzing code, finding files, understanding a project
    "memory" — remembering, recalling, or forgetting information
    "web_search" — searching the internet (not for personal advice)
    "communication" — sending WhatsApp messages or emails to specific people
    "file_management" — creating, reading, writing, deleting, renaming files/folders
    "app_control" — opening, closing, switching applications or windows
    "system_control" — locking, shutting down, restarting, sleeping, volume control
    "media_control" — playing, pausing, skipping music
    "time_date" — asking for the time or date
    "clipboard" — reading, writing, or clearing the clipboard
    "screenshot" — taking a screenshot
    "screen_awareness" — describing or analyzing what's on screen
    "diagnostics" — running system diagnostics
    "code_generation" — generating or writing code
    "terminal_command" — running a terminal/powerShell command
    "desktop_automation" — clicking, typing, pressing keys, scrolling
    "browser" — opening URLs or searching the browser
    "conversation" — general chat, greetings, opinions, jokes, casual talk
    "reminder" — setting alarms, reminders, or timed notifications

- "goal": a short phrase describing what the user wants to accomplish.
    Example: "plan their weekly schedule", "find a project file",
    "send a WhatsApp message to a contact", "search the web for a topic",
    "open an application", "remember a fact", "get the current time".

- "required_capabilities": a list of strings naming the capabilities needed.
    Possible values: "scheduler", "file_search", "code_analysis",
    "memory_store", "web_browser", "communication", "app_launcher",
    "system_commands", "volume_control", "media_player", "clock",
    "clipboard", "screenshot", "screen_awareness", "diagnostics",
    "code_generator", "terminal", "desktop_automation", "browser",
    "file_manager", "general_chat".

- "confidence": a number between 0.0 and 1.0 indicating how certain you are.

CRITICAL RULES:
- NEVER output actions, plan steps, or parameters.
- NEVER use action names like "open_app", "web_search", "memory_store".
- ONLY output the four fields above.
- If unsure, set confidence < 0.5.

EXAMPLES:

User: I have college from 9 to 4:30, gym, assignments and only four hours of free time. Plan my week.
{"intent":"scheduling","goal":"plan their weekly schedule","required_capabilities":["scheduler"],"confidence":0.95}

User: Create a study schedule Monday to Friday.
{"intent":"scheduling","goal":"create a study schedule","required_capabilities":["scheduler"],"confidence":0.95}

User: Remember that my exam is tomorrow.
{"intent":"memory","goal":"remember an exam date","required_capabilities":["memory_store"],"confidence":0.98}

User: Search the web for LangGraph.
{"intent":"web_search","goal":"search the web for LangGraph","required_capabilities":["web_browser"],"confidence":0.97}

User: Send Rahul a WhatsApp message saying I will be late.
{"intent":"communication","goal":"send a WhatsApp message to Rahul","required_capabilities":["communication"],"confidence":0.95}

User: Send an email to John about the project.
{"intent":"communication","goal":"send an email to John","required_capabilities":["communication"],"confidence":0.95}

User: Open Chrome.
{"intent":"app_control","goal":"open Chrome browser","required_capabilities":["app_launcher"],"confidence":0.98}

User: Close Chrome.
{"intent":"app_control","goal":"close Chrome browser","required_capabilities":["app_launcher"],"confidence":0.98}

User: Analyze my repository.
{"intent":"project_analysis","goal":"analyze a code repository","required_capabilities":["file_search","code_analysis"],"confidence":0.92}

User: Find my Jarvis project.
{"intent":"project_analysis","goal":"find the Jarvis project","required_capabilities":["file_search"],"confidence":0.90}

User: What time is it?
{"intent":"time_date","goal":"check the current time","required_capabilities":["clock"],"confidence":0.99}

User: Mute.
{"intent":"system_control","goal":"mute system volume","required_capabilities":["volume_control"],"confidence":0.98}

User: Hello Jarvis.
{"intent":"conversation","goal":"greet the assistant","required_capabilities":["general_chat"],"confidence":0.99}

User: How do I center a div in CSS?
{"intent":"conversation","goal":"ask about CSS centering","required_capabilities":["general_chat"],"confidence":0.85}

User: Play some music.
{"intent":"media_control","goal":"play music","required_capabilities":["media_player"],"confidence":0.95}

User: Play annul mele in apple music.
{"intent":"media_control","goal":"play a specific song in Apple Music","required_capabilities":["media_player"],"confidence":0.95}

User: Set a reminder in 3 minutes to sleep.
{"intent":"reminder","goal":"set a timed reminder","required_capabilities":["reminder"],"confidence":0.98}

User: Remind me in 10 minutes to check the oven.
{"intent":"reminder","goal":"set a timed reminder","required_capabilities":["reminder"],"confidence":0.98}

Output ONLY the JSON. No prose, no markdown, no actions.
"""


# LRU-ish intent cache: voice commands repeat often; classify each unique
# phrase once and reuse it (skips a ~1.5 s LLM round trip per repeat).
_intent_cache: dict = {}
_INTENT_CACHE_MAX = 128


def _classify_intent(user_text: str) -> Optional[dict]:
    """Classify user intent. Returns {"intent", "goal", "confidence", "required_capabilities"}
    or None if classification fails. NEVER generates actions."""
    key = user_text.strip().lower()
    cached = _intent_cache.get(key)
    if cached is not None:
        logger.debug("Intent cache hit: %s", key[:60])
        return cached

    resp = _ollama_chat_with_retry(
        model=_get_planner_model(),
        messages=[
            {"role": "system", "content": _INTENT_CLASSIFIER_PROMPT},
            {"role": "user", "content": user_text},
        ],
        temperature=0.0,
        num_predict=200,
    )
    if resp is None:
        logger.warning("Intent classification failed (LLM unavailable)")
        return None
    try:
        raw = resp["message"]["content"]
        parsed = _extract_json(raw)
        if parsed and isinstance(parsed, dict) and "intent" in parsed:
            if len(_intent_cache) >= _INTENT_CACHE_MAX:
                _intent_cache.clear()
            _intent_cache[key] = parsed
            return parsed
        logger.warning("Intent classification returned invalid JSON: %.200s", raw)
        return None
    except Exception as exc:
        logger.warning("Intent classification parsing failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Phase 2: Capability Resolution — maps intent → capability (middle layer)
# ---------------------------------------------------------------------------
_INTENT_TO_CAPABILITY: dict[str, str] = {
    "conversation": "general_chat",
    "scheduling": "scheduler",
    "project_analysis": "file_search",
    "memory": "memory_store",
    "web_search": "web_browser",
    "communication": "communication",
    "app_control": "app_launcher",
    "system_control": "system_commands",
    "media_control": "media_player",
    "time_date": "clock",
    "clipboard": "clipboard",
    "screenshot": "screenshot",
    "screen_awareness": "screen_awareness",
    "diagnostics": "diagnostics",
    "code_generation": "code_generator",
    "terminal_command": "terminal",
    "desktop_automation": "desktop_automation",
    "browser": "browser",
    "file_management": "file_manager",
    "reminder": "reminder",
}

_CAPABILITY_HANDLERS: dict[str, Callable[[dict, str], Optional[dict]]] = {}


def _capability(name: str):
    """Decorator to register a capability handler function."""
    def decorator(fn):
        _CAPABILITY_HANDLERS[name] = fn
        return fn
    return decorator


def _resolve_capability(intent: dict) -> str:
    """Map classified intent to the capability that should handle it.
    Prefers required_capabilities over the default intent→capability map."""
    # First, check if any required_capability maps to a registered handler
    req = intent.get("required_capabilities", [])
    for cap in req:
        if cap in _CAPABILITY_HANDLERS:
            return cap
    # Fall back to intent → capability map
    return _INTENT_TO_CAPABILITY.get(intent.get("intent", ""), "general_chat")


def _invoke_capability(capability: str, intent: dict, user_text: str) -> Optional[dict]:
    """Dispatch to a registered capability handler.
    Handler receives (intent, user_text) and returns an action plan dict."""
    handler = _CAPABILITY_HANDLERS.get(capability)
    if handler is None:
        logger.warning("No handler for capability: %s", capability)
        return None
    return handler(intent, user_text)


# ---------------------------------------------------------------------------
# Phase 3: Capability Handlers — each generates actions for ONE domain
# ---------------------------------------------------------------------------

def _cap_llm(prompt: str, text: str) -> Optional[dict]:
    """Call Ollama with a capability-specific system prompt."""
    resp = _ollama_chat_with_retry(
        model=_get_planner_model(),
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ],
        temperature=0.0,
        num_predict=400,
    )
    if resp is None:
        logger.warning("Capability LLM call failed (LLM unavailable)")
        return None
    try:
        raw = resp["message"]["content"]
        return _extract_json(raw)
    except Exception as exc:
        logger.warning("Capability LLM call parsing failed: %s", exc)
        return None


@_capability("general_chat")
def _cap_general_chat(intent: dict, text: str) -> Optional[dict]:
    """Handle general conversation."""
    return _cap_llm(
        "You are JARVIS, a helpful AI assistant.\n"
        "Output a JSON action plan:\n"
        '  {"action": "ai_chat", "text": "<friendly response>"}\n'
        "Output ONLY the JSON. No prose, no markdown.",
        text,
    )


@_capability("scheduler")
def _cap_scheduler(intent: dict, text: str) -> Optional[dict]:
    """Handle scheduling and time-planning requests."""
    return _cap_llm(
        "You are JARVIS, a scheduling assistant. The user wants to plan their time.\n"
        "Output a JSON action plan:\n"
        '  {"action": "ai_chat", "text": "<helpful scheduling response>"}\n'
        "Be helpful, specific, and actionable. Output ONLY the JSON.",
        text,
    )


@_capability("file_search")
def _cap_file_search(intent: dict, text: str) -> Optional[dict]:
    """Handle project analysis and file search requests."""
    return _cap_llm(
        "You are JARVIS, a file-search assistant. Extract the search target.\n"
        "Output a JSON action plan:\n"
        '  {"action": "file_operation", "op": "search_files", "query": "<what to find>"}\n'
        "Output ONLY the JSON.",
        text,
    )


@_capability("web_browser")
def _cap_web_browser(intent: dict, text: str) -> Optional[dict]:
    """Handle web search requests."""
    return _cap_llm(
        "You are JARVIS, a web search assistant. Extract the search query.\n"
        "Output a JSON action plan:\n"
        '  {"action": "web_search", "query": "<search query>"}\n'
        "Output ONLY the JSON.",
        text,
    )


@_capability("communication")
def _cap_communication(intent: dict, text: str) -> Optional[dict]:
    """Handle WhatsApp and email requests."""
    return _cap_llm(
        "You are JARVIS, a messaging assistant. Determine if the user wants to send "
        "a WhatsApp message or an email.\n"
        "For WhatsApp:\n"
        '  {"action": "whatsapp", "contact": "<name>", "message": "<message>"}\n'
        "For Email:\n"
        '  {"action": "email", "recipient": "<name>", "subject": "<subject>", "body": "<body>"}\n'
        "Output ONLY the JSON.",
        text,
    )


@_capability("app_launcher")
def _cap_app_launcher(intent: dict, text: str) -> Optional[dict]:
    """Handle app open/close requests."""
    return _cap_llm(
        "You are JARVIS, an app control assistant. Determine if the user wants to "
        "open or close an application.\n"
        "For opening:\n"
        '  {"action": "open_app", "app": "<app name>"}\n'
        "For closing:\n"
        '  {"action": "close_app", "app": "<app name>"}\n'
        "Output ONLY the JSON.",
        text,
    )


@_capability("system_commands")
def _cap_system_commands(intent: dict, text: str) -> Optional[dict]:
    """Handle system control and volume requests not caught by regex."""
    return _cap_llm(
        "You are JARVIS, a system control assistant.\n"
        "Output a JSON action plan using one of:\n"
        '  {"action": "system_control", "op": "<lock/shutdown/restart/sleep>"}\n'
        '  {"action": "volume_control", "op": "<up/down/mute/unmute/set>", "level": <0-100>}\n'
        "Output ONLY the JSON.",
        text,
    )


@_capability("media_player")
def _cap_media_player(intent: dict, text: str) -> Optional[dict]:
    """Handle music playback requests."""
    t = text.lower()
    # "play <song> in <app>" → search_in_app_v2
    m = re.match(
        r"(?:play|search\s+for|find)\s+(.+?)\s+in\s+"
        r"(apple\s*music|spotify|youtube\s*music|amazon\s*music)\s*$",
        t, re.IGNORECASE,
    )
    if m:
        return {
            "action": "search_in_app_v2",
            "app": m.group(2).strip(),
            "query": m.group(1).strip(),
            "mode": "click",
        }
    # "play <song>" (no app) → music play with query
    m2 = re.match(r"^play\s+(.+)$", t, re.IGNORECASE)
    if m2:
        return {"action": "music", "op": "play", "query": m2.group(1).strip()}
    # Bare toggle
    return _cap_llm(
        "You are JARVIS, a media control assistant.\n"
        "Output a JSON action plan:\n"
        '  {"action": "music", "op": "<play/pause/stop/next/previous>"}\n'
        "Output ONLY the JSON.",
        text,
    )


@_capability("code_generator")
def _cap_code_generator(intent: dict, text: str) -> Optional[dict]:
    """Handle code generation requests."""
    return _cap_llm(
        "You are JARVIS, a code generation assistant.\n"
        "Output a JSON action plan:\n"
        '  {"action": "generate_code", "description": "<what to generate>", "language": "<language>"}\n'
        "Output ONLY the JSON.",
        text,
    )


@_capability("file_manager")
def _cap_file_manager(intent: dict, text: str) -> Optional[dict]:
    """Handle file and folder operations not caught by regex."""
    return _cap_llm(
        "You are JARVIS, a file management assistant.\n"
        "Output a JSON action plan using one of:\n"
        '  {"action": "file_operation", "op": "<op>", "name/path/query": "..."}\n'
        '  {"action": "folder_operation", "op": "<op>", "name/path": "..."}\n'
        "Output ONLY the JSON.",
        text,
    )


@_capability("browser")
def _cap_browser(intent: dict, text: str) -> Optional[dict]:
    """Handle browser navigation and search requests."""
    return _cap_llm(
        "You are JARVIS, a browser control assistant.\n"
        "Output a JSON action plan using one of:\n"
        '  {"action": "browser_open", "url": "<url>"}\n'
        '  {"action": "browser_search", "query": "<query>"}\n'
        "Output ONLY the JSON.",
        text,
    )


@_capability("terminal")
def _cap_terminal(intent: dict, text: str) -> Optional[dict]:
    """Handle terminal command requests."""
    return _cap_llm(
        "You are JARVIS, a terminal assistant.\n"
        "Output a JSON action plan:\n"
        '  {"action": "run_terminal_command", "command": "<command>"}\n'
        "Output ONLY the JSON.",
        text,
    )


@_capability("desktop_automation")
def _cap_desktop_automation(intent: dict, text: str) -> Optional[dict]:
    """Handle mouse/keyboard automation requests not caught by regex."""
    return _cap_llm(
        "You are JARVIS, a desktop automation assistant.\n"
        "Output a JSON action plan using one of:\n"
        '  {"action": "type_text", "text": "..."}\n'
        '  {"action": "press_key", "key": "..."}\n'
        '  {"action": "click", "x": <num>, "y": <num>}\n'
        '  {"action": "scroll", "direction": "<up/down>", "amount": <num>}\n'
        "Output ONLY the JSON.",
        text,
    )


# Simple capabilities — no LLM needed (mostly caught by regex fast-path anyway)

@_capability("clock")
def _cap_clock(intent: dict, text: str) -> Optional[dict]:
    """Handle time/date queries."""
    t = text.lower()
    if "date" in t:
        return {"action": "date"}
    return {"action": "time"}


@_capability("screenshot")
def _cap_screenshot(intent: dict, text: str) -> Optional[dict]:
    return {"action": "screenshot"}


@_capability("diagnostics")
def _cap_diagnostics(intent: dict, text: str) -> Optional[dict]:
    return {"action": "diagnostics"}


@_capability("clipboard")
def _cap_clipboard(intent: dict, text: str) -> Optional[dict]:
    """Handle clipboard queries."""
    t = text.lower()
    if "clear" in t or "empty" in t or "wipe" in t:
        return {"action": "clipboard", "op": "clear"}
    if "write" in t or "copy" in t or "put" in t:
        return {"action": "clipboard", "op": "write", "text": text}
    return {"action": "clipboard", "op": "read"}


@_capability("screen_awareness")
def _cap_screen_awareness(intent: dict, text: str) -> Optional[dict]:
    """Handle screen awareness / vision requests."""
    t = text.lower()
    if "error" in t:
        return {"action": "screen_awareness", "op": "error"}
    if "code" in t or "review" in t:
        return {"action": "screen_awareness", "op": "code_review"}
    if "summarize" in t or "document" in t or "page" in t:
        return {"action": "screen_awareness", "op": "summarize_document"}
    return {"action": "screen_awareness", "op": "describe"}


@_capability("memory_store")
def _cap_memory_store(intent: dict, text: str) -> Optional[dict]:
    """Handle memory storage / recall requests."""
    t = text.lower()
    if "recall" in t or "remember" in t or "what do you" in t:
        return {"action": "memory_recall"}
    if "forget" in t or "clear" in t:
        return {"action": "memory_clear"}
    return {"action": "memory_store", "fact": text}


@_capability("reminder")
def _cap_reminder(intent: dict, text: str) -> Optional[dict]:
    """Handle reminder/alarm requests."""
    return _cap_llm(
        "You are JARVIS, a reminder assistant. Extract the time and task from the user's request.\n"
        "Output a JSON action plan:\n"
        '  {"action": "reminder", "time": "<relative time like in 3 minutes, or absolute like tomorrow 9am>", '
        '"task": "<what to remind about>"}\n'
        "Output ONLY the JSON.",
        text,
    )


# ---------------------------------------------------------------------------
# Multi-step Task Decomposition
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
{"steps":[
  {"action":"file_operation","op":"search_files","query":"Jarvis project"},
  {"action":"file_operation","op":"search_files","query":"Jarvis project main files"},
  {"action":"ai_chat","text":"I found the Jarvis project. Let me identify the most important files to get started."},
  {"action":"file_operation","op":"read_file","path":"main.py"},
  {"action":"file_operation","op":"read_file","path":"planner.py"},
  {"action":"ai_chat","text":"Based on the project structure, I recommend starting with main.py for the entry point..."}
]}

User: Open calculator and create a reminder to stop studying in 2 minutes.
Objective: Set up a study timer.
{"steps":[
  {"action":"open_app","app":"calculator"},
  {"action":"reminder","time":"in 2 minutes","task":"stop studying"}
]}

User: Open Chrome, search for weather.
Objective: Check the weather online.
{"steps":[
  {"action":"open_app","app":"Chrome"},
  {"action":"web_search","query":"weather"}
]}

User: Remind me about my meeting and send an email to the team.
Objective: Manage a meeting reminder and notify team members.
{"steps":[
  {"action":"reminder","time":"","task":"meeting reminder"},
  {"action":"email","recipient":"team","subject":"meeting","body":"Reminder about our meeting"}
]}

User: Search the web for AI news and save the results to a file.
Objective: Gather and store information about AI developments.
{"steps":[
  {"action":"web_search","query":"AI news"},
  {"action":"ai_chat","text":"I will save the AI news results to a file for you."}
]}

User: Open Spotify, play some music and set volume to 30.
Objective: Start listening to music at a comfortable volume.
{"steps":[
  {"action":"open_app","app":"Spotify"},
  {"action":"music","op":"play"},
  {"action":"volume_control","op":"set","level":30}
]}

User: Play annul mele in apple music.
Objective: Play a specific song in Apple Music.
{"steps":[
  {"action":"search_in_app_v2","app":"apple music","query":"annul mele","mode":"click"}
]}

User: Set a reminder in 3 minutes to sleep.
Objective: Set a timed reminder.
{"steps":[
  {"action":"reminder","time":"in 3 minutes","task":"sleep"}
]}

CRITICAL RULES:
- Understand the OBJECTIVE, not just split the sentence.
- "Tell me where to start" -> analyze and recommend (ai_chat). NEVER route to whatsapp.
- "Open the important files" -> find them first, then open.
- Decompose into MEANINGFUL sub-tasks that form a coherent workflow.
- Each step must use a valid action from the list above.
- Use ai_chat for analytical, explanatory, or conversational steps ONLY.
- Do NOT use whatsapp unless the user explicitly asks to message someone.
- Do NOT use ai_chat for music playback — use the "music" action with "op" field.
- Do NOT use ai_chat for reminders/timers — use the "reminder" action with "time" and "task" fields.
- For "play [song] in [app]" — use "search_in_app_v2" with the app name and song query.
- For "set a reminder in [time] to [task]" — use "reminder" with the time and task.
- Output ONLY the JSON. No prose, no markdown, no explanation.
"""


def _decompose_multi_step(user_text: str) -> Optional[dict]:
    """Use LLM to decompose a complex request into logical steps.
    Returns {"steps": [...]} or None if decomposition fails."""
    resp = _ollama_chat_with_retry(
        model=_get_planner_model(),
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
        parsed = _extract_json(raw)
        if parsed and isinstance(parsed, dict):
            steps = parsed.get("steps", [])
            if isinstance(steps, list) and len(steps) >= 2:
                cleaned: list[dict] = []
                for step in steps:
                    if isinstance(step, dict) and step.get("action"):
                        cleaned.append(step)
                if len(cleaned) >= 2:
                    logger.info("LLM-decomposed %d steps for: %s",
                                len(cleaned), user_text[:80])
                    _METRICS.record(multi_step_plans=1)
                    return {"steps": cleaned}
        logger.warning("Multi-step decomposition returned invalid structure: %.200s", raw)
        return None
    except Exception as exc:
        logger.warning("Multi-step decomposition parsing failed: %s", exc)
        return None


_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def _extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of `text` and parse it. Returns None
    if no valid JSON is found."""
    if not text:
        return None
    match = _JSON_OBJECT_RE.search(text)
    candidate = match.group(0) if match else text.strip()
    # Try strict first, then a light repair, then aggressive repair.
    for attempt in (candidate, _light_json_repair(candidate), _aggressive_json_repair(candidate)):
        if not attempt or not attempt.strip():
            continue
        try:
            return json.loads(attempt)
        except json.JSONDecodeError:
            continue
    logger.warning("Failed to extract valid JSON from: %.200s", text)
    return None


def _light_json_repair(text: str) -> str:
    """Common small fixes: trailing commas, single quotes, smart quotes."""
    out = text
    out = re.sub(r",\s*([}\]])", r"\1", out)  # trailing commas
    out = out.replace("“", '"').replace("”", '"')
    out = out.replace("‘", "'").replace("’", "'")
    # Replace single-quoted strings with double-quoted (very conservative).
    out = re.sub(r"'([^'\n]+)'\s*:", r'"\1":', out)
    out = re.sub(r":\s*'([^'\n]+)'", r': "\1"', out)
    return out


def _aggressive_json_repair(text: str) -> str:
    """More aggressive JSON repair: fix unquoted keys, values, Python literals."""
    out = text.strip()
    if not out:
        return out
    # Remove leading/trailing non-JSON garbage
    first_brace = out.find("{")
    last_brace = out.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        out = out[first_brace:last_brace + 1]
    # Fix unquoted keys (conservative: only alphanumeric keys preceded by { or ,)
    out = re.sub(r"([{,]\s*)([a-zA-Z_]\w*)\s*:", r'\1"\2":', out)
    # Fix Python literals (before value quoting so True/False/None stay bare)
    out = re.sub(r"\bTrue\b", "true", out)
    out = re.sub(r"\bFalse\b", "false", out)
    out = re.sub(r"\bNone\b", "null", out)
    # Fix unquoted string values (alphanumeric identifiers after ': ')
    # Match colon-space then an unquoted identifier, but not true/false/null/numbers
    out = re.sub(
        r'(:\s*)([a-zA-Z_][a-zA-Z0-9_]*)(?=\s*[,}])',
        lambda m: m.group(1) + '"' + m.group(2) + '"'
        if m.group(2).lower() not in ("true", "false", "null")
        else m.group(1) + m.group(2).lower(),
        out,
    )
    return out


# ---------------------------------------------------------------------------
# Plan Validation
# ---------------------------------------------------------------------------

# Required parameters for each action type (top-level)
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
    "open_folder": ["path"],
    "clarification": ["question"],
}

# Op-specific additional required params (action → op → [params])
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
_DELETE_ACTIONS: set[str] = {"delete_file", "delete_folder", "rename_file", "rename_folder",
                              "move_file"}

# Invalid parameter combinations (action, param1, param2, reason)
_INVALID_COMBOS: list[tuple[str, str, str, str]] = [
    ("volume_control", "op", "level",
     "volume_control with op='set' requires 'level' parameter"),
    ("reminder", "index", "time",
     "reminder: 'index' and 'time' cannot both be set"),
]


def _validate_numeric_param(name: str, value: object, index: int, action: str, issues: list[str]) -> bool:
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


def _validate_single_step(step: dict, index: int, issues: list[str]) -> Optional[dict]:
    """Validate a single action step. Returns the step or None if invalid.
    Appends warnings to `issues` for non-fatal problems."""
    action = step.get("action")
    if not action:
        issues.append(f"Step {index}: missing 'action' field")
        return None
    if action not in SUPPORTED_ACTIONS and action not in _TOOL_REGISTRY:
        issues.append(f"Step {index}: unsupported action '{action}'")
        return None

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
            # Empty set → whole action is dangerous
            issues.append(
                f"Step {index} ({action}): dangerous operation — requires confirmation"
            )
        elif op in dangerous_ops:
            issues.append(
                f"Step {index} ({action}/{op}): dangerous operation — requires confirmation"
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


def _check_duplicate_steps(steps: list[dict], issues: list[str]) -> None:
    """Detect identical consecutive steps."""
    for i in range(1, len(steps)):
        if steps[i] == steps[i - 1]:
            issues.append(
                f"Steps {i - 1} and {i} are identical duplicates: {steps[i]}"
            )


def _check_cross_resource_conflicts(steps: list[dict], issues: list[str]) -> None:
    """Detect steps that create a resource and later delete it, or similar conflicts."""
    created: dict[str, int] = {}  # resource_name -> step index
    for i, step in enumerate(steps):
        action = step.get("action", "")
        op = step.get("op", "")
        if action == "file_operation" and op in _CREATE_ACTIONS:
            name = step.get("name", "")
            if name:
                created.setdefault(name, i)
        if action in ("file_operation", "folder_operation") and op in _DELETE_ACTIONS:
            target = step.get("name", "") or step.get("path", "")
            if target and target in created:
                issues.append(
                    f"Step {i} ({action}/{op}) deletes/modifies '{target}' "
                    f"created in step {created[target]}"
                )


def _check_step_ordering(steps: list[dict], issues: list[str]) -> None:
    """Flag suspicious step ordering (e.g. write to a file before creating it)."""
    # Track created resources
    exists_after: set[str] = set()
    for i, step in enumerate(steps):
        action = step.get("action", "")
        op = step.get("op", "")
        name = step.get("name", "") or step.get("path", "")
        if action == "file_operation" and op in _CREATE_ACTIONS and name:
            exists_after.add(name)
        if action == "file_operation" and op == "write_file" and name:
            if name not in exists_after:
                # Non-fatal — the file might already exist on disk
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
    issues: list[str] = []

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
        if len(steps) > _MAX_STEPS:
            issues.append(
                f"Plan exceeds maximum step count ({len(steps)} > {_MAX_STEPS})"
            )
            result["valid"] = False
            result["issues"] = issues
            return result

        cleaned: list[dict] = []
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
                if (cleaned[i].get("action") == "open_app"
                        and cleaned[j].get("action") == "open_app"
                        and cleaned[i].get("app") == cleaned[j].get("app")):
                    issues.append(
                        f"Steps {i} and {j}: both open the same app '{cleaned[i].get('app')}'"
                    )

    else:
        v = _validate_single_step(plan, 0, issues)
        if v is None:
            result["valid"] = False

    result["issues"] = issues
    # NOTE: fatal errors (missing action, unsupported action, missing required
    # params) already set valid=False via the `if v is None` check above.
    # The post-step checks (duplicate, cross-resource, ordering) only emit
    # warnings and must NOT invalidate the plan.
    return result


def _validate_plan(plan: dict) -> Optional[dict]:
    """Internal validator. Returns the plan if valid, None if invalid.
    Logs all issues. Backward-compatible with existing callers."""
    report = validate_plan(plan)
    for issue in report["issues"]:
        logger.warning("Plan validation: %s", issue)
    if not report["valid"]:
        _METRICS.record(validation_failures=1)
        return None
    return plan


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

    text = _sanitise_input(user_text)

    # If circuit breaker is open, skip LLM path entirely
    if _CIRCUIT_BREAKER.is_open:
        logger.info("Circuit breaker open — forcing regex-only path")
        use_llm = False

    # Apply speech correction (lazy-loaded)
    _sc = _get_speech_correction()
    if _sc is not None:
        corrected = _sc.correct(text)
        if corrected != text:
            logger.info("Speech correction: '%s' -> '%s'", text, corrected)
        text = corrected

    # Check for incomplete commands (clarification handler)
    clarification = _needs_clarification(text)
    if clarification is not None:
        logger.info("Clarification needed: %s", clarification["question"])
        return clarification

    # Multi-step path: use LLM decomposition for logical task planning,
    # fall back to syntactic clause splitting if LLM unavailable.
    if _has_multi_step_intent(text):
        if use_llm:
            decomposed = _decompose_multi_step(text)
            if decomposed is not None and "steps" in decomposed:
                report = validate_plan(decomposed)
                if report["valid"]:
                    logger.info("LLM-decomposed multi-step plan (%d steps) for: %s",
                                len(decomposed["steps"]), text[:100])
                    return decomposed
                logger.info("LLM decomposition invalid, falling back to syntax: %s",
                            "; ".join(report["issues"]))
        # Fall back to syntactic splitting
        clauses = _split_clauses(text)
        if len(clauses) > 1:
            local_ctx = dict(_INITIAL_CONTEXT)
            # Load current_app from session memory (Issue 7)
            try:
                import session_memory as _sm
                ctx_app = _sm.get("current_app")
                if ctx_app:
                    local_ctx["current_app"] = ctx_app
            except Exception:
                pass
            steps: List[dict] = []
            for clause in clauses:
                resolved = _resolve_pronouns(clause, local_ctx)
                plan = _plan_single(resolved, use_llm=use_llm)
                # Route bare "search X" after open_app to search_in_app_v2,
                # but only if the clause doesn't mention "the web".
                prev_app = (steps[-1].get("app", "")
                            if steps and steps[-1].get("action") == "open_app"
                            else local_ctx.get("current_app", ""))
                if (plan.get("action") == "web_search"
                        and prev_app
                        and "search" in clause.lower()[:10]
                        and "web" not in clause.lower()[:20]
                        and not re.search(r"\bin\b", clause.lower())):
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
            logger.info("Multi-step plan (%d steps) generated for: %s", len(steps), text[:100])
            return {"steps": steps}

    # Single-action path
    plan = _plan_single(text, use_llm=use_llm)
    # Route standalone "search for X" to search_in_app_v2 ONLY when
    # a current_app is active AND the user isn't asking for the web
    # ("search the web for X" should stay as web_search).
    if (plan.get("action") == "web_search"
            and "search" in text.lower()[:10]
            and "web" not in text.lower()[:20]):
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
    report = validate_plan(plan)
    if not report["valid"]:
        msg = "; ".join(report["issues"]) if report["issues"] else "Invalid plan"
        logger.warning("execute_plan rejected: %s", msg)
        return f"I cannot execute that plan, sir. Invalid: {msg}"
    # Lazy import to avoid circular dependency at module load
    try:
        from task_executor import execute_plan as _executor_execute_plan
        return _executor_execute_plan(plan)
    except ImportError as exc:
        logger.error("Failed to import task_executor: %s", exc)
        return "I cannot execute plans right now, sir. The executor is unavailable."


def warmup_model():
    """Pre-warm the LLM model in background to eliminate cold-start latency.
    Call this on startup in a background thread."""
    import threading
    def _warm():
        try:
            client = _get_ollama_client()
            model = _get_planner_model()
            client.chat(
                model=model,
                messages=[{"role": "user", "content": "hi"}],
                options={"num_predict": 1},
            )
            logger.info("Model warm-up complete: %s", model)
        except Exception as exc:
            logger.warning("Model warm-up failed: %s", exc)
    threading.Thread(target=_warm, daemon=True, name="model-warmup").start()


# ---------------------------------------------------------------------------
# Late initialisation — called once during module setup
# ---------------------------------------------------------------------------
_log_handler_coverage()
