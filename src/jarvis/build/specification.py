"""Specification generation from requirements."""

from __future__ import annotations

from typing import Any, Dict, List


class SpecGenerator:
    """Produces technical specification markdown from requirements."""

    def generate(self, name: str, requirements_md: str) -> str:
        """Generate a specification document informed by requirements."""
        data: Dict[str, Any] = {
            "overview": f"Technical specification for {name}.",
            "stack": "Python 3.11+, modular package layout",
            "architecture": [
                "api: REST or CLI entry point",
                "core: domain logic and services",
                "storage: file or database persistence",
            ],
            "modules": [
                {"name": "core", "purpose": "Primary application engine", "depends_on": []},
                {"name": "ui", "purpose": "User interface layer", "depends_on": ["core"]},
            ],
            "milestones": [
                "M1: Scaffold workspace and requirements",
                "M2: Implement core modules",
                "M3: Integration and polish",
            ],
        }
        _ = requirements_md  # available for LLM-backed generators
        return self._render(name, data)

    def _render(self, name: str, data: Dict[str, Any]) -> str:
        lines: List[str] = [
            f"# Specification — {name}",
            "",
            "## Overview",
            "",
            str(data.get("overview", "")),
            "",
            "## Stack",
            "",
            str(data.get("stack", "")),
            "",
            "## Architecture",
            "",
        ]
        for item in data.get("architecture", []):
            lines.append(f"- {item}")
        lines.extend(["", "## Modules", ""])
        for mod in data.get("modules", []):
            deps = ", ".join(mod.get("depends_on", [])) or "none"
            lines.append(f"- **{mod.get('name', 'module')}**: {mod.get('purpose', '')} (depends on: {deps})")
        lines.extend(["", "## Milestones", ""])
        for item in data.get("milestones", []):
            lines.append(f"- {item}")
        lines.append("")
        return "\n".join(lines)
