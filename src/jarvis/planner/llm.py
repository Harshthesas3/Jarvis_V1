"""LLM caller with retry, timeout, and JSON extraction/repair utilities."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Optional

from .circuit_breaker import get_circuit_breaker
from .config import (
    LLM_RETRY_DELAY_MS,
    LLM_TIMEOUT_SECONDS,
    MAX_LLM_RETRIES,
)
from .metrics import get_metrics

logger = logging.getLogger("jarvis.planner.llm")

# Persistent ollama client — reuses httpx connection pool (~3.2s saved per call)
_ollama_client = None

def _get_client():
    global _ollama_client
    if _ollama_client is None:
        import ollama as _ollama_mod
        _ollama_client = _ollama_mod.Client()
    return _ollama_client


def llm_chat_with_retry(
    model: str,
    messages: list,
    *,
    temperature: float = 0.0,
    num_predict: int = 400,
    timeout: int | None = None,
) -> dict | None:
    """Call ollama.chat with retry, timeout, and circuit-breaker support."""
    cb = get_circuit_breaker()
    if cb.is_open:
        get_metrics().record(circuit_breaker_hits=1)
        logger.warning("LLM circuit breaker is open — skipping LLM call")
        return None

    if timeout is None:
        timeout = LLM_TIMEOUT_SECONDS

    options = {"temperature": temperature, "num_predict": num_predict}
    last_exc: Exception | None = None

    for attempt in range(MAX_LLM_RETRIES + 1):
        try:
            start = time.monotonic()
            resp = _get_client().chat(model=model, messages=messages, options=options)
            elapsed = (time.monotonic() - start) * 1000.0
            get_metrics().record_llm_call(elapsed)
            cb.record_success()
            return resp
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_LLM_RETRIES:
                get_metrics().record(llm_retries=1)
                logger.warning(
                    "LLM call attempt %d/%d failed: %s. Retrying in %dms...",
                    attempt + 1,
                    MAX_LLM_RETRIES + 1,
                    exc,
                    LLM_RETRY_DELAY_MS,
                )
                time.sleep(LLM_RETRY_DELAY_MS / 1000.0)

    get_metrics().record(llm_failures=1)
    cb.record_failure()
    logger.error("All %d LLM retries exhausted: %s", MAX_LLM_RETRIES + 1, last_exc)
    return None


# ---------------------------------------------------------------------------
# JSON extraction with repair fallbacks
# ---------------------------------------------------------------------------

_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def extract_json(text: str) -> Optional[dict]:
    """Pull the first JSON object out of text and parse it."""
    if not text:
        return None
    match = _JSON_OBJECT_RE.search(text)
    candidate = match.group(0) if match else text.strip()
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
    """Common small fixes: trailing comms, single quotes, smart quotes."""
    out = text
    out = re.sub(r",\s*([}\]])", r"\1", out)  # trailing commas
    out = out.replace("“", '"').replace("”", '"')
    out = out.replace("‘", "'").replace("’", "'")
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
    out = re.sub(
        r'(:\s*)([a-zA-Z_][a-zA-Z0-9_]*)(?=\s*[,}])',
        lambda m: m.group(1) + '"' + m.group(2) + '"'
        if m.group(2).lower() not in ("true", "false", "null")
        else m.group(1) + m.group(2).lower(),
        out,
    )
    return out