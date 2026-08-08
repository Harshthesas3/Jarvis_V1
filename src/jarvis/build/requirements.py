"""Requirement gathering for autonomous project builds."""

from __future__ import annotations

from typing import Any, Dict, List


class RequirementGatherer:
    """Produces structured requirements markdown for a project."""

    def generate(self, name: str, description: str) -> str:
        """Generate requirements document from project name and description."""
        data: Dict[str, Any] = {
            "overview": description or f"A {name} application built autonomously by JARVIS.",
            "functional": [
                f"F1: Core {name} functionality as described by the user",
                "F2: User-facing interface for primary workflows",
                "F3: Persistent data storage where applicable",
            ],
            "non_functional": [
                "N1: Maintainable, modular codebase",
                "N2: Clear documentation and progress tracking",
            ],
            "user_stories": [
                f"U1: As a user, I want to use {name} for its intended purpose",
            ],
        }
        return self._render(name, data)

    def _render(self, name: str, data: Dict[str, Any]) -> str:
        lines: List[str] = [
            f"# Requirements — {name}",
            "",
            "## Overview",
            "",
            str(data.get("overview", "")),
            "",
            "## Functional requirements",
            "",
        ]
        for item in data.get("functional", []):
            lines.append(f"- {item}")
        lines.extend(["", "## Non-functional requirements", ""])
        for item in data.get("non_functional", []):
            lines.append(f"- {item}")
        lines.extend(["", "## User stories", ""])
        for item in data.get("user_stories", []):
            lines.append(f"- {item}")
        lines.append("")
        return "\n".join(lines)
