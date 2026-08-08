"""Application registry for managing applications."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class ApplicationInfo:
    """Information about an application."""
    name: str
    path: str
    executable: str
    description: Optional[str] = None
    working_dir: Optional[str] = None
    arguments: List[str] = field(default_factory=list)


class ApplicationRegistry:
    """Registry for managing applications and their execution."""

    def __init__(self):
        self._applications: Dict[str, ApplicationInfo] = {}
        self._execution_history: List[Dict[str, Any]] = []

    def register_application(self, name: str, executable: str, **kwargs) -> bool:
        """
        Register an application with the registry.

        Args:
            name: Unique name for the application
            executable: Path to the executable
            **kwargs: Additional application info (description, working_dir, arguments)

        Returns:
            True if registration successful, False if application name already exists
        """
        if name in self._applications:
            return False

        app_info = ApplicationInfo(
            name=name,
            path=executable,  # Path is the same as executable for simple case
            executable=executable,
            description=kwargs.get("description"),
            working_dir=kwargs.get("working_dir"),
            arguments=kwargs.get("arguments", [])
        )

        self._applications[name] = app_info
        return True

    def unregister_application(self, name: str) -> bool:
        """
        Unregister an application from the registry.

        Args:
            name: Name of the application to remove

        Returns:
            True if application was removed, False if not found
        """
        if name in self._applications:
            del self._applications[name]
            return True
        return False

    def get_application(self, name: str) -> Optional[ApplicationInfo]:
        """
        Get an application by name.

        Args:
            name: Name of the application to retrieve

        Returns:
            ApplicationInfo if found, None otherwise
        """
        return self._applications.get(name)

    def list_applications(self) -> List[str]:
        """
        List all registered application names.

        Returns:
            List of application names
        """
        return list(self._applications.keys())

    def execute_application(self, name: str, **kwargs) -> Dict[str, Any]:
        """
        Execute an application by name.

        Args:
            name: Name of the application to execute
            **kwargs: Additional arguments

        Returns:
            Dictionary containing:
                - success (bool): Whether execution succeeded
                - reason (str): Human-readable reason for success/failure
                - logs (List[str]): Execution logs
                - execution_time (float): Time taken to execute
                - data (Any): Process information
        """
        start_time = time.time()

        # Get the application
        app = self.get_application(name)
        if app is None:
            return {
                "success": False,
                "reason": f"Application '{name}' not found",
                "logs": [f"Application '{name}' not found in registry"],
                "execution_time": time.time() - start_time,
                "data": None
            }

        # Build command
        cmd = [app.executable] + app.arguments

        try:
            import subprocess

            # Start the process
            process = subprocess.Popen(
                cmd,
                cwd=app.working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            execution_time = time.time() - start_time

            result = {
                "success": True,
                "reason": f"Application '{name}' started successfully",
                "logs": [
                    f"Started {name} with PID {process.pid}",
                    f"Executable: {app.executable}",
                    f"Arguments: {' '.join(cmd)}"
                ],
                "execution_time": execution_time,
                "data": {
                    "name": app.name,
                    "pid": process.pid,
                    "executable": app.executable,
                    "arguments": app.arguments,
                    "working_dir": app.working_dir
                }
            }

            self._execution_history.append(result)
            return result

        except FileNotFoundError:
            execution_time = time.time() - start_time
            error_result = {
                "success": False,
                "reason": f"Executable not found: {app.executable}",
                "logs": [
                    f"Failed to start {name}",
                    f"Executable path: {app.executable}",
                    f"Working directory: {app.working_dir or 'Not specified'}"
                ],
                "execution_time": execution_time,
                "data": None
            }

            self._execution_history.append(error_result)
            return error_result

        except PermissionError:
            execution_time = time.time() - start_time
            error_result = {
                "success": False,
                "reason": f"Permission denied: {app.executable}",
                "logs": [
                    f"Failed to start {name}",
                    f"Executable: {app.executable}",
                    f"Working directory: {app.working_dir or 'Not specified'}"
                ],
                "execution_time": execution_time,
                "data": None
            }

            self._execution_history.append(error_result)
            return error_result

        except Exception as e:
            execution_time = time.time() - start_time
            error_result = {
                "success": False,
                "reason": f"Application execution failed: {str(e)}",
                "logs": [
                    f"Failed to start {name}",
                    f"Exception: {str(e)}",
                    f"Executable: {app.executable}"
                ],
                "execution_time": execution_time,
                "data": None
            }

            self._execution_history.append(error_result)
            return error_result

    def get_execution_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get execution history.

        Args:
            limit: Maximum number of results to return (None for all)

        Returns:
            List of execution results
        """
        if limit is None:
            return self._execution_history.copy()
        return self._execution_history[-limit:]

    def clear_history(self) -> None:
        """Clear execution history."""
        self._execution_history.clear()