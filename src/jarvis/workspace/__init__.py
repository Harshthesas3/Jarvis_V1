"""Project workspace management."""

from __future__ import annotations

from jarvis.workspace.manager import (
    DEFAULT_PROJECT_ROOT,
    WorkspaceManager,
    slugify,
)

__all__ = ["DEFAULT_PROJECT_ROOT", "WorkspaceManager", "slugify"]