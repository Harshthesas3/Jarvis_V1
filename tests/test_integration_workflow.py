"""End-to-end integration test for the Build Spotify workflow."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from jarvis.bridge.voice import parse_build_request, submit_build_request
from jarvis.build.engine import BuildPipeline, register_build_handler
from jarvis.eventbus import events as ev
from jarvis.interfaces.events import SystemEvent
from jarvis.jobs.model import Job, JobStatus
from jarvis.jobs.queue import BackgroundJobQueue
from jarvis.jobs.service import JobService
from jarvis.jobs.store import JobStore
from jarvis.memory.manager import MemoryManager
from jarvis.memory.project_state import ProjectStateMemory
from jarvis.workspace.manager import WorkspaceManager

FAKE_BUILD_SCRIPT = """import sys, time
print("Planning the build")
time.sleep(0.15)
print("Writing modules 50%")
print("Done.")
sys.exit(0)
"""


class RecordingEventBus:
    def __init__(self) -> None:
        self.events: list[SystemEvent] = []

    def publish(self, event: SystemEvent) -> None:
        self.events.append(event)

    def publish_async(self, event: SystemEvent) -> None:
        self.events.append(event)

    def subscribe(self, *args, **kwargs) -> None:
        pass

    def subscribe_all(self, *args, **kwargs) -> None:
        pass

    def register_subscriber(self, *args, **kwargs) -> None:
        pass


class TestBuildSpotifyWorkflow(unittest.TestCase):
    """Validate: Build Spotify → Gather Requirements → Generate Spec →
    Create Workspace → Launch OpenCode → Track Progress → Update Memory →
    Notify User → Resume Later → Continue Automatically
    """

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.project_root = os.path.join(self.tmp, "projects")
        os.makedirs(self.project_root, exist_ok=True)

        fd, self.script_path = tempfile.mkstemp(suffix=".py", dir=self.tmp)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(FAKE_BUILD_SCRIPT)

        self.bus = RecordingEventBus()
        self.workspace = WorkspaceManager(project_root=self.project_root, event_bus=self.bus)
        self.pipeline = BuildPipeline(workspace_manager=self.workspace, event_bus=self.bus)

        db_path = os.path.join(self.tmp, "jobs.db")
        self.store = JobStore(db_path)
        self.queue = BackgroundJobQueue(self.store, event_bus=self.bus, workers=1)
        self.service = JobService(self.store, self.queue)

        def _build_handler(job, report):
            result = self.pipeline.run(
                job,
                report,
                opencode_binary=sys.executable,
                opencode_args=[self.script_path],
            )
            if result.get("status") != "completed":
                raise RuntimeError(result.get("error") or str(result))

        self.service.register_handler("build_project", _build_handler)

        json_path = os.path.join(self.tmp, "memory.json")
        sqlite_path = os.path.join(self.tmp, "memory.db")
        chroma_path = os.path.join(self.tmp, "chroma")
        self.memory = MemoryManager(json_path=json_path, sqlite_path=sqlite_path, chroma_path=chroma_path)
        self.project_state = ProjectStateMemory(job_service=self.service, workspace_manager=self.workspace)

    def tearDown(self) -> None:
        self.queue.shutdown(wait=True)
        self.store.close()
        self.memory.close()

    def _event_types(self) -> list[str]:
        return [e.type for e in self.bus.events]

    def test_parse_build_spotify_request(self) -> None:
        parsed = parse_build_request("build me a spotify clone")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertIn("Spotify", parsed["name"])

    def test_full_workflow(self) -> None:
        # 1. User request: "Build Spotify"
        parsed = parse_build_request("build me a Spotify music app")
        self.assertIsNotNone(parsed)

        job = self.service.submit(
            "build_project",
            {"name": "Spotify", "description": "A Spotify-like music streaming app"},
        )

        # Wait for background completion
        deadline = time.time() + 10.0
        while time.time() < deadline:
            job = self.service.get(job.job_id)
            assert job is not None
            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                break
            time.sleep(0.05)

        self.assertEqual(job.status, JobStatus.COMPLETED, job.error)

        # 2–4. Workspace, requirements, spec
        workspace = job.workspace
        assert workspace is not None
        self.assertTrue(os.path.isdir(workspace))
        self.assertTrue(os.path.exists(os.path.join(workspace, "requirements.md")))
        self.assertTrue(os.path.exists(os.path.join(workspace, "spec.md")))

        progress = self.workspace.read_progress(workspace)
        self.assertEqual(progress["status"], "completed")
        self.assertGreaterEqual(progress["progress"], 100.0)

        # 5–7. OpenCode launch + progress tracking + events
        self.assertIn(ev.WORKSPACE_CREATED, self._event_types())
        self.assertIn(ev.SPEC_GENERATED, self._event_types())

        # 8. Update memory
        self.memory.project.register_project("Spotify", workspace, metadata={"description": "Music app"})
        projects = self.memory.project.list_projects()
        self.assertTrue(any(p.get("name") == "Spotify" for p in projects))

        # 9. Notify user (job progress events published)
        self.assertIn(ev.JOB_STARTED, self._event_types())
        self.assertIn(ev.JOB_COMPLETED, self._event_types())

        # 10–11. Resume later → continue automatically
        self.project_state.set_active_project("Spotify")
        ctx = self.project_state.build_context_block()
        self.assertIn("Spotify", ctx)

        # Re-run prepare_documents simulates resume/continue
        docs = self.pipeline.prepare_documents(workspace, "Spotify", "Continued build")
        self.assertTrue(os.path.exists(docs["spec"]))

    def test_pipeline_run_with_mock_opencode(self) -> None:
        job = Job(job_id="wf1", kind="build_project", params={"name": "Spotify", "description": "Music app"})
        reports: list[tuple[float, str | None]] = []

        def report(p: float, msg: str | None = None) -> None:
            reports.append((p, msg))

        result = self.pipeline.run(
            job,
            report,
            opencode_binary=sys.executable,
            opencode_args=[self.script_path],
        )
        self.assertEqual(result["status"], "completed")
        self.assertTrue(any(r[0] >= 40 for r in reports))


if __name__ == "__main__":
    unittest.main()
