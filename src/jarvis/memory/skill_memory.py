"""Skill memory.

Handles skill registration, usage tracking, and skill metadata storage.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import sqlite3

from jarvis.interfaces.memory import SkillMemory as SkillMemoryABC


class SkillMemory(SkillMemoryABC):
    """Skill memory for tracking skill metadata and usage statistics.

    Stores skill definitions, usage counts, and metadata.
    """

    def __init__(self, conn: sqlite3.Connection, lock: any) -> None:
        """Initialize skill memory.

        Args:
            conn: SQLite database connection
            lock: Thread lock for database operations
        """
        self._conn = conn
        self._lock = lock

    # ------------------------------------------------------------------ #
    # Skill CRUD operations
    # ------------------------------------------------------------------ #

    def register_skill(
        self,
        name: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Register a new skill or update existing one.

        Args:
            name: Skill name (unique identifier)
            description: Skill description
            metadata: Additional skill metadata

        Returns:
            Skill ID
        """
        import uuid
        import time

        with self._lock:
            cursor = self._conn.cursor()
            skill_id = str(uuid.uuid4())
            now = time.time()
            metadata_json = json.dumps(metadata or {})

            cursor.execute(
                """
                INSERT INTO skills (
                    id, name, description, usage_count, last_used,
                    metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    skill_id,
                    name,
                    description,
                    0,  # initial usage count
                    None,  # last_used
                    metadata_json,
                    now,
                    now,
                ),
            )
            self._conn.commit()
            return skill_id

    def get_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Get a skill by ID.

        Args:
            skill_id: Skill ID

        Returns:
            Skill dictionary or None if not found
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT id, name, description, usage_count, last_used,
                       metadata, created_at, updated_at
                FROM skills WHERE id = ?
                """,
                (skill_id,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "name": row["name"],
                    "description": row["description"],
                    "usage_count": row["usage_count"],
                    "last_used": row["last_used"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            return None

    def get_skill_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a skill by name.

        Args:
            name: Skill name

        Returns:
            Skill dictionary or None if not found
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT id, name, description, usage_count, last_used,
                       metadata, created_at, updated_at
                FROM skills WHERE name = ?
                """,
                (name,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "name": row["name"],
                    "description": row["description"],
                    "usage_count": row["usage_count"],
                    "last_used": row["last_used"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            return None

    def list_skills(self) -> List[Dict[str, Any]]:
        """List all skills.

        Returns:
            List of skill dictionaries
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT id, name, description, usage_count, last_used,
                       metadata, created_at, updated_at
                FROM skills ORDER BY name
                """
            )
            rows = cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "description": row["description"],
                    "usage_count": row["usage_count"],
                    "last_used": row["last_used"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]

    def update_skill(
        self,
        skill_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update a skill.

        Args:
            skill_id: Skill ID
            name: New skill name (optional)
            description: New skill description (optional)
            metadata: New metadata (optional, replaces existing)

        Returns:
            True if skill was updated, False if not found
        """
        with self._lock:
            cursor = self._conn.cursor()

            # Build dynamic UPDATE query
            updates = []
            params = []

            if name is not None:
                updates.append("name = ?")
                params.append(name)
            if description is not None:
                updates.append("description = ?")
                params.append(description)
            if metadata is not None:
                updates.append("metadata = ?")
                params.append(json.dumps(metadata))

            if not updates:
                return False  # Nothing to update

            updates.append("updated_at = ?")
            params.append(self._get_timestamp())
            params.append(skill_id)

            query = f"UPDATE skills SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            self._conn.commit()
            return cursor.rowcount > 0

    def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill.

        Args:
            skill_id: Skill ID

        Returns:
            True if skill was deleted, False if not found
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
            self._conn.commit()
            return cursor.rowcount > 0

    # ------------------------------------------------------------------ #
    # Usage tracking
    # ------------------------------------------------------------------ #

    def increment_usage(self, skill_id: str) -> int:
        """Increment usage count for a skill.

        Args:
            skill_id: Skill ID

        Returns:
            New usage count
        """
        with self._lock:
            cursor = self._conn.cursor()
            now = self._get_timestamp()

            # Get current usage count
            cursor.execute(
                "SELECT usage_count FROM skills WHERE id = ?", (skill_id,)
            )
            row = cursor.fetchone()
            current_count = row["usage_count"] if row else 0

            # Update usage count and last_used
            new_count = current_count + 1
            cursor.execute(
                """
                UPDATE skills
                SET usage_count = ?, last_used = ?, updated_at = ?
                WHERE id = ?
                """,
                (new_count, now, now, skill_id),
            )
            self._conn.commit()
            return new_count

    def get_usage_count(self, skill_id: str) -> int:
        """Get usage count for a skill.

        Args:
            skill_id: Skill ID

        Returns:
            Usage count
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT usage_count FROM skills WHERE id = ?", (skill_id,)
            )
            row = cursor.fetchone()
            return row["usage_count"] if row else 0

    # ------------------------------------------------------------------ #
    # Helper methods
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_timestamp() -> float:
        """Get current timestamp."""
        import time

        return time.time()