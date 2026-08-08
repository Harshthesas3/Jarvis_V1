"""Build pipeline orchestrating workspace, documents, and OpenCode."""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any, Callable, Dict, List, Optional

from jarvis.build.requirements import RequirementGatherer
from jarvis.build.specification import SpecGenerator
from jarvis.eventbus import events as ev
from jarvis.interfaces.events import EventBus, EventPriority, SystemEvent
from jarvis.jobs.model import Job
from jarvis.jobs.queue import ProgressReporter
from jarvis.opencode.session import infer_progress, run_opencode_build
from jarvis.workspace.manager import WorkspaceManager

logger = logging.getLogger("jarvis.build.engine")


class BuildPipeline:
    """End-to-end build flow: scaffold → requirements → spec → OpenCode."""

    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        event_bus: Optional[EventBus] = None,
        requirements_gatherer: Optional[RequirementGatherer] = None,
        spec_generator: Optional[SpecGenerator] = None,
    ) -> None:
        self._workspace_manager = workspace_manager
        self._event_bus = event_bus
        self._requirements = requirements_gatherer or RequirementGatherer()
        self._spec = spec_generator or SpecGenerator()

    @property
    def workspace_manager(self) -> WorkspaceManager:
        return self._workspace_manager

    def _publish(self, event_type: str, data: Dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish_async(
                SystemEvent(type=event_type, source="build.engine", priority=EventPriority.NORMAL, data=data)
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to publish build event %s", event_type)

    def prepare_documents(self, workspace: str, name: str, description: str) -> Dict[str, str]:
        """Write requirements.md and spec.md; update progress and publish events."""
        req_path = os.path.join(workspace, "requirements.md")
        spec_path = os.path.join(workspace, "spec.md")

        req_md = self._requirements.generate(name, description)
        with open(req_path, "w", encoding="utf-8") as fh:
            fh.write(req_md)

        spec_md = self._spec.generate(name, req_md)
        with open(spec_path, "w", encoding="utf-8") as fh:
            fh.write(spec_md)

        self._workspace_manager.update_progress(
            workspace,
            step="spec",
            message="Requirements and specification generated",
            progress=40.0,
            status="building",
        )
        self._publish(ev.SPEC_GENERATED, {"name": name, "workspace": workspace})
        return {"requirements": req_path, "spec": spec_path}

    def run(
        self,
        job: Job,
        report: ProgressReporter,
        *,
        opencode_binary: Optional[str] = None,
        opencode_args: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Execute the full build pipeline for a background job."""
        params = job.params
        name = str(params.get("name") or "Project")
        description = str(params.get("description") or "")

        report(5.0, "Creating workspace")
        if not self._workspace_manager.exists(name):
            scaffold = self._workspace_manager.scaffold(name, description)
            workspace = scaffold["path"]
        else:
            workspace = self._workspace_manager.resolve(name)
        job.workspace = workspace

        report(20.0, "Gathering requirements and generating specification")
        self.prepare_documents(workspace, name, description)

        if opencode_binary or opencode_args:
            report(45.0, "Launching build agent")
            return run_opencode_build(
                job,
                report,
                event_bus=self._event_bus,
                workspace_manager=self._workspace_manager,
                opencode_binary=opencode_binary,
                opencode_args=opencode_args,
            )

        instruction = str(params.get("instruction") or f"Build {name}. {description}".strip())
        report(50.0, "Launching OpenCode")
        self._publish(ev.OPENCODE_LAUNCHED, {"job_id": job.job_id, "workspace": workspace})

        from jarvis.opencode.session import OpencodeSession

        session = OpencodeSession(workspace, instruction)
        try:
            session.start()
        except RuntimeError as exc:
            self._workspace_manager.update_progress(workspace, message=str(exc), status="failed")
            self._publish(ev.OPENCODE_FAILED, {"job_id": job.job_id, "workspace": workspace, "error": str(exc)})
            return {"status": "failed", "error": str(exc), "workspace": workspace}

        progress = 50.0
        while session.running:
            if job.is_cancelling:
                session.terminate()
                self._workspace_manager.update_progress(workspace, status="cancelled")
                return {"status": "cancelled", "workspace": workspace}
            for line in session.poll_lines():
                if not line:
                    continue
                job.append_log(line)
                hint = infer_progress(line)
                if hint and hint > progress:
                    progress = hint
                report(progress, line[:200])
            __import__("time").sleep(0.05)

        rc = session.wait()
        if rc != 0:
            self._workspace_manager.update_progress(workspace, message=f"OpenCode exited {rc}", status="failed")
            self._publish(ev.OPENCODE_FAILED, {"job_id": job.job_id, "workspace": workspace, "exit_code": rc})
            return {"status": "failed", "exit_code": rc, "workspace": workspace}

        self._workspace_manager.update_progress(
            workspace,
            step="complete",
            message="Build complete",
            progress=100.0,
            status="completed",
        )
        self._publish(ev.OPENCODE_COMPLETED, {"job_id": job.job_id, "workspace": workspace})
        report(100.0, "Build complete")
        return {"status": "completed", "workspace": workspace}


def register_build_handler(service: Any, *, pipeline: BuildPipeline) -> None:
    """Register the ``build_project`` handler on a JobService."""

    def handler(job: Job, report: ProgressReporter) -> None:
        result = pipeline.run(job, report)
        if result.get("status") not in ("completed",):
            raise RuntimeError(result.get("error") or f"Build failed: {result}")

    service.register_handler("build_project", handler)
