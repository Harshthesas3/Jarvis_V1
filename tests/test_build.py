import os
import sys
import unittest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from jarvis.build.engine import BuildPipeline  # noqa: E402
from jarvis.build.requirements import RequirementGatherer  # noqa: E402
from jarvis.build.specification import SpecGenerator  # noqa: E402
from jarvis.jobs.model import Job, JobStatus  # noqa: E402
from jarvis.workspace.manager import WorkspaceManager  # noqa: E402

FAKE_SCRIPT = """import sys, time
print("Planning the build")
time.sleep(0.2)
print("Writing modules 50%")
print("Done.")
sys.exit(0)
"""


def _write_script(text, dir_path=None):
    import tempfile

    parent = dir_path or tempfile.mkdtemp()
    fd, path = tempfile.mkstemp(suffix=".py", dir=parent)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


class FakeRequirementGatherer(RequirementGatherer):
    def generate(self, name, description):
        return f"# Requirements — {name}\n\n## Overview\n\n{description}"


class FakeSpecGenerator(SpecGenerator):
    def generate(self, name, requirements_md):
        return f"# Specification — {name}\n\n## Overview\n\nBased on:\n{requirements_md[:200]}"


class RecordingBus:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)

    def publish_async(self, event):
        self.events.append(event)


class TestRenderers(unittest.TestCase):
    def test_requirements_render(self):
        gatherer = RequirementGatherer()
        md = gatherer._render("App", {"overview": "o", "functional": ["F1: a", "F2: b"], "non_functional": ["N1: c"], "user_stories": ["U1: d"]})
        self.assertIn("F1: a", md)
        self.assertIn("N1: c", md)

    def test_spec_render(self):
        generator = SpecGenerator()
        md = generator._render(
            "App",
            {
                "overview": "o",
                "stack": "Python",
                "architecture": ["api: rest"],
                "modules": [{"name": "core", "purpose": "engine", "depends_on": ["lib"]}],
                "milestones": ["M1: hello"],
            },
        )
        self.assertIn("**core**", md)
        self.assertIn("M1: hello", md)


class TestBuildPipeline(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp_root = tempfile.mkdtemp()
        self.script_dir = tempfile.mkdtemp()
        self.bus = RecordingBus()
        self.script = _write_script(FAKE_SCRIPT, dir_path=self.script_dir)
        self.pipeline = BuildPipeline(
            workspace_manager=WorkspaceManager(project_root=self.tmp_root),
            event_bus=self.bus,
            requirements_gatherer=FakeRequirementGatherer(),
            spec_generator=FakeSpecGenerator(),
        )

    def tearDown(self):
        if hasattr(self, "script") and self.script and os.path.exists(self.script):
            try:
                os.remove(self.script)
            except OSError:
                pass

    def test_prepare_documents(self):
        workspace = self.pipeline.workspace_manager.scaffold("DocApp", "desc")["path"]
        docs = self.pipeline.prepare_documents(workspace, "DocApp", "desc")
        self.assertTrue(docs["requirements"].endswith("requirements.md"))
        self.assertTrue(docs["spec"].endswith("spec.md"))
        with open(docs["requirements"], encoding="utf-8") as fh:
            self.assertIn("DocApp", fh.read())
        progress = self.pipeline.workspace_manager.read_progress(workspace)
        self.assertEqual(progress["progress"], 40.0)
        self.assertIn("project.spec_generated", [e.type for e in self.bus.events])

    def test_full_run(self):
        job = Job(job_id="p1", kind="build_project", params={"name": "FullApp", "description": "desc"})
        reports = []

        def report(progress, message=None):
            reports.append((progress, message))

        result = self.pipeline.run(
            job,
            report,
            opencode_binary=sys.executable,
            opencode_args=[self.script],
        )
        self.assertEqual(result["status"], "completed")
        progress = self.pipeline.workspace_manager.read_progress(job.workspace)
        self.assertEqual(progress["status"], "completed")
        self.assertEqual(progress["progress"], 100.0)
        self.assertTrue(any(r[0] >= 40 for r in reports))
        self.assertTrue(os.path.exists(os.path.join(job.workspace, "spec.md")))


if __name__ == "__main__":
    unittest.main()