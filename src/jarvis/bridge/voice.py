"""Bridge between the live voice loop and the modular build/jobs system."""

from __future__ import annotations

import logging
import re
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger("jarvis.bridge.voice")

_BUILD_RE = re.compile(
    r"^(?:please\s+)?(?:build|create|make|develop|generate)\s+"
    r"(?:me\s+)?(?:an?\s+|a\s+)?([\w\- ]+?)(?:\s+app|\s+project|\s+tool|\s+site|\s+website|\s+program|\s+game)?\s*$"
)

_SERVICES: Dict[str, Any] = {}
_LOCK = threading.Lock()


def _get_services() -> Dict[str, Any]:
    """Lazily build the job system + build pipeline (import-safe)."""
    with _LOCK:
        if _SERVICES:
            return _SERVICES
        from jarvis.build.engine import BuildPipeline, register_build_handler
        from jarvis.jobs.queue import BackgroundJobQueue
        from jarvis.jobs.service import JobService
        from jarvis.jobs.store import JobStore
        from jarvis.opencode.session import register_default_handler as register_opencode_handler
        from jarvis.workspace.manager import WorkspaceManager

        store = JobStore()
        queue = BackgroundJobQueue(store, event_bus=None, workers=1)
        service = JobService(store, queue)
        workspace_manager = WorkspaceManager()
        pipeline = BuildPipeline(workspace_manager=workspace_manager, event_bus=None)

        register_build_handler(service, pipeline=pipeline)
        register_opencode_handler(service, workspace_manager=workspace_manager)

        _SERVICES["service"] = service
        _SERVICES["pipeline"] = pipeline
        _SERVICES["workspace"] = workspace_manager
        logger.info("Build bridge initialized")
        return _SERVICES


def parse_build_request(text: str) -> Optional[Dict[str, str]]:
    """Extract (name, description) from 'build me a spotify clone' style phrases."""
    if not text or not text.strip():
        return None
    clean = text.strip().lower()
    match = _BUILD_RE.match(clean)
    if not match:
        return None
    name = match.group(1).strip().title()
    if not name or len(name) < 2:
        return None
    return {"name": name, "description": text.strip()}


def submit_build_request(text: str) -> str:
    """Enqueue a background build; returns a TTS-ready acknowledgment."""
    parsed = parse_build_request(text)
    if parsed is None:
        return "I can build an app or project for you, sir. Try saying, build me a Spotify clone."
    name = parsed["name"]
    services = _get_services()
    job = services["service"].submit(
        "build_project",
        {"name": name, "description": parsed["description"]},
    )
    logger.info("Enqueued build job %s for %s", job.job_id, name)
    return (
        f"On it, sir. I have started building {name} in the background. "
        f"It will be at C: Project {name}. I will update the progress as I go."
    )


def build_project_handler(plan: Dict[str, Any]) -> str:
    """Tool handler signature for the live planner: plan -> TTS string."""
    text = str(plan.get("description") or plan.get("text") or "")
    name = str(plan.get("name") or "")
    if name:
        services = _get_services()
        job = services["service"].submit(
            "build_project",
            {"name": name.title(), "description": text},
        )
        logger.info("Enqueued build job %s for %s", job.job_id, name)
        return (
            f"On it, sir. I have started building {name.title()} in the background. "
            f"It will be at C: Project {name.title()}. I will update the progress as I go."
        )
    return submit_build_request(text)
