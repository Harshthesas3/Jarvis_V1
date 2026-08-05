"""Job domain model for the background job system."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)


@dataclass
class Job:
    """A unit of background work tracked by the job system."""

    job_id: str
    kind: str
    params: Dict[str, Any] = field(default_factory=dict)
    workspace: Optional[str] = None
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    message: str = ""
    logs: List[str] = field(default_factory=list)
    error: Optional[str] = None
    eta_seconds: Optional[float] = None
    created_at: str = field(default_factory=_now_iso)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.status, str):
            self.status = JobStatus(self.status)
        self._cancel_event = threading.Event()

    @property
    def cancel_event(self) -> threading.Event:
        return self._cancel_event

    @property
    def is_cancelling(self) -> bool:
        return self.status == JobStatus.CANCELLING or self._cancel_event.is_set()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "params": self.params,
            "workspace": self.workspace,
            "status": self.status.value,
            "progress": round(self.progress, 2),
            "message": self.message,
            "logs": self.logs,
            "error": self.error,
            "eta_seconds": self.eta_seconds,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Job":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    def append_log(self, line: str, max_logs: int = 200) -> None:
        self.logs.append(line)
        if len(self.logs) > max_logs:
            self.logs = self.logs[-max_logs:]
