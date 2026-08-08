"""Execution Memory.

Handles execution logs, performance metrics, and semantic search capabilities.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import sqlite3

from jarvis.interfaces.memory import ExecutionMemory as ExecutionMemoryABC
from jarvis.memory.chroma_memory import ChromaSemanticMemory


class ExecutionMemory(ExecutionMemoryABC):
    """Execution memory for tracking logs, performance metrics, and semantic search.

    Stores execution logs, performance data, and provides semantic search
    capabilities through ChromaDB integration.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        lock: any,
        chroma_semantic: ChromaSemanticMemory,
    ) -> None:
        """Initialize execution memory.

        Args:
            conn: SQLite database connection
            lock: Thread lock for database operations
            chroma_semantic: ChromaDB semantic memory instance
        """
        self._conn = conn
        self._lock = lock
        self._chroma = chroma_semantic

    # ------------------------------------------------------------------ #
    # Execution logging
    # ------------------------------------------------------------------ #

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
        """Log an execution event.

        Args:
            component: Component name (e.g., 'stt', 'llm', 'tts')
            action: Action performed
            status: Status ('success', 'failure', 'timeout')
            duration: Execution duration in seconds (optional)
            input_data: Input data (will be JSON serialized)
            output_data: Output data (will be JSON serialized)
            error: Error message if any
            metadata: Additional metadata

        Returns:
            Log entry ID
        """
        import time

        with self._lock:
            cursor = self._conn.cursor()
            timestamp = time.time()
            input_json = json.dumps(input_data) if input_data is not None else None
            output_json = json.dumps(output_data) if output_data is not None else None
            metadata_json = json.dumps(metadata) if metadata is not None else None

            cursor.execute(
                """
                INSERT INTO execution_logs (
                    timestamp, component, action, status, duration,
                    input_data, output_data, error, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    component,
                    action,
                    status,
                    duration,
                    input_json,
                    output_json,
                    error,
                    metadata_json,
                ),
            )
            self._conn.commit()
            return cursor.lastrowid

    def get_execution_logs(
        self,
        component: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Get execution logs with optional filtering.

        Args:
            component: Filter by component (optional)
            status: Filter by status (optional)
            limit: Maximum number of records to return
            offset: Offset for pagination

        Returns:
            List of execution log dictionaries
        """
        with self._lock:
            cursor = self._conn.cursor()

            query = """
                SELECT id, timestamp, component, action, status, duration,
                       input_data, output_data, error, metadata
                FROM execution_logs
            """
            params = []

            conditions = []
            if component is not None:
                conditions.append("component = ?")
                params.append(component)
            if status is not None:
                conditions.append("status = ?")
                params.append(status)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor.execute(query, params)
            rows = cursor.fetchall()

            return [
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "component": row["component"],
                    "action": row["action"],
                    "status": row["status"],
                    "duration": row["duration"],
                    "input_data": json.loads(row["input_data"]) if row["input_data"] else None,
                    "output_data": json.loads(row["output_data"]) if row["output_data"] else None,
                    "error": row["error"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
                }
                for row in rows
            ]

    # ------------------------------------------------------------------ #
    # Semantic search capabilities
    # ------------------------------------------------------------------ #

    def store_execution_embedding(
        self,
        key: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store an execution-related text entry with embedding for semantic search.

        Args:
            key: Unique identifier for the entry
            text: Text content to embed
            metadata: Additional metadata to store with the embedding
        """
        # Add execution context to metadata
        exec_metadata = {
            "type": "execution",
            "timestamp": self._get_timestamp(),
        }
        if metadata:
            exec_metadata.update(metadata)

        self._chroma.store_embedding(key, text, metadata=exec_metadata)

    def search_executions(
        self,
        query: str,
        top_k: int = 5,
        component: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search execution logs using semantic similarity.

        Args:
            query: Search query text
            top_k: Maximum number of results to return
            component: Filter by component (optional)
            status: Filter by status (optional)

        Returns:
            List of matching execution log entries with similarity scores
        """
        # Build ChromaDB filter
        where_clause: Dict[str, Any] = {"type": "execution"}
        if component:
            where_clause["component"] = component
        if status:
            where_clause["status"] = status

        # Search in ChromaDB
        results = self._chroma.search_facts(
            query=query,
            top_k=top_k,
            category=None,  # We're using type field instead of category
        )

        # Filter by our custom where clause (since ChromaDB doesn't support complex filtering in search_facts)
        # In a full implementation, we'd pass where_clause to the search method
        filtered_results = []
        for result in results:
            # Manual filtering since our search_facts doesn't support where parameter
            meta = result.get("metadata", {})
            if meta.get("type") == "execution":
                if component is None or meta.get("component") == component:
                    if status is None or meta.get("status") == status:
                        filtered_results.append(result)

        return filtered_results[:top_k]

    # ------------------------------------------------------------------ #
    # Performance metrics
    # ------------------------------------------------------------------ #

    def get_performance_stats(
        self, component: Optional[str] = None, hours: int = 24
    ) -> Dict[str, Any]:
        """Get performance statistics for a component.

        Args:
            component: Component name (optional, gets all if None)
            hours: Number of hours to look back

        Returns:
            Dictionary containing performance statistics
        """
        import time

        with self._lock:
            cursor = self._conn.cursor()
            since_time = time.time() - (hours * 3600)

            query = """
                SELECT
                    component,
                    COUNT(*) as total_count,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
                    SUM(CASE WHEN status = 'failure' THEN 1 ELSE 0 END) as failure_count,
                    AVG(duration) as avg_duration,
                    MIN(duration) as min_duration,
                    MAX(duration) as max_duration
                FROM execution_logs
                WHERE timestamp > ?
            """
            params = [since_time]

            if component is not None:
                query += " AND component = ?"
                params.append(component)

            query += " GROUP BY component"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            stats = {}
            for row in rows:
                comp = row["component"]
                total = row["total_count"] or 0
                success = row["success_count"] or 0
                failure = row["failure_count"] or 0
                success_rate = (success / total * 100) if total > 0 else 0

                stats[comp] = {
                    "total_executions": total,
                    "successful_executions": success,
                    "failed_executions": failure,
                    "success_rate_percent": round(success_rate, 2),
                    "avg_duration_seconds": round(row["avg_duration"], 3) if row["avg_duration"] else 0,
                    "min_duration_seconds": round(row["min_duration"], 3) if row["min_duration"] else 0,
                    "max_duration_seconds": round(row["max_duration"], 3) if row["max_duration"] else 0,
                }

            return stats

    # ------------------------------------------------------------------ #
    # Helper methods
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_timestamp() -> float:
        """Get current timestamp."""
        import time

        return time.time()