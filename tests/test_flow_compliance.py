"""Flow compliance: execution and workflow paths must not bypass core subsystems."""

from __future__ import annotations

import ast
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "jarvis"
sys.path.insert(0, str(ROOT / "src"))

# Modules that must route memory through MemoryManager (not direct store access).
MEMORY_GATEWAY = "jarvis.memory.manager"

# Modules allowed to import low-level stores (inside memory package only).
MEMORY_INTERNAL = {"jarvis.memory.store", "jarvis.memory.chroma_memory"}

# Patterns that indicate bypassing the execution engine for skill dispatch.
BYPASS_PATTERNS = (
    "task_executor._dispatch",
    "task_executor.execute_plan",
)


def _iter_python_files(base: Path):
    for path in base.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def _imports_module(path: Path, module: str) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == module:
                    return True
    return False


class TestFlowCompliance(unittest.TestCase):
    def test_app_wires_through_execution_engine(self) -> None:
        app_path = SRC / "app.py"
        src = app_path.read_text(encoding="utf-8")
        self.assertIn("GraphExecutionEngine", src)
        self.assertIn("MemoryManager", src)
        self.assertIn("InMemoryEventBus", src)
        self.assertIn("BuildPipeline", src)

    def test_adapter_uses_jarvis_planner_not_root(self) -> None:
        adapter = SRC / "execution" / "adapter.py"
        src = adapter.read_text(encoding="utf-8")
        self.assertIn("from jarvis.planner import plan_action", src)
        self.assertNotIn("from planner import", src)

    def test_no_direct_json_store_outside_memory_package(self) -> None:
        violations = []
        for path in _iter_python_files(SRC):
            mod = ".".join(path.relative_to(SRC.parent).with_suffix("").parts)
            if mod.startswith("jarvis.memory"):
                continue
            if _imports_module(path, "jarvis.memory.store"):
                violations.append(str(path.relative_to(ROOT)))
        self.assertEqual(violations, [])

    def test_workspace_publishes_via_event_bus(self) -> None:
        mgr = SRC / "workspace" / "manager.py"
        src = mgr.read_text(encoding="utf-8")
        self.assertIn("event_bus", src)
        self.assertIn("publish_async", src)

    def test_bridge_submits_build_through_job_service(self) -> None:
        bridge = SRC / "bridge" / "voice.py"
        src = bridge.read_text(encoding="utf-8")
        self.assertIn("build_project", src)
        self.assertIn("JobService", src)
        self.assertIn("BuildPipeline", src)


if __name__ == "__main__":
    unittest.main()
