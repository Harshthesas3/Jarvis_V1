"""Validate subsystem dependency layering and acyclic import graph."""

from __future__ import annotations

import ast
import os
import sys
import unittest
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "jarvis"
sys.path.insert(0, str(ROOT / "src"))

# Layer order: lower index = more foundational (must not import from higher layers).
LAYERS: List[Tuple[str, Set[str]]] = [
    ("interfaces", {"jarvis.interfaces"}),
    ("types", {"jarvis.types"}),
    ("infrastructure", {"jarvis.eventbus", "jarvis.telemetry", "jarvis.services", "jarvis.di"}),
    ("memory", {"jarvis.memory"}),
    ("execution", {"jarvis.execution", "jarvis.skills", "jarvis.planner"}),
    ("workflow", {"jarvis.jobs", "jarvis.workspace", "jarvis.build", "jarvis.opencode"}),
    ("application", {"jarvis.app", "jarvis.main", "jarvis.api", "jarvis.bridge"}),
]

FORBIDDEN_EDGES: Set[Tuple[str, str]] = {
    ("infrastructure", "execution"),
    ("infrastructure", "workflow"),
    ("infrastructure", "application"),
    ("memory", "execution"),
    ("memory", "workflow"),
    ("memory", "application"),
    ("interfaces", "execution"),
    ("interfaces", "memory"),
    ("interfaces", "workflow"),
    ("interfaces", "application"),
}


def _module_layer(module: str) -> str | None:
    for layer_name, prefixes in LAYERS:
        if any(module == p or module.startswith(p + ".") for p in prefixes):
            return layer_name
    return None


def _collect_imports(py_file: Path) -> Set[str]:
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    imports: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return imports


def _jarvis_modules() -> Dict[str, Path]:
    modules: Dict[str, Path] = {}
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC.parent).with_suffix("")
        mod = ".".join(rel.parts)
        modules[mod] = path
    return modules


class TestDependencyGraph(unittest.TestCase):
    def test_no_forbidden_layer_imports(self) -> None:
        """Infrastructure and memory must not depend on execution/workflow layers."""
        violations: List[str] = []
        modules = _jarvis_modules()
        for mod_name, path in modules.items():
            src_layer = _module_layer(mod_name)
            if src_layer is None:
                continue
            for imp in _collect_imports(path):
                if imp != "jarvis":
                    continue
                # resolve jarvis.* imports from AST more precisely
                pass
            # Parse jarvis.* imports explicitly
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("jarvis."):
                    tgt_layer = _module_layer(node.module)
                    if tgt_layer is None or src_layer == tgt_layer:
                        continue
                    src_idx = next(i for i, (n, _) in enumerate(LAYERS) if n == src_layer)
                    tgt_idx = next(i for i, (n, _) in enumerate(LAYERS) if n == tgt_layer)
                    if (src_layer, tgt_layer) in FORBIDDEN_EDGES or tgt_idx > src_idx + 2:
                        if (src_layer, tgt_layer) in FORBIDDEN_EDGES:
                            violations.append(f"{mod_name} ({src_layer}) -> {node.module} ({tgt_layer})")
        self.assertEqual(violations, [], "Forbidden dependency edges:\n" + "\n".join(violations))

    def test_core_modules_import_cleanly(self) -> None:
        """Smoke-import critical subsystems without circular import errors."""
        modules = [
            "jarvis.interfaces.events",
            "jarvis.interfaces.memory",
            "jarvis.interfaces.automation",
            "jarvis.interfaces.executor",
            "jarvis.interfaces.skill",
            "jarvis.eventbus.bus",
            "jarvis.memory.manager",
            "jarvis.execution.engine",
            "jarvis.skills.registry",
            "jarvis.jobs.service",
            "jarvis.workspace.manager",
            "jarvis.build.engine",
            "jarvis.opencode.session",
        ]
        for mod in modules:
            with self.subTest(module=mod):
                __import__(mod)

    def test_interfaces_have_no_jarvis_implementation_imports(self) -> None:
        """Interface package must only depend on types, not concrete subsystems."""
        iface_dir = SRC / "interfaces"
        violations: List[str] = []
        for path in iface_dir.glob("*.py"):
            if path.name == "__init__.py":
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.startswith("jarvis.") and not node.module.startswith("jarvis.types"):
                        violations.append(f"{path.name}: {node.module}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
