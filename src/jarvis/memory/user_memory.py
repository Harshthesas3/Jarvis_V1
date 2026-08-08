"""User Memory.

Handles user-specific data including:
- User preferences and settings
- User profile information
- Usage statistics and patterns
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import sqlite3

from jarvis.interfaces.memory import UserMemory as UserMemoryABC


class UserMemory(UserMemoryABC):
    """User memory for tracking user-specific data.

    Stores user preferences, settings, profile information, and usage patterns.
    """

    def __init__(
        self,
        json_store: any,  # JsonMemoryStore
        conn: sqlite3.Connection,
        lock: any,
    ) -> None:
        """Initialize user memory.

        Args:
            json_store: JSON memory store for simple key-value storage
            conn: SQLite database connection
            lock: Thread lock for database operations
        """
        self._json_store = json_store
        self._conn = conn
        self._lock = lock

    # ------------------------------------------------------------------ #
    # Preference management (JSON-backed for simplicity)
    # ------------------------------------------------------------------ #

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a user preference.

        Args:
            key: Preference key
            default: Default value if preference not found

        Returns:
            Preference value or default
        """
        return self._json_store.get(f"user_pref.{key}", default)

    def set_preference(self, key: str, value: Any) -> None:
        """Set a user preference.

        Args:
            key: Preference key
            value: Preference value to store
        """
        self._json_store.set(f"user_pref.{key}", value)

    def delete_preference(self, key: str) -> bool:
        """Delete a user preference.

        Args:
            key: Preference key

        Returns:
            True if preference was deleted, False if not found
        """
        return self._json_store.delete(f"user_pref.{key}")

    def get_all_preferences(self) -> Dict[str, Any]:
        """Get all user preferences.

        Returns:
            Dictionary of all user preferences
        """
        all_data = self._json_store.get_all()
        preferences = {}
        for key, value in all_data.items():
            if key.startswith("user_pref."):
                pref_key = key[len("user_pref.") :]
                preferences[pref_key] = value
        return preferences

    # ------------------------------------------------------------------ #
    # Profile management (SQLite-backed for structured data)
    # ------------------------------------------------------------------ # ------------------------------------------------------------------ #
    def set_profile_field(self, field: str, value: Any) -> None:
        """Set a user profile field.

        Args:
            field: Profile field name
            value: Field value (will be JSON serialized)
        """
        with self._lock:
            cursor = self._conn.cursor()
            value_json = json.dumps(value)
            now = self._get_timestamp()

            cursor.execute(
                """
                INSERT INTO user_preferences (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    updated_at=excluded.updated_at
                """,
                (f"user_profile.{field}", value_json, now),
            )
            self._conn.commit()

    def get_profile_field(self, field: str, default: Any = None) -> Any:
        """Get a user profile field.

        Args:
            field: Profile field name
            default: Default value if field not found

        Returns:
            Field value or default
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT value FROM user_preferences WHERE key = ?",
                (f"user_profile.{field}",),
            )
            row = cursor.fetchone()
            if row:
                try:
                    return json.loads(row["value"])
                except (json.JSONDecodeError, TypeError):
                    return row["value"]
            return default

    def get_profile(self) -> Dict[str, Any]:
        """Get complete user profile.

        Returns:
            Dictionary containing all user profile fields
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT key, value FROM user_preferences WHERE key LIKE 'user_profile.%'"
            )
            rows = cursor.fetchall()
            profile = {}
            for row in rows:
                field = row["key"][len("user_profile.") :]
                try:
                    profile[field] = json.loads(row["value"])
                except (json.JSONDecodeError, TypeError):
                    profile[field] = row["value"]
            return profile

    # ------------------------------------------------------------------ #
    # Usage statistics
    # ------------------------------------------------------------------ #

    def increment_usage_stat(self, stat_name: str, amount: int = 1) -> int:
        """Increment a usage statistic.

        Args:
            stat_name: Name of the statistic
            amount: Amount to increment by

        Returns:
            New value of the statistic
        """
        with self._lock:
            cursor = self._conn.cursor()
            now = self._get_timestamp()

            # Get current value
            cursor.execute(
                "SELECT value FROM user_preferences WHERE key = ?",
                (f"usage_stat.{stat_name}",),
            )
            row = cursor.fetchone()
            current_value = int(row["value"]) if row and row["value"] else 0

            # Update value
            new_value = current_value + amount
            cursor.execute(
                """
                INSERT INTO user_preferences (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    updated_at=excluded.updated_at
                """,
                (f"usage_stat.{stat_name}", str(new_value), now),
            )
            self._conn.commit()
            return new_value

    def get_usage_stat(self, stat_name: str, default: int = 0) -> int:
        """Get a usage statistic.

        Args:
            stat_name: Name of the statistic
            default: Default value if statistic not found

        Returns:
            Statistic value
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT value FROM user_preferences WHERE key = ?",
                (f"usage_stat.{stat_name}",),
            )
            row = cursor.fetchone()
            if row and row["value"]:
                try:
                    return int(row["value"])
                except (ValueError, TypeError):
                    return default
            return default

    def get_all_usage_stats(self) -> Dict[str, int]:
        """Get all usage statistics.

        Returns:
            Dictionary of usage statistics
        """
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                "SELECT key, value FROM user_preferences WHERE key LIKE 'usage_stat.%'"
            )
            rows = cursor.fetchall()
            stats = {}
            for row in rows:
                stat_name = row["key"][len("user_stat.") :]
                try:
                    stats[stat_name] = int(row["value"])
                except (ValueError, TypeError):
                    stats[stat_name] = 0
            return stats

    # ------------------------------------------------------------------ #
    # Helper methods
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_timestamp() -> float:
        """Get current timestamp."""
        import time

        return time.time()