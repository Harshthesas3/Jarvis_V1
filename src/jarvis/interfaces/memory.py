"""Memory storage interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class MemoryStore(ABC):
    """Persistent memory storage."""

    @abstractmethod
    def load(self) -> Dict[str, Any]:
        """Load all memory data."""

    @abstractmethod
    def save(self, data: Dict[str, Any]) -> None:
        """Persist memory data."""

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Get a specific value from memory."""

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """Set a specific value in memory."""

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a key from memory. Returns True if existed."""

    @abstractmethod
    def clear(self) -> None:
        """Clear all memory data."""


class SemanticMemory(ABC):
    """Vector-based semantic memory for similarity search."""

    @abstractmethod
    def store_embedding(self, key: str, text: str, metadata: Optional[dict] = None) -> None:
        """Store a text entry with its embedding."""

    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search memory by semantic similarity."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if semantic memory is available."""


class ConversationMemory(ABC):
    """Session-based conversation history with rolling window."""

    @abstractmethod
    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation history."""

    @abstractmethod
    def get_history(self, limit: Optional[int] = None) -> List[Dict[str, str]]:
        """Get recent conversation history."""

    @abstractmethod
    def clear(self) -> None:
        """Clear conversation history."""

    @abstractmethod
    def summarize(self) -> str:
        """Get a summary of the conversation so far."""


class ProjectMemory(ABC):
    """Project-specific metadata and state."""

    @abstractmethod
    def register_project(
        self, name: str, path: str, metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Register a new project or update existing one."""

    @abstractmethod
    def get_project(self, name: str) -> Optional[Dict[str, Any]]:
        """Get project information by name."""

    @abstractmethod
    def list_projects(self) -> List[Dict[str, Any]]:
        """List all registered projects."""

    @abstractmethod
    def update_project_metadata(
        self, name: str, metadata: Dict[str, Any]
    ) -> bool:
        """Update project metadata."""

    @abstractmethod
    def delete_project(self, name: str) -> bool:
        """Delete a project."""


class UserMemory(ABC):
    """User-specific data including preferences, profile, and usage statistics."""

    @abstractmethod
    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a user preference."""

    @abstractmethod
    def set_preference(self, key: str, value: Any) -> None:
        """Set a user preference."""

    @abstractmethod
    def delete_preference(self, key: str) -> bool:
        """Delete a user preference."""

    @abstractmethod
    def get_all_preferences(self) -> Dict[str, Any]:
        """Get all user preferences."""

    @abstractmethod
    def set_profile_field(self, field: str, value: Any) -> None:
        """Set a user profile field."""

    @abstractmethod
    def get_profile_field(self, field: str, default: Any = None) -> Any:
        """Get a user profile field."""

    @abstractmethod
    def get_profile(self) -> Dict[str, Any]:
        """Get complete user profile."""

    @abstractmethod
    def increment_usage_stat(self, stat_name: str, amount: int = 1) -> int:
        """Increment a usage statistic."""

    @abstractmethod
    def get_usage_stat(self, stat_name: str, default: int = 0) -> int:
        """Get a usage statistic."""

    @abstractmethod
    def get_all_usage_stats(self) -> Dict[str, int]:
        """Get all usage statistics."""


class TaskMemory(ABC):
    """Task tracking and management."""

    @abstractmethod
    def create_task(
        self,
        subject: str,
        description: str = "",
        active_form: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new task."""

    @abstractmethod
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a task by ID."""

    @abstractmethod
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
        """Update a task."""

    @abstractmethod
    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""

    @abstractmethod
    def list_tasks(
        self,
        status: Optional[str] = None,
        owner: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List tasks with optional filtering."""

    @abstractmethod
    def add_task_dependency(self, task_id: str, depends_on_task_id: str) -> bool:
        """Add a dependency relationship."""

    @abstractmethod
    def get_task_dependencies(self, task_id: str) -> List[str]:
        """Get list of task IDs that this task depends on."""


class SkillMemory(ABC):
    """Skill metadata and usage statistics."""

    @abstractmethod
    def register_skill(
        self,
        name: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Register a new skill or update existing one."""

    @abstractmethod
    def get_skill(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Get a skill by ID."""

    @abstractmethod
    def get_skill_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a skill by name."""

    @abstractmethod
    def list_skills(self) -> List[Dict[str, Any]]:
        """List all skills."""

    @abstractmethod
    def update_skill(
        self,
        skill_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Update a skill."""

    @abstractmethod
    def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill."""

    @abstractmethod
    def increment_usage(self, skill_id: str) -> int:
        """Increment usage count for a skill."""

    @abstractmethod
    def get_usage_count(self, skill_id: str) -> int:
        """Get usage count for a skill."""


class ExecutionMemory(ABC):
    """Execution logs, performance metrics, and semantic search capabilities."""

    @abstractmethod
    def log_execution(
        self,
        component: str,
        action: str,
        status: str,
        duration: Optional[float] = None,
        input_data: Optional[Any] = None,
        output_data: Optional[Any] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Log an execution event."""

    @abstractmethod
    def get_execution_logs(
        self,
        component: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get execution logs with optional filtering."""

    @abstractmethod
    def store_execution_embedding(
        self,
        key: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store an execution-related text entry with embedding for semantic search."""

    @abstractmethod
    def search_executions(
        self,
        query: str,
        top_k: int = 5,
        component: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search execution logs using semantic similarity."""

    @abstractmethod
    def get_performance_stats(
        self, component: Optional[str] = None, hours: int = 24
    ) -> Dict[str, Any]:
        """Get performance statistics for a component."""