"""Project Memory.

Handles project-specific metadata and state including:
- Project registration and tracking
- Project metadata storage
- Project state persistence
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import sqlite3

from jarvis.interfaces.memory import ProjectMemory as ProjectMemoryABC


class ProjectMemory(ProjectMemoryABC):
    """Project memory for tracking project-specific data.

    Stores project metadata, state, and configuration in SQLite.
    """

    def __init__(self, conn: sqlite3.Connection, lock: any) -> None:
        """Initialize project memory.

        Args:
            conn: SQLite database connection
            lock: Thread lock for database operations
        """
        self._conn = conn
        self._lock = lock

    # ------------------------------------------------------------------ #
    # Project CRUD operations
    # ------------------------------------------------------------------ #

    def register_project(
        self,
        name: str,
        path: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Register a new project or update existing one.

        Args:
            name: Project name (unique identifier)
            path: Project file system path
            metadata: Optional project metadata as dictionary

        Returns:
            Project ID
        """
        with self._lock:
            cursor = self._conn.cursor()
            metadata_json = json.dumps(metadata or {})
            now = self._get_timestamp()

            # Use UPSERT (INSERT OR REPLACE) to handle existing projects
            cursor.execute(
                """
                INSERT INTO projects (name, path, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    path=excluded.path,
                    metadata=excluded.metadata,
                    updated_at=excluded.updated_at
                """,
                (name, path, metadata_json, now, now),
            )
            self._conn.commit()
            return cursor.lastrowid

    def get_project(self, name: str) -> Optional[Dict[str, Any]]:
        """Get project information by name.

        Args:
            name: Project name

        Returns:
            Project dictionary or None if not found
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT id, name, path, metadata, created_at, updated_at FROM projects WHERE name = ?",
                (name,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "name": row["name"],
                    "path": row["path"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            return None

    def list_projects(self) -> List[Dict[str, Any]]:
        """List all registered projects.

        Returns:
            List of project dictionaries
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT id, name, path, metadata, created_at, updated_at FROM projects ORDER BY name"
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "path": row["path"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]

    def update_project_metadata(
        self, name: str, metadata: Dict[str, Any]
    ) -> bool:
        """Update project metadata.

        Args:
            name: Project name
            metadata: New metadata to merge with existing

        Returns:
            True if project was updated, False if not found
        """
        with self._lock:
            cursor = self._conn.cursor()
            # Get existing metadata
            cursor.execute(
                "SELECT metadata FROM projects WHERE name = ?", (name,)
            )
            row = cursor.fetchone()
            if not row:
                return False

            existing_metadata = (
                json.loads(row["metadata"]) if row["metadata"] else {}
            )
            # Merge new metadata with existing
            existing_metadata.update(metadata)
            metadata_json = json.dumps(existing_metadata)
            now = self._get_timestamp()

            cursor.execute(
                """
                UPDATE projects
                SET metadata = ?, updated_at = ?
                WHERE name = ?
                """,
                (metadata_json, now, name),
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def delete_project(self, name: str) -> bool:
        """Delete a project.

        Args:
            name: Project name

        Returns:
            True if project was deleted, False if not found
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("DELETE FROM projects WHERE name = ?", (name,))
            self._conn.commit()
            return cursor.rowcount > 0

    # ------------------------------------------------------------------ #
    # Helper methods
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_timestamp() -> float:
        """Get current timestamp."""
        import time

        return time.time()
