"""Task builder and graph builder utilities."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from jarvis.types import ExecutionGraph, ExecutionMode, TaskNode


class TaskBuilder:
    """Fluent builder for TaskNode construction.

    Usage:
        task = (TaskBuilder("open_chrome")
                .action("open_app").param("app", "Chrome")
                .build())
    """

    def __init__(self, task_id: str) -> None:
        self._id = task_id
        self._action: str = ""
        self._params: Dict[str, Any] = {}
        self._depends_on: List[str] = []
        self._execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL
        self._max_retries: int = 0
        self._timeout_seconds: Optional[float] = None
        self._label: str = ""

    def action(self, name: str) -> "TaskBuilder":
        self._action = name
        return self

    def param(self, key: str, value: Any) -> "TaskBuilder":
        self._params[key] = value
        return self

    def params(self, **kwargs: Any) -> "TaskBuilder":
        self._params.update(kwargs)
        return self

    def depends_on(self, *task_ids: str) -> "TaskBuilder":
        self._depends_on.extend(task_ids)
        return self

    def mode(self, mode: ExecutionMode) -> "TaskBuilder":
        self._execution_mode = mode
        return self

    def retries(self, count: int) -> "TaskBuilder":
        self._max_retries = count
        return self

    def timeout(self, seconds: float) -> "TaskBuilder":
        self._timeout_seconds = seconds
        return self

    def label(self, text: str) -> "TaskBuilder":
        self._label = text
        return self

    def build(self) -> TaskNode:
        return TaskNode(
            id=self._id,
            action=self._action,
            params=dict(self._params),
            depends_on=list(self._depends_on),
            execution_mode=self._execution_mode,
            max_retries=self._max_retries,
            timeout_seconds=self._timeout_seconds,
            label=self._label,
        )


class GraphBuilder:
    """Fluent builder for ExecutionGraph construction.

    Usage:
        graph = (GraphBuilder("my_plan")
                 .then("find_file", "file_operation", op="search_files", query="test.txt")
                 .then("read_it", "file_operation", op="read_file", path="test.txt")
                     .after("find_file")
                 .build())
    """

    def __init__(self, graph_id: str) -> None:
        from jarvis.types import ExecutionGraph

        self._graph = ExecutionGraph(id=graph_id)
        self._last_node_id: Optional[str] = None

    def then(self, task_id: str, action: str, **params: Any) -> "GraphBuilder":
        node = TaskNode(id=task_id, action=action, params=params)
        self._graph.add_node(node)
        self._last_node_id = task_id
        return self

    def after(self, *task_ids: str) -> "GraphBuilder":
        if self._last_node_id and self._last_node_id in self._graph.nodes:
            for dep_id in task_ids:
                self._graph.add_edge(dep_id, self._last_node_id)
        return self

    def chain(self, task_id: str, action: str, **params: Any) -> "GraphBuilder":
        self.then(task_id, action, **params)
        if self._last_node_id and len(self._graph.nodes) > 1:
            prev_ids = [nid for nid in self._graph.nodes if nid != task_id]
            self.after(*prev_ids)
        return self

    def build(self) -> "ExecutionGraph":
        return self._graph
