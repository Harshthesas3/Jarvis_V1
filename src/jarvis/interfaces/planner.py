"""Intent planning and task decomposition interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from jarvis.types import ExecutionGraph, IntentResult, PlanResult


class IntentClassifier(ABC):
    """Classifies user intent from natural language text."""

    @abstractmethod
    def classify(self, text: str) -> Optional[IntentResult]:
        """Classify the user's intent from raw text."""


class Planner(ABC):
    """Transforms user input into executable execution graphs."""

    @abstractmethod
    def plan(self, text: str) -> PlanResult:
        """Transform user input into an execution graph plan."""

    @abstractmethod
    def plan_with_context(self, text: str, context: Optional[dict] = None) -> PlanResult:
        """Plan with additional contextual information."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the planner is ready."""


class CapabilityHandler(ABC):
    """Handles a specific capability domain."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this capability."""

    @abstractmethod
    def can_handle(self, intent: IntentResult) -> bool:
        """Check if this handler can handle the given intent."""

    @abstractmethod
    def build_graph(self, intent: IntentResult, text: str) -> Optional[ExecutionGraph]:
        """Build an execution graph for the given intent."""
