"""DAG-based execution engine with dependency-aware scheduling."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Set

from jarvis.eventbus.events import (
    EXECUTION_CANCELLED,
    EXECUTION_COMPLETE,
    EXECUTION_FAILED,
    EXECUTION_STARTED,
    TASK_COMPLETE,
    TASK_FAILED,
    TASK_RETRYING,
    TASK_STARTED,
)
from jarvis.interfaces.events import EventBus, EventPriority, SystemEvent
from jarvis.interfaces.executor import ExecutionEngine, TaskHandler
from jarvis.types import (
    ExecutionGraph,
    ExecutionResult,
    PlanStatus,
    TaskNode,
    TaskResult,
    TaskStatus,
)

logger = logging.getLogger("jarvis.execution.engine")

_MAX_RETRY_DELAY_MS = 5000
_BASE_RETRY_DELAY_MS = 500


class GraphExecutionEngine(ExecutionEngine):
    """DAG-based execution engine with dependency-aware scheduling.

    Supports topological ordering, parallel-capable scheduling,
    exponential-backoff retry, per-task timeout, per-graph cancellation,
    and progress observability via callbacks + event bus.
    """

    def __init__(self, event_bus: Optional[EventBus] = None) -> None:
        self._handlers: Dict[str, TaskHandler] = {}
        self._cancel_flags: Dict[str, threading.Event] = {}
        self._lock = threading.RLock()
        self._event_bus = event_bus
        self._active_graphs: Dict[str, ExecutionResult] = {}

    def register_handler(self, handler: TaskHandler) -> None:
        with self._lock:
            self._handlers[handler.action] = handler

    def register_handlers(self, handlers: list[TaskHandler]) -> None:
        for handler in handlers:
            self.register_handler(handler)

    def execute(self, plan: dict | ExecutionGraph) -> ExecutionResult:
        """Execute a plan (dict or ExecutionGraph) and return results."""
        if isinstance(plan, dict):
            from .adapter import _plan_to_graph

            graph = _plan_to_graph(plan)
        else:
            graph = plan
        return self.execute_async(graph)

    def execute_async(
        self,
        plan: dict | ExecutionGraph,
        on_progress: Optional[Callable[[TaskResult], None]] = None,
    ) -> ExecutionResult:
        """Execute a plan asynchronously with progress callbacks."""
        if isinstance(plan, dict):
            from .adapter import _plan_to_graph

            graph = _plan_to_graph(plan)
        else:
            graph = plan

        errors = graph.validate()
        if errors:
            result = ExecutionResult(
                graph_id=graph.id,
                status=PlanStatus.FAILED,
                error="; ".join(errors),
            )
            self._active_graphs[graph.id] = result
            return result

        cancel_event = threading.Event()
        with self._lock:
            self._cancel_flags[graph.id] = cancel_event

        result = ExecutionResult(graph_id=graph.id, status=PlanStatus.RUNNING)
        self._active_graphs[graph.id] = result
        t_start = time.perf_counter()

        self._publish_event(EXECUTION_STARTED, {"graph_id": graph.id, "node_count": len(graph.nodes)})

        try:
            ordered = graph.topological_sort()
            completed: Set[str] = set()
            task_results: Dict[str, TaskResult] = {}

            for node in ordered:
                if cancel_event.is_set():
                    result.status = PlanStatus.CANCELLED
                    self._publish_event(EXECUTION_CANCELLED, {"graph_id": graph.id})
                    break

                node_result = self._execute_node(node, graph, completed, cancel_event, on_progress)
                task_results[node.id] = node_result
                completed.add(node.id)

                if node_result.status == TaskStatus.FAILED:
                    if node.execution_mode.value in ("sequential",):
                        remaining = [n for n in ordered if n.id not in completed]
                        for skipped in remaining:
                            task_results[skipped.id] = TaskResult(
                                task_id=skipped.id,
                                status=TaskStatus.SKIPPED,
                            )
                            completed.add(skipped.id)
                        break

            elapsed = (time.perf_counter() - t_start) * 1000
            result.task_results = task_results
            result.total_duration_ms = elapsed

            all_failed = all(r.status == TaskStatus.SKIPPED for r in task_results.values()) and bool(task_results)
            any_failed = any(r.status in (TaskStatus.FAILED, TaskStatus.SKIPPED) for r in task_results.values())

            if result.status != PlanStatus.CANCELLED:
                if all_failed and not any(r.status == TaskStatus.SUCCEEDED for r in task_results.values()):
                    result.status = PlanStatus.FAILED
                elif any_failed:
                    result.status = PlanStatus.PARTIALLY_COMPLETED
                else:
                    result.status = PlanStatus.COMPLETED

            if result.status == PlanStatus.FAILED:
                self._publish_event(EXECUTION_FAILED, {"graph_id": graph.id, "error": result.error or "Unknown"})
            else:
                self._publish_event(EXECUTION_COMPLETE, {"graph_id": graph.id, "duration_ms": elapsed})

        except Exception as exc:
            elapsed = (time.perf_counter() - t_start) * 1000
            result.status = PlanStatus.FAILED
            result.error = str(exc)
            result.total_duration_ms = elapsed
            logger.exception("Graph execution failed: %s", exc)
            self._publish_event(EXECUTION_FAILED, {"graph_id": graph.id, "error": str(exc)})

        self._active_graphs[graph.id] = result
        with self._lock:
            self._cancel_flags.pop(graph.id, None)

        return result

    def _execute_node(
        self,
        node: TaskNode,
        graph: ExecutionGraph,
        completed: Set[str],
        cancel_event: threading.Event,
        on_progress: Optional[Callable[[TaskResult], None]],
    ) -> TaskResult:
        for dep_id in node.depends_on:
            if dep_id not in completed:
                return TaskResult(task_id=node.id, status=TaskStatus.SKIPPED, error=f"Dependency not met: {dep_id}")

        handler = self._handlers.get(node.action)
        if handler is None:
            return TaskResult(
                task_id=node.id,
                status=TaskStatus.FAILED,
                error=f"No handler registered for action: {node.action}",
            )

        self._publish_event(TASK_STARTED, {"task_id": node.id, "action": node.action})

        t_start = time.perf_counter()
        last_error: Optional[str] = None
        retries = 0
        max_retries = node.max_retries

        while retries <= max_retries:
            if cancel_event.is_set():
                return TaskResult(task_id=node.id, status=TaskStatus.CANCELLED)
            try:
                context = {"graph": graph, "completed_tasks": completed}
                if node.timeout_seconds:
                    output = self._run_with_timeout(handler, node, context, node.timeout_seconds)
                else:
                    output = handler.execute(node, context)

                duration = (time.perf_counter() - t_start) * 1000
                tr = TaskResult(task_id=node.id, status=TaskStatus.SUCCEEDED, output=output, duration_ms=duration, retry_count=retries)
                self._publish_event(TASK_COMPLETE, {"task_id": node.id, "output": output[:200] if output else ""})
                if on_progress:
                    on_progress(tr)
                return tr
            except TimeoutError:
                last_error = f"Task timed out after {node.timeout_seconds}s"
            except Exception as exc:
                last_error = str(exc)

            retries += 1
            if retries <= max_retries:
                delay = min(_BASE_RETRY_DELAY_MS * (2 ** (retries - 1)), _MAX_RETRY_DELAY_MS)
                logger.warning("Task %s failed attempt %d/%d, retrying in %dms: %s", node.id, retries, max_retries + 1, delay, last_error)
                self._publish_event(TASK_RETRYING, {"task_id": node.id, "attempt": retries, "delay_ms": delay, "error": last_error})
                cancel_event.wait(delay / 1000)

        duration = (time.perf_counter() - t_start) * 1000
        tr = TaskResult(task_id=node.id, status=TaskStatus.FAILED, error=last_error, duration_ms=duration, retry_count=retries - 1)
        self._publish_event(TASK_FAILED, {"task_id": node.id, "error": last_error})
        if on_progress:
            on_progress(tr)
        return tr

    def _run_with_timeout(self, handler: TaskHandler, node: TaskNode, context: dict, timeout: float) -> str:
        result: list[str] = []
        exception: list[Exception] = []

        def _run() -> None:
            try:
                result.append(handler.execute(node, context))
            except Exception as exc:
                exception.append(exc)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=timeout)
        if thread.is_alive():
            raise TimeoutError(f"Task {node.id} timed out after {timeout}s")
        if exception:
            raise exception[0]
        return result[0]

    def cancel(self, graph_id: str) -> bool:
        with self._lock:
            cancel_event = self._cancel_flags.get(graph_id)
            if cancel_event is None:
                return False
            cancel_event.set()
            if graph_id in self._active_graphs:
                self._active_graphs[graph_id].status = PlanStatus.CANCELLED
            return True

    def get_status(self, graph_id: str) -> Optional[ExecutionResult]:
        return self._active_graphs.get(graph_id)

    def get_active_graphs(self) -> Dict[str, ExecutionResult]:
        return dict(self._active_graphs)

    def is_registered(self, action: str) -> bool:
        return action in self._handlers

    def _publish_event(self, event_type: str, data: dict) -> None:
        if self._event_bus:
            self._event_bus.publish(SystemEvent(type=event_type, source="execution_engine", data=data))