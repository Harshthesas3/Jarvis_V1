"""Persistent, thread-safe storage for background jobs."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from typing import Dict, List, Optional

from jarvis.jobs.model import Job, JobStatus

logger = logging.getLogger("jarvis.jobs.store")


def default_store_path() -> str:
    data_dir = os.environ.get("JARVIS_DATA_DIR", os.path.join(os.getcwd(), "data"))
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "jobs.db")


class JobStore:
    """SQLite-backed job persistence.

    A single connection guarded by an RLock is used for in-process
    access; WAL mode keeps concurrent writers safe.
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS jobs (
        job_id      TEXT PRIMARY KEY,
        kind        TEXT NOT NULL,
        params      TEXT NOT NULL,
        workspace   TEXT,
        status      TEXT NOT NULL,
        progress    REAL NOT NULL DEFAULT 0,
        message     TEXT NOT NULL DEFAULT '',
        logs        TEXT NOT NULL DEFAULT '[]',
        error       TEXT,
        created_at  TEXT NOT NULL,
        started_at  TEXT,
        finished_at TEXT
    );
    """

    def __init__(self, path: Optional[str] = None) -> None:
        self._path = path or default_store_path()
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(self._SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def create(self, job: Job) -> Job:
        with self._lock:
            self._conn.execute(
                "INSERT INTO jobs (job_id, kind, params, workspace, status, progress, message, logs, error, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    job.job_id,
                    job.kind,
                    json.dumps(job.params),
                    job.workspace,
                    job.status.value,
                    job.progress,
                    job.message,
                    json.dumps(job.logs),
                    job.error,
                    job.created_at,
                ),
            )
            self._conn.commit()
        return job

    def save(self, job: Job) -> Job:
        with self._lock:
            self._conn.execute(
                "UPDATE jobs SET kind=?, params=?, workspace=?, status=?, progress=?, message=?, logs=?, error=?, "
                "started_at=?, finished_at=? WHERE job_id=?",
                (
                    job.kind,
                    json.dumps(job.params),
                    job.workspace,
                    job.status.value,
                    job.progress,
                    job.message,
                    json.dumps(job.logs),
                    job.error,
                    job.started_at,
                    job.finished_at,
                    job.job_id,
                ),
            )
            self._conn.commit()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def list(self, status: Optional[JobStatus] = None, limit: int = 100) -> List[Job]:
        with self._lock:
            if status is not None:
                rows = self._conn.execute(
                    "SELECT * FROM jobs WHERE status=? ORDER BY created_at DESC LIMIT ?",
                    (status.value, limit),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
        return [self._row_to_job(r) for r in rows]

    def count(self, status: Optional[JobStatus] = None) -> int:
        with self._lock:
            if status is not None:
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM jobs WHERE status=?", (status.value,)
                ).fetchone()
            else:
                row = self._conn.execute("SELECT COUNT(*) FROM jobs").fetchone()
        return int(row[0])

    def delete(self, job_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM jobs WHERE job_id=?", (job_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def purge_old(self, max_age_days: int = 30) -> int:
        cutoff = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        with self._lock:
            cur = self._conn.execute("DELETE FROM jobs WHERE created_at < ?", (cutoff,))
            self._conn.commit()
        return cur.rowcount

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        def col(name: str) -> Optional[str]:
            idx = row.keys().index(name)
            return row[idx]

        return Job(
            job_id=col("job_id"),
            kind=col("kind"),
            params=json.loads(col("params") or "{}"),
            workspace=col("workspace"),
            status=JobStatus(col("status")),
            progress=float(col("progress") or 0),
            message=col("message") or "",
            logs=json.loads(col("logs") or "[]"),
            error=col("error"),
            created_at=col("created_at"),
            started_at=col("started_at"),
            finished_at=col("finished_at"),
        )
