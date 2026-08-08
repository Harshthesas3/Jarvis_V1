import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath("src"))
sys.path.insert(0, os.path.abspath("."))

from jarvis.workspace.manager import WorkspaceManager, slugify  # noqa: E402


class TestWorkspaceManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.manager = WorkspaceManager(project_root=self.tmp)

    def test_slugify(self):
        self.assertEqual(slugify("Spotify"), "Spotify")
        self.assertEqual(slugify("  My  Cool  App "), "My_Cool_App")
        self.assertEqual(slugify("a/b\\c:d"), "abcd")
        self.assertEqual(slugify("###"), "Project")

    def test_scaffold_creates_files(self):
        result = self.manager.scaffold("Spotify", "A music player")
        path = result["path"]
        self.assertTrue(self.manager.exists("Spotify"))
        for filename in ("README.md", "requirements.md", "spec.md", "progress.json"):
            self.assertTrue(os.path.exists(os.path.join(path, filename)), filename)
        self.assertTrue(os.path.isdir(os.path.join(path, "Source")))
        progress = self.manager.read_progress(path)
        self.assertEqual(progress["status"], "building")
        self.assertEqual(progress["progress"], 5.0)

    def test_scaffold_is_idempotent(self):
        first = self.manager.scaffold("App")
        second = self.manager.scaffold("App")
        self.assertEqual(first["path"], second["path"])

    def test_update_and_read_progress(self):
        workspace = self.manager.scaffold("App", "desc")["path"]
        self.manager.update_progress(workspace, step="opencode", message="working", progress=42.0)
        progress = self.manager.read_progress(workspace)
        self.assertEqual(progress["progress"], 42.0)
        self.assertEqual(progress["current_step"], "opencode")
        self.assertEqual(progress["steps"][-1]["step"], "opencode")
        self.manager.update_progress(workspace, step="opencode", message="v2", progress=60.0)
        steps = self.manager.read_progress(workspace)["steps"]
        self.assertEqual(len([s for s in steps if s["step"] == "opencode"]), 1)

    def test_read_progress_returns_default_for_missing(self):
        progress = self.manager.read_progress(os.path.join(self.tmp, "nope"))
        self.assertEqual(progress["status"], "unknown")

    def test_list_projects(self):
        self.manager.scaffold("One")
        self.manager.scaffold("Two")
        projects = self.manager.list_projects()
        names = [p["name"] for p in projects]
        self.assertIn("One", names)
        self.assertIn("Two", names)


if __name__ == "__main__":
    unittest.main()