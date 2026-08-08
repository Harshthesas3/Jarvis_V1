"""Task Memory.

Handles task tracking and management including:
- Task creation, retrieval, updating, deletion
- Task dependencies (blocking/blocked by)
- Task status tracking (pending, in_progress, completed, deleted)
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import sqlite3

from jarvis.interfaces.memory import TaskMemory as TaskMemoryABC


class TaskMemory(TaskMemoryABC):
    """Task memory for tracking and managing tasks.

    Stores tasks with their properties, dependencies, and status.
    """

    def __init__(self, conn: sqlite3.Connection, lock: any) -> None:
        """Initialize task memory.

        Args:
            conn: SQLite database connection
            lock: Thread lock for database operations
        """
        self._conn = conn
        self._lock = lock

    # ------------------------------------------------------------------ #
    # Task CRUD operations
    # ------------------------------------------------------------------ #

    def create_task(
        self,
        subject: str,
        description: str = "",
        active_form: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new task.

        Args:
            subject: Task title/description
            description: Detailed task description
            active_form: Present continuous form for spinner
            metadata: Additional task metadata

        Returns:
            Task ID
        """
        import uuid
        import time

        with self._lock:
            cursor = self._conn.cursor()
            task_id = str(uuid.uuid4())
            now = time.time()
            metadata_json = json.dumps(metadata or {})

            cursor.execute(
                """
                INSERT INTO tasks (
                    id, subject, description, status, active_form, owner,
                    metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    subject,
                    description,
                    "pending",  # initial status
                    active_form,
                    None,  # owner (unassigned)
                    metadata_json,
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return task_id

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a task by ID.

        Args:
            task_id: Task ID

        Returns:
            Task dictionary or None if not found
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT id, subject, description, status, active_form, owner,
                       metadata, created_at, updated_at
                FROM tasks WHERE id = ?
                """,
                (task_id,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "subject": row["subject"],
                    "description": row["description"],
                    "status": row["status"],
                    "active_form": row["active_form"],
                    "owner": row["owner"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            return None

    def update_task(
        self,
        task_id: str,
        subject: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        active_form: Optional[str] = None,
        owner: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update a task.

        Args:
            task_id: Task ID
            subject: New task title (optional)
            description: New task description (optional)
            status: New task status (optional)
            active_form: New active form (optional)
            owner: New task owner (optional)
            metadata: New metadata (optional, replaces existing)

        Returns:
            True if task was updated, False if not found
        """
        with self._lock:
            cursor = self._conn.cursor()

            # Build dynamic UPDATE query
            updates = []
            params = []

            if subject is not None:
                updates.append("subject = ?")
                params.append(subject)
            if description is not None:
                updates.append("description = ?")
                params.append(description)
            if status is not None:
                updates.append("status = ?")
                params.append(status)
            if active_form is not None:
                updates.append("active_form = ?")
                params.append(active_form)
            if owner is not None:
                updates.append("owner = ?")
                params.append(owner)
            if metadata is not None:
                updates.append("metadata = ?")
                params.append(json.dumps(metadata))

            if not updates:
                return False  # Nothing to update

            updates.append("updated_at = ?")
            params.append(self._get_timestamp())
            params.append(task_id)

            query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            self._conn.commit()
            return cursor.rowcount > 0

    def delete_task(self, task_id: str) -> bool:
        """Delete a task.

        Args:
            task_id: Task ID

        Returns:
            True if task was deleted, False if not found
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            self._conn.commit()
            return cursor.rowcount > 0

    def list_tasks(
        self,
        status: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List tasks with optional filtering.

        Args:
            status: Filter by status (optional)
            owner: Filter by owner (optional)

        Returns:
            List of task dictionaries
        """
        with self._lock:
            cursor = self._conn.cursor()

            query = """
                SELECT id, subject, description, status, active_form, owner,
                       metadata, created_at, updated_at
                FROM tasks
            """
            params = []

            conditions = []
            if status is not None:
                conditions.append("status = ?")
                params.append(status)
            if owner is not None:
                conditions.append("owner = ?")
                params.append(owner)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY created_at"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [
                {
                    "id": row["id"],
                    "subject": row["subject"],
                    "description": row["description"],
                    "status": row["status"],
                    "active_form": row["active_form"],
                    "owner": row["owner"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]

    # ------------------------------------------------------------------ #
    # Task dependency management
    # ------------------------------------------------------------------ #

    def add_task_dependency(self, task_id: str, depends_on_task_id: str) -> bool:
        """Add a dependency relationship (task_id depends on depends_on_task_id).

        Args:
            task_id: Task ID that depends on another task
            depends_on_task_id: Task ID that must be completed first

        Returns:
            True if dependency was added, False if either task not found
        """
        # Check if both tasks exist
        if not self.get_task(task_id) or not self.get_task(depends_on_task_id):
            return False

        # For simplicity, we'll store dependencies in metadata
        # In a production system, you might want a separate dependencies table
        with self._lock:
            cursor = self._conn.cursor()
            task = self.get_task(task_id)
            if task:
                metadata = task["metadata"]
                if "dependencies" not in metadata:
                    metadata["dependencies"] = []
                if depends_on_task_id not in metadata["dependencies"]:
                    metadata["dependencies"].append(depends_on_task_id)
                    self.update_task(task_id, metadata=metadata)
                    return True
            return False

    def get_task_dependencies(self, task_id: str) -> List[str]:
        """Get list of task IDs that this task depends on.

        Args:
            task_id: Task ID

        Returns:
            List of dependency task IDs
        """
        task = self.get_task(task_id)
        if task and "dependencies" in task["metadata"]:
            return task["metadata"]["dependencies"]
        return []

    # ------------------------------------------------------------------ #
    # Helper methods
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_timestamp() -> float:
        """Get current timestamp."""
        import time

        return time.time()