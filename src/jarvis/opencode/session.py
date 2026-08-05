"""OpenCode CLI integration: launcher, background session, progress monitor."""

from __future__ import annotations

import logging
import os
import queue
import re
import shutil
import subprocess
import threading
from typing import Any, Dict, List, Optional

from jarvis.eventbus import events as ev
from jarvis.interfaces.events import EventBus, EventPriority, SystemEvent
from jarvis.jobs.model import Job
from jarvis.jobs.queue import ProgressReporter
from jarvis.workspace.manager import WorkspaceManager

logger = logging.getLogger("jarvis.opencode.session")

_PROGRESS_HINTS: List[tuple] = [
    (re.compile(r"(plan(ning)?|planned|map(pe|ping)|outline)", re.IGNORECASE), 20.0),
    (re.compile(r"(writ|edit|apply|creating|generat)", re.IGNORECASE), 45.0),
    (re.compile(r"(test|run|check|lint|build)", re.IGNORECASE), 70.0),
    (re.compile(r"(\u2713|done|complete|finish|success)", re.IGNORECASE), 90.0),
    (re.compile(r"(error|fail(ed|ure))", re.IGNORECASE), 0.0),
]


class OpencodeSession:
    """A single background invocation of the OpenCode CLI in a workspace."""

    def __init__(
        self,
        workspace: str,
        prompt: str,
        *,
        binary: Optional[str] = None,
        extra_args: Optional[List[str]] = None,
    ) -> None:
        self.workspace = workspace
        self.prompt = prompt
        self.binary = binary or os.environ.get("OPENCODE_BIN", "opencode")
        self.extra_args = list(extra_args or [])
        self._process: Optional[subprocess.Popen] = None
        self._lines: "queue.Queue[bytes]" = queue.Queue()
        self._readers: List[threading.Thread] = []

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> "OpencodeSession":
        cmd = [self.binary, "run", self.prompt]
        if self.extra_args:
            cmd = [self.binary, *self.extra_args, self.prompt]
        popen_cmd, resolved = cmd, shutil.which(self.binary)
        if resolved:
            lower = resolved.lower()
            if lower.endswith((".cmd", ".bat")):
                popen_cmd = ["cmd.exe", "/c", *cmd]
            elif lower.endswith(".ps1"):
                popen_cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", resolved, *cmd[1:]]
            else:
                popen_cmd = [resolved, *cmd[1:]]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self._process = subprocess.Popen(
                popen_cmd,
                cwd=self.workspace,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
            )
        except OSError as exc:
            raise RuntimeError(f"Could not find OpenCode binary '{self.binary}': {exc}") from exc
        self._readers.append(threading.Thread(target=self._read_output, daemon=True))
        self._readers[-1].start()
        return self

    def _read_output(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        for raw in iter(self._process.stdout.readline, ""):
            self._lines.put(raw.encode("utf-8", errors="replace"))
        self._lines.put(b"")

    def poll_lines(self, timeout: float = 0.1) -> List[str]:
        """Drain any output produced since the last call."""
        out: List[str] = []
        deadline = __import__("time").monotonic() + timeout
        while True:
            try:
                raw = self._lines.get_nowait()
            except queue.Empty:
                if not out or __import__("time").monotonic() >= deadline:
                    return out
                __import__("time").sleep(0.02)
            else:
                if raw == b"":
                    return out
                out.append(raw.decode("utf-8", errors="replace").rstrip())

    def wait(self) -> int:
        if self._process is None:
            return -1
        rc = self._process.wait()
        for reader in self._readers:
            reader.join(timeout=1.0)
        return rc

    def terminate(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()


def infer_progress(line: str) -> Optional[float]:
    """Heuristic progress estimate from an OpenCode output line."""
    m = re.search(r"(\d{1,3})\s*%", line)
    if m:
        return min(float(m.group(1)), 95.0)
    for pattern, value in _PROGRESS_HINTS:
        if pattern.search(line):
            return value
    return None


def run_opencode_build(
    job: Job,
    report: ProgressReporter,
    *,
    event_bus: Optional[EventBus] = None,
    workspace_manager: Optional[WorkspaceManager] = None,
    opencode_binary: Optional[str] = None,
    opencode_args: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Job handler: scaffold a workspace, launch OpenCode, stream progress.

    Designed to run on the background job queue while the voice loop
    stays responsive.
    """
    params = job.params
    name = str(params.get("name") or "Project")
    description = str(params.get("description") or "")
    instruction = str(params.get("instruction") or f"Build {name}. {description}".strip())

    manager = workspace_manager or WorkspaceManager(event_bus=event_bus)
    workspace = job.workspace or manager.resolve(name)
    if not manager.exists(name):
        report(8.0, "Scaffolding workspace")
        workspace = manager.scaffold(name, description)["path"]
    job.workspace = workspace

    report(12.0, "Launching OpenCode in background")
    _publish(event_bus, ev.OPENCODE_LAUNCHED, {"job_id": job.job_id, "workspace": workspace, "prompt": instruction})

    session = OpencodeSession(workspace, instruction, binary=opencode_binary, extra_args=opencode_args)
    session.start()

    progress = 12.0
    latest = ""
    manager.update_progress(workspace, step="opencode", message="OpenCode running", progress=12.0, status="building")

    try:
        while session.running:
            if job.is_cancelling:
                session.terminate()
                manager.update_progress(workspace, step="opencode", message="Cancelled", status="cancelled")
                _publish(event_bus, ev.OPENCODE_FAILED, {"job_id": job.job_id, "workspace": workspace, "error": "cancelled"})
                return {"status": "cancelled", "workspace": workspace}
            for line in session.poll_lines():
                if not line:
                    continue
                latest = line
                job.append_log(line)
                manager.update_progress(workspace, message=f"OpenCode: {line[:200]}", progress=progress)
                hint = infer_progress(line)
                if hint and hint > progress:
                    progress = hint
                    report(progress, line[:200])
            report(progress, latest[:200])
            __import__("time").sleep(0.05)

        for line in session.poll_lines():
            if line:
                latest = line
                job.append_log(line)

        rc = session.wait()
        manager.update_progress(
            workspace,
            step="opencode",
            message="OpenCode finished",
            progress=95.0,
            status="building",
        )
        if rc != 0:
            manager.update_progress(workspace, message=f"OpenCode exited {rc}", status="failed")
            _publish(event_bus, ev.OPENCODE_FAILED, {"job_id": job.job_id, "workspace": workspace, "exit_code": rc})
            return {"status": "failed", "exit_code": rc, "workspace": workspace, "summary": latest[:500]}

        manager.update_progress(workspace, step="opencode", message="Done", progress=100.0, status="completed")
        _publish(event_bus, ev.OPENCODE_COMPLETED, {"job_id": job.job_id, "workspace": workspace, "exit_code": 0})
        return {"status": "completed", "exit_code": 0, "workspace": workspace, "summary": latest[:500]}
    finally:
        if session.running:
            session.terminate()


def register_default_handler(
    service: Any,
    *,
    event_bus: Optional[EventBus] = None,
    workspace_manager: Optional[WorkspaceManager] = None,
) -> None:
    """Register the 'opencode_build' handler on a JobService."""

    def handler(job: Job, report: ProgressReporter) -> None:
        run_opencode_build(job, report, event_bus=event_bus, workspace_manager=workspace_manager)

    service.register_handler("opencode_build", handler)


def _publish(event_bus: Optional[EventBus], event_type: str, data: Dict[str, Any]) -> None:
    if event_bus is None:
        return
    try:
        event_bus.publish_async(
            SystemEvent(type=event_type, source="opencode.session", priority=EventPriority.NORMAL, data=data)
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to publish opencode event %s", event_type)


def opencode_available() -> bool:
    return shutil.which(os.environ.get("OPENCODE_BIN", "opencode")) is not None