"""Project workspace manager: scaffolds C:\\Project\\<Name> per project."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from jarvis.eventbus import events as ev
from jarvis.interfaces.events import EventBus, EventPriority, SystemEvent

logger = logging.getLogger("jarvis.workspace.manager")

DEFAULT_PROJECT_ROOT = r"C:\Project"

README_TEMPLATE = """# {name}

{description}

## Status

This project is being built autonomously by JARVIS with OpenCode.

## Documents

- [Requirements](requirements.md)
- [Specification](spec.md)
- [Progress](progress.json)
"""

REQUIREMENTS_TEMPLATE = """# Requirements — {name}

{description}

## Functional requirements

- (to be filled by the requirement gatherer)

## Non-functional requirements

- (to be filled)
"""

SPEC_TEMPLATE = """# Specification — {name}

{description}

## Architecture

- (to be filled by the spec generator)

## Modules

- (to be filled)
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9 _-]", "", name).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned or "Project"


class WorkspaceManager:
    """Creates and tracks project workspaces under a project root."""

    def __init__(self, project_root: Optional[str] = None, event_bus: Optional[EventBus] = None) -> None:
        self._project_root = project_root or os.environ.get("JARVIS_PROJECT_ROOT", DEFAULT_PROJECT_ROOT)
        self._event_bus = event_bus
        self._lock = threading.RLock()

    @property
    def project_root(self) -> str:
        return self._project_root

    def resolve(self, name: str) -> str:
        return os.path.join(self._project_root, slugify(name))

    def exists(self, name: str) -> bool:
        return os.path.isdir(self.resolve(name))

    def scaffold(self, name: str, description: str = "") -> Dict[str, Any]:
        """Create a new project workspace with documentation skeleton."""
        path = self.resolve(name)
        with self._lock:
            os.makedirs(path, exist_ok=True)
            os.makedirs(os.path.join(path, "Source"), exist_ok=True)

            self._write_if_missing(os.path.join(path, "README.md"), README_TEMPLATE.format(name=name, description=description))
            self._write_if_missing(os.path.join(path, "requirements.md"), REQUIREMENTS_TEMPLATE.format(name=name, description=description))
            self._write_if_missing(os.path.join(path, "spec.md"), SPEC_TEMPLATE.format(name=name, description=description))

            if not os.path.exists(os.path.join(path, "progress.json")):
                self.update_progress(
                    path,
                    step="scaffold",
                    message=f"Workspace created for {name}",
                    progress=5.0,
                    status="building",
                )

            if not os.path.exists(os.path.join(path, "workspace.json")):
                workspace_data = {
                    "name": name,
                    "created_at": _now_iso(),
                    "updated_at": _now_iso(),
                    "status": "building",
                    "workspace_path": path,
                    "project_spec": {
                        "requirements_file": "requirements.md",
                        "specification_file": "spec.md"
                    }
                }
                with open(os.path.join(path, "workspace.json"), "w", encoding="utf-8") as fh:
                    json.dump(workspace_data, fh, indent=2, ensure_ascii=False)

            self._git_init(path)

        result = {
            "name": name,
            "path": path,
            "status": "scaffolded",
            "files": ["README.md", "requirements.md", "spec.md", "progress.json", "source"],
        }
        self._publish(ev.WORKSPACE_CREATED, result)
        self._publish(ev.PROJECT_SCAFFOLDED, result)
        logger.info("Scaffolded workspace %s at %s", name, path)
        return result

    def update_progress(
        self,
        workspace: str,
        *,
        step: Optional[str] = None,
        message: Optional[str] = None,
        progress: Optional[float] = None,
        status: Optional[str] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Atomically update the project's progress.json."""
        progress_path = os.path.join(workspace, "progress.json")
        with self._lock:
            data = self.read_progress(workspace)
            data["updated_at"] = _now_iso()
            if step is not None:
                data["current_step"] = step
                data.setdefault("steps", [])
                existing = next((s for s in data["steps"] if s.get("step") == step), None)
                if existing is None:
                    data["steps"].append({"step": step, "status": "done", "message": message or ""})
                else:
                    existing.update({"status": "done", "message": message or existing.get("message", "")})
            if message is not None:
                data["message"] = message
            if progress is not None:
                data["progress"] = round(progress, 2)
            if status is not None:
                data["status"] = status
            if error is not None:
                data["error"] = error
                data["status"] = "failed"

            tmp = progress_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
            os.replace(tmp, progress_path)
        return data

    def read_progress(self, workspace: str) -> Dict[str, Any]:
        progress_path = os.path.join(workspace, "progress.json")
        if not os.path.exists(progress_path):
            return {"status": "unknown", "progress": 0.0, "steps": []}
        try:
            with open(progress_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read progress.json at %s: %s", progress_path, exc)
            return {"status": "unknown", "progress": 0.0, "steps": [], "read_error": str(exc)}

    def list_projects(self) -> List[Dict[str, Any]]:
        if not os.path.isdir(self._project_root):
            return []
        projects = []
        for entry in sorted(os.listdir(self._project_root)):
            path = os.path.join(self._project_root, entry)
            if os.path.isdir(path) and os.path.exists(os.path.join(path, "progress.json")):
                projects.append({"name": entry, "path": path, **self.read_progress(path)})
        return projects

    def _write_if_missing(self, path: str, content: str) -> None:
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)

    def _git_init(self, path: str) -> None:
        try:
            subprocess.run(
                ["git", "init", "-q", path],
                check=False,
                capture_output=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("git init failed for %s: %s", path, exc)

    def _publish(self, event_type: str, data: Dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish_async(
                SystemEvent(type=event_type, source="workspace.manager", priority=EventPriority.NORMAL, data=data)
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to publish workspace event %s", event_type)
