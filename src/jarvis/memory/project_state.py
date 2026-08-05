"""Project-state memory: tracks active projects and unfinished jobs.

This module answers questions like
  - "What are you currently building?"
  - "Did you finish the Spotify clone?"
  - "What was the last thing we were working on?"

It is intentionally thin: it reads the canonical sources of truth
(JobStore and WorkspaceManager) and caches a session-level summary
so the conversation layer can inject it into the LLM context without
repeating expensive I/O.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger("jarvis.memory.project_state")


class ProjectStateMemory:
    """Session-level cache of active projects and unfinished jobs.

    Injected into the LLM system prompt as a compact context block so
    JARVIS never has to say "I don't know what I was doing."

    Parameters
    ----------
    job_service : optional
        A ``jarvis.jobs.service.JobService`` instance.  When present,
        active/unfinished jobs are loaded from it.
    workspace_manager : optional
        A ``jarvis.workspace.manager.WorkspaceManager`` instance.  When
        present, scaffolded projects are discovered automatically.
    """

    def __init__(
        self,
        job_service: Optional[Any] = None,
        workspace_manager: Optional[Any] = None,
    ) -> None:
        self._job_service = job_service
        self._workspace_manager = workspace_manager
        self._lock = threading.RLock()
        # Session-level overrides (e.g. user said "continue Spotify")
        self._active_project: Optional[str] = None
        self._conversation_context: List[Dict[str, str]] = []
        self._dedupe_cache: List[str] = []  # last N response hashes

    # ------------------------------------------------------------------
    # Active project tracking
    # ------------------------------------------------------------------

    def set_active_project(self, name: str) -> None:
        """Mark *name* as the current active project for this session."""
        with self._lock:
            self._active_project = name
        logger.info("Active project set to: %s", name)

    def get_active_project(self) -> Optional[str]:
        """Return the session-active project name, or None."""
        with self._lock:
            return self._active_project

    # ------------------------------------------------------------------
    # Job awareness
    # ------------------------------------------------------------------

    def active_jobs(self) -> List[Dict[str, Any]]:
        """Return a list of currently running/queued jobs (dicts)."""
        if self._job_service is None:
            return []
        try:
            jobs = self._job_service.active()
            return [j.to_dict() for j in jobs]
        except Exception as exc:
            logger.warning("Could not query active jobs: %s", exc)
            return []

    def unfinished_jobs(self) -> List[Dict[str, Any]]:
        """Return jobs that started but did not complete (running + queued)."""
        return self.active_jobs()

    # ------------------------------------------------------------------
    # Project list
    # ------------------------------------------------------------------

    def known_projects(self) -> List[Dict[str, Any]]:
        """Return scaffolded projects visible to the workspace manager."""
        if self._workspace_manager is None:
            return []
        try:
            return self._workspace_manager.list_projects()
        except Exception as exc:
            logger.warning("Could not list projects: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Response deduplication
    # ------------------------------------------------------------------

    def is_duplicate_response(self, text: str, window: int = 5) -> bool:
        """Return True if *text* is too similar to a recent response.

        Prevents JARVIS from saying the same thing twice in a row.  Uses
        a simple normalised lowercase cache rather than embeddings.
        """
        key = " ".join(text.lower().split())[:120]
        with self._lock:
            if key in self._dedupe_cache[-window:]:
                return True
            self._dedupe_cache.append(key)
            if len(self._dedupe_cache) > 50:
                self._dedupe_cache = self._dedupe_cache[-50:]
        return False

    def clear_dedupe(self) -> None:
        """Reset the deduplication window (e.g. on topic change)."""
        with self._lock:
            self._dedupe_cache.clear()

    # ------------------------------------------------------------------
    # Context block for LLM injection
    # ------------------------------------------------------------------

    def build_context_block(self) -> str:
        """Return a compact string summarising current state for LLM injection.

        The output is prepended to the system prompt so JARVIS is always
        aware of what is happening without the user having to re-state it.
        """
        lines: List[str] = []

        active_proj = self.get_active_project()
        if active_proj:
            lines.append(f"Active project: {active_proj}")

        jobs = self.active_jobs()
        if jobs:
            job_strs = [
                f"  - [{j['kind']}] {j.get('message', '')} ({j['status']}, {j.get('progress', 0):.0f}%)"
                for j in jobs[:5]
            ]
            lines.append("Running jobs:\n" + "\n".join(job_strs))

        projects = self.known_projects()
        if projects:
            in_progress = [p for p in projects if p.get("status") not in ("completed", "unknown")]
            if in_progress:
                names = ", ".join(p["name"] for p in in_progress[:5])
                lines.append(f"In-progress workspaces: {names}")

        if not lines:
            return ""

        return "## Current System State\n" + "\n".join(lines)
