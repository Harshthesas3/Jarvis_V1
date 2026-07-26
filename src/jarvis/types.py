"""Core shared types for JARVIS.

These are the primitive types used across all layers of the system.
No layer-specific logic should be imported here to keep this dependency-free.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Planner constants
# ---------------------------------------------------------------------------

MAX_INPUT_LENGTH: int = 2000
CONFIDENCE_THRESHOLD: float = 0.70
MAX_STEPS: int = 20
MAX_LLM_RETRIES: int = 2
LLM_RETRY_DELAY_MS: int = 500
LLM_TIMEOUT_SECONDS: int = 30
CIRCUIT_BREAKER_MAX_FAILURES: int = 5
CIRCUIT_BREAKER_RESET_SECONDS: int = 60


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PlanStatus(enum.Enum):
    """Status of a plan through its lifecycle."""
    PENDING = "pending"
    VALIDATED = "validated"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PARTIALLY_COMPLETED = "partially_completed"


class TaskStatus(enum.Enum):
    """Status of a single task in the execution graph."""
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class ExecutionMode(enum.Enum):
    """Execution mode for the graph engine."""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    PARALLEL_BARRIER = "parallel_barrier"
    CONDITIONAL = "conditional"


class Confidence(enum.Enum):
    """Confidence levels for intent classification."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNCERTAIN = "uncertain"


class LogLevel(enum.Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Action:
    """A named action with typed parameters."""
    name: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskNode:
    """A single node in the execution graph.

    Each task is a discrete, retryable, observable unit of work.
    Dependencies form a DAG through ``depends_on``.
    """
    id: str
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    max_retries: int = 0
    timeout_seconds: Optional[float] = None
    label: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def with_params(self, **kwargs: Any) -> TaskNode:
        return TaskNode(
            id=self.id,
            action=self.action,
            params={**self.params, **kwargs},
            depends_on=self.depends_on,
            execution_mode=self.execution_mode,
            max_retries=self.max_retries,
            timeout_seconds=self.timeout_seconds,
            label=self.label or "",
            metadata=self.metadata,
        )


@dataclass
class ExecutionGraph:
    """A directed acyclic graph of tasks to execute."""
    id: str
    nodes: Dict[str, TaskNode] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: TaskNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, from_id: str, to_id: str) -> None:
        if from_id in self.nodes and to_id in self.nodes:
            existing = list(self.nodes[to_id].depends_on)
            if from_id not in existing:
                self.nodes[to_id] = self.nodes[to_id].with_params(
                    depends_on=existing + [from_id],
                )

    @property
    def root_nodes(self) -> List[TaskNode]:
        all_deps = {d for n in self.nodes.values() for d in n.depends_on}
        return [n for n in self.nodes.values() if n.id not in all_deps]

    @property
    def leaf_nodes(self) -> List[TaskNode]:
        dependents = {d for n in self.nodes.values() for d in n.depends_on}
        return [n for n in self.nodes.values() if n.id not in dependents]

    def topological_sort(self) -> List[TaskNode]:
        in_degree: Dict[str, int] = {}
        for nid, node in self.nodes.items():
            in_degree.setdefault(nid, 0)
            for dep in node.depends_on:
                in_degree[nid] = in_degree.get(nid, 0) + 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        ordered = []
        while queue:
            nid = queue.pop(0)
            ordered.append(self.nodes[nid])
            for other_nid, other_node in self.nodes.items():
                if nid in other_node.depends_on:
                    in_degree[other_nid] -= 1
                    if in_degree[other_nid] == 0:
                        queue.append(other_nid)
        return ordered

    def validate(self) -> List[str]:
        visited: Dict[str, bool] = {}
        errors: List[str] = []

        def _visit(nid: str, path: List[str]) -> None:
            if nid in visited:
                if visited[nid] is False:
                    cycle = " -> ".join(path + [nid])
                    errors.append(f"Cycle detected: {cycle}")
                return
            visited[nid] = False
            for other_nid, other_node in self.nodes.items():
                if nid in other_node.depends_on:
                    _visit(other_nid, path + [nid])
            visited[nid] = True

        for nid in self.nodes:
            if nid not in visited:
                _visit(nid, [])
        return errors


@dataclass
class IntentResult:
    """Result of intent classification."""
    intent: str
    goal: str
    confidence: float
    required_capabilities: List[str]
    raw_text: str


@dataclass
class PlanResult:
    """Result of planning a user request."""
    graph: Optional[ExecutionGraph]
    status: PlanStatus
    message: str = ""
    confidence: float = 0.0
    alternatives: List[ExecutionGraph] = field(default_factory=list)


@dataclass
class TaskResult:
    """Result of executing a single task."""
    task_id: str
    status: TaskStatus
    output: str = ""
    error: Optional[str] = None
    duration_ms: float = 0.0
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """Overall result of executing an execution graph."""
    graph_id: str
    status: PlanStatus
    task_results: Dict[str, TaskResult] = field(default_factory=dict)
    total_duration_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class AudioChunk:
    """A chunk of audio data."""
    data: bytes
    sample_rate: int = 16000
    channels: int = 1
    dtype: str = "int16"
    timestamp: float = 0.0


@dataclass
class TranscriptResult:
    """Result of speech transcription."""
    text: str
    confidence: float = 0.0
    language: str = "en"
    is_wake_word: bool = False
    duration_ms: float = 0.0


@dataclass
class WindowInfo:
    """Information about a desktop window."""
    hwnd: int
    title: str
    class_name: str = ""
    process_id: int = 0
    process_name: str = ""
    bounds: Optional[Dict[str, int]] = None
    is_visible: bool = False
    is_focused: bool = False


@dataclass
class ElementInfo:
    """Information about a UI element."""
    automation_id: str = ""
    control_type: str = ""
    name: str = ""
    class_name: str = ""
    bounds: Optional[Dict[str, int]] = None
    is_enabled: bool = True
    is_visible: bool = True


@dataclass
class ServiceHealth:
    """Health status of a service."""
    name: str
    healthy: bool
    message: str = ""
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
