"""Facade for the background job system."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable, Dict, List, Optional

from jarvis.jobs.model import Job, JobStatus
from jarvis.jobs.queue import BackgroundJobQueue, JobHandler
from jarvis.jobs.store import JobStore

logger = logging.getLogger("jarvis.jobs.service")


class JobService:
    """High-level job API used by intents, skills and the API layer.

    ``submit`` persists the job and returns immediately; execution
    happens on the background queue while the caller stays responsive.
    """

    def __init__(self, store: JobStore, queue: BackgroundJobQueue) -> None:
        self._store = store
        self._queue = queue

    def submit(
        self,
        kind: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        workspace: Optional[str] = None,
        eta_seconds: Optional[float] = None,
    ) -> Job:
        job = Job(
            job_id=uuid.uuid4().hex[:12],
            kind=kind,
            params=dict(params or {}),
            workspace=workspace,
            eta_seconds=eta_seconds,
        )
        self._store.create(job)
        return self._queue.submit(job)

    def register_handler(self, kind: str, handler: JobHandler) -> None:
        self._queue.register(kind, handler)

    def get(self, job_id: str) -> Optional[Job]:
        return self._store.get(job_id)

    def list(self, status: Optional[JobStatus] = None, limit: int = 100) -> List[Job]:
        return self._store.list(status=status, limit=limit)

    def active(self, limit: int = 100) -> List[Job]:
        active = [s for s in JobStatus if not s.terminal]
        jobs: List[Job] = []
        for status in active:
            jobs.extend(self._store.list(status=status, limit=limit))
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs

    def cancel(self, job_id: str) -> bool:
        return self._queue.cancel(job_id)

    def supports(self, kind: str) -> bool:
        return self._queue.supports(kind)

    def shutdown(self) -> None:
        self._queue.shutdown(wait=False)
        self._store.close()
