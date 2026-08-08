"""Memory Manager for Jarvis.

Provides centralized access to different types of memory:
- Conversation Memory: sliding window of chat history
- Project Memory: project-specific metadata and state
- User Memory: user preferences and settings
- Task Memory: task tracking and management
- Skill Memory: skill metadata and usage statistics
- Execution Memory: execution logs and semantic search

Uses appropriate storage backends:
- JSON: for simple key-value storage (user preferences, configuration)
- SQLite: for structured relational data (projects, tasks, skills, execution logs)
- ChromaDB: for semantic search and vector-based memory (execution logs, conversation summarization)
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from jarvis.memory.store import JsonMemoryStore
from jarvis.memory.chroma_memory import ChromaSemanticMemory

# Forward declarations to avoid circular imports
from .project_memory import ProjectMemory
from .user_memory import UserMemory
from .task_memory import TaskMemory
from .skill_memory import SkillMemory
from .execution_memory import ExecutionMemory
from .conversation_memory import ConversationMemoryWrapper


class MemoryManager:
    """Central memory manager coordinating different memory types.

    Attributes:
        json_store: JSON file-backed key-value store for simple data
        chroma_semantic: ChromaDB-backed semantic memory for vector search
        sqlite_conn: Thread-safe SQLite connection for structured data
        _lock: Thread lock for database operations
    """

    def __init__(
        self,
        json_path: str = "memory.json",
        chroma_path: str = "data/chroma_memory",
        sqlite_path: str = "data/memory.db",
    ) -> None:
        """Initialize memory manager with storage backends.

        Args:
            json_path: Path to JSON file for key-value storage
            chroma_path: Path to ChromaDB persistent directory
            sqlite_path: Path to SQLite database file
        """
        # JSON store for simple key-value (user prefs, config, etc.)
        self.json_store = JsonMemoryStore(json_path)

        # ChromaDB for semantic search and vector memory
        self.chroma_semantic = ChromaSemanticMemory(
            persist_directory=chroma_path,
            collection_name="jarvis_memory",
        )

        # SQLite for structured relational data
        self.sqlite_path = Path(sqlite_path)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.sqlite_conn = sqlite3.connect(str(self.sqlite_path), check_same_thread=False)
        self.sqlite_conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._initialize_tables()

        # Initialize memory subsystems
        self._conversation = ConversationMemoryWrapper(self.json_store)
        self._project = ProjectMemory(self.sqlite_conn, self._lock)
        self._user = UserMemory(self.json_store, self.sqlite_conn, self._lock)
        self._task = TaskMemory(self.sqlite_conn, self._lock)
        self._skill = SkillMemory(self.sqlite_conn, self._lock)
        self._execution = ExecutionMemory(
            self.sqlite_conn, self._lock, self.chroma_semantic
        )

    def _initialize_tables(self) -> None:
        """Create database tables if they don't exist."""
        with self._lock:
            cursor = self.sqlite_conn.cursor()

            # Projects table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    path TEXT NOT NULL,
                    metadata TEXT,  -- JSON string
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

            # User preferences table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS user_preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT,  -- JSON string
                    updated_at REAL NOT NULL
                )
                """
            )

            # Tasks table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    description TEXT,
                    status TEXT NOT NULL,  -- pending, in_progress, completed, deleted
                    active_form TEXT,
                    owner TEXT,
                    metadata TEXT,  -- JSON string
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

            # Skills table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS skills (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    usage_count INTEGER DEFAULT 0,
                    last_used REAL,
                    metadata TEXT,  -- JSON string
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

            # Execution logs table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    component TEXT NOT NULL,  -- e.g., 'stt', 'llm', 'tts'
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,  -- success, failure, timeout
                    duration REAL,  -- seconds
                    input_data TEXT,  -- JSON string
                    output_data TEXT,  -- JSON string
                    error TEXT,
                    metadata TEXT  -- JSON string
                )
                """
            )

            # Create indexes for common queries
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_execution_timestamp ON execution_logs(timestamp)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_execution_component ON execution_logs(component)"
            )

            self.sqlite_conn.commit()

    # --------------------------------------------------------------------- #
    # Memory subsystem accessors
    # --------------------------------------------------------------------- #

    @property
    def conversation(self) -> ConversationMemoryWrapper:
        """Access conversation memory (sliding window chat history)."""
        return self._conversation

    @property
    def project(self) -> ProjectMemory:
        """Access project memory (project metadata and state)."""
        return self._project

    @property
    def user(self) -> UserMemory:
        """Access user memory (preferences and settings)."""
        return self._user

    @property
    def task(self) -> TaskMemory:
        """Access task memory (task tracking and management)."""
        return self._task

    @property
    def skill(self) -> SkillMemory:
        """Access skill memory (skill metadata and usage)."""
        return self._skill

    @property
    def execution(self) -> ExecutionMemory:
        """Access execution memory (logs and semantic search)."""
        return self._execution

    # --------------------------------------------------------------------- #
    # Utility methods
    # --------------------------------------------------------------------- #

    def close(self) -> None:
        """Close all storage connections."""
        self.sqlite_conn.close()
        # Note: JsonMemoryStore and ChromaSemanticMemory handle their own cleanup

    def backup(self, backup_dir: str) -> None:
        """Create backup of all memory stores.

        Args:
            backup_dir: Directory to store backups
        """
        import shutil
        from datetime import datetime

        backup_path = Path(backup_dir) / f"jarvis_memory_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_path.mkdir(parents=True, exist_ok=True)

        # Backup JSON store
        shutil.copy2(self.json_store._path, backup_path / "memory.json")

        # Backup ChromaDB (copy the entire directory)
        if self.chroma_semantic._client:
            chroma_backup = backup_path / "chroma_memory"
            shutil.copytree(self.chroma_semantic._persist_directory, chroma_backup)

        # Backup SQLite database
        shutil.copy2(self.sqlite_path, backup_path / "memory.db")


# Global memory manager instance
_memory_manager: Optional[MemoryManager] = None
_manager_lock = threading.Lock()


def get_memory_manager() -> MemoryManager:
    """Get or create the global memory manager instance.

    Returns:
        Singleton MemoryManager instance
    """
    global _memory_manager
    with _manager_lock:
        if _memory_manager is None:
            _memory_manager = MemoryManager()
        return _memory_manager


def initialize_memory_manager(
    json_path: str = "memory.json",
    chroma_path: str = "data/chroma_memory",
    sqlite_path: str = "data/memory.db",
) -> MemoryManager:
    """Initialize the global memory manager with custom paths.

    Args:
        json_path: Path to JSON file for key-value storage
        chroma_path: Path to ChromaDB persistent directory
        sqlite_path: Path to SQLite database file

    Returns:
        Initialized MemoryManager instance
    """
    global _memory_manager
    with _manager_lock:
        _memory_manager = MemoryManager(json_path, chroma_path, sqlite_path)
        return _memory_manager