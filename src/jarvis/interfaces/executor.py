"""Task execution interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional

from jarvis.types import ExecutionGraph, ExecutionResult, TaskNode, TaskResult


class TaskHandler(ABC):
    """Handles execution of a specific task action."""

    @property
    @abstractmethod
    def action(self) -> str:
        """The action name this handler supports."""

    @abstractmethod
    def execute(self, task: TaskNode, context: dict) -> str:
        """Execute the task and return a status message."""


class ExecutionEngine(ABC):
    """Core execution engine that runs execution graphs."""

    @abstractmethod
    def execute(self, graph: ExecutionGraph) -> ExecutionResult:
        """Execute a graph and return results."""

    @abstractmethod
    def execute_async(
        self,
        graph: ExecutionGraph,
        on_progress: Optional[Callable[[TaskResult], None]] = None,
    ) -> ExecutionResult:
        """Execute a graph asynchronously with progress callbacks."""

    @abstractmethod
    def register_handler(self, handler: TaskHandler) -> None:
        """Register a task handler for an action type."""

    @abstractmethod
    def cancel(self, graph_id: str) -> bool:
        """Cancel execution of a graph."""

    @abstractmethod
    def get_status(self, graph_id: str) -> Optional[ExecutionResult]:
        """Get the current status of a graph execution."""


class ExecutorContext(ABC):
    """Shared context passed through the execution pipeline."""

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from context."""

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """Set a value in context."""

    @abstractmethod
    def update(self, data: dict) -> None:
        """Update multiple values at once."""
