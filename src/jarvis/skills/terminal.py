"""Terminal skill implementation."""

from __future__ import annotations

import logging
import subprocess
import time
import os
from typing import Any, Dict, List, Optional

from jarvis.skills.interfaces import SkillInterface

logger = logging.getLogger("jarvis.skills.terminal")


class TerminalSkill(SkillInterface):
    """Skill for terminal/command line operations."""

    @property
    def name(self) -> str:
        return "terminal"

    @property
    def description(self) -> str:
        return "Terminal operations including command execution, shell management, and process control"

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute terminal operations.

        Supported operations:
        - execute_command: Execute a shell command
        - execute_powershell: Execute a PowerShell command
        - get_environment: Get environment variables
        - set_environment: Set environment variables
        - get_current_directory: Get current working directory
        - change_directory: Change working directory
        - list_processes: List running processes
        - kill_process: Kill a process by ID or name

        Args:
            action: Operation to perform
            **kwargs: Operation-specific arguments

        Returns:
            Dictionary with execution results
        """
        start_time = time.time()
        action = kwargs.get("action", "").lower()

        try:
            if action == "execute_command":
                result = self._execute_command(**kwargs)
            elif action == "execute_powershell":
                result = self._execute_powershell(**kwargs)
            elif action == "get_environment":
                result = self._get_environment(**kwargs)
            elif action == "set_environment":
                result = self._set_environment(**kwargs)
            elif action == "get_current_directory":
                result = self._get_current_directory(**kwargs)
            elif action == "change_directory":
                result = self._change_directory(**kwargs)
            elif action == "list_processes":
                result = self._list_processes(**kwargs)
            elif action == "kill_process":
                result = self._kill_process(**kwargs)
            else:
                result = {
                    "success": False,
                    "reason": f"Unknown action: {action}",
                    "logs": [
                        f"Available actions: execute_command, execute_powershell, get_environment, "
                        f"set_environment, get_current_directory, change_directory, list_processes, kill_process"
                    ],
                    "data": None
                }

            # Add execution time to result
            result["execution_time"] = time.time() - start_time
            return result

        except Exception as e:
            logger.error("TerminalSkill execution failed: %s", e, exc_info=True)
            return {
                "success": False,
                "reason": f"TerminalSkill execution failed: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None,
                "execution_time": time.time() - start_time
            }

    def _execute_command(self, **kwargs) -> Dict[str, Any]:
        """Execute a shell command."""
        command = kwargs.get("command")
        if not command:
            return {
                "success": False,
                "reason": "command parameter required",
                "logs": ["Please provide command parameter"],
                "data": None
            }

        try:
            # Execute command in shell
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=kwargs.get("timeout", 30)
            )

            success = result.returncode == 0
            output = result.stdout
            error = result.stderr

            logs = [
                f"Executed command: {command}",
                f"Exit code: {result.returncode}",
                f"Output length: {len(output)} chars",
                f"Error length: {len(error)} chars"
            ]

            if success:
                reason = f"Command executed successfully: {command}"
            else:
                reason = f"Command failed with exit code {result.returncode}: {command}"

            return {
                "success": success,
                "reason": reason,
                "logs": logs,
                "data": {
                    "command": command,
                    "exit_code": result.returncode,
                    "stdout": output,
                    "stderr": error,
                    "success": success
                }
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "reason": f"Command timed out: {command}",
                "logs": [f"Command execution exceeded timeout: {command}"],
                "data": {"command": command, "timed_out": True}
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to execute command: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"command": command}
            }

    def _execute_powershell(self, **kwargs) -> Dict[str, Any]:
        """Execute a PowerShell command."""
        command = kwargs.get("command")
        if not command:
            return {
                "success": False,
                "reason": "command parameter required",
                "logs": ["Please provide command parameter"],
                "data": None
            }

        try:
            # Execute PowerShell command
            ps_command = ["powershell", "-Command", command]
            result = subprocess.run(
                ps_command,
                capture_output=True,
                text=True,
                timeout=kwargs.get("timeout", 30)
            )

            success = result.returncode == 0
            output = result.stdout
            error = result.stderr

            logs = [
                f"Executed PowerShell command: {command}",
                f"Exit code: {result.returncode}",
                f"Output length: {len(output)} chars",
                f"Error length: {len(error)} chars"
            ]

            if success:
                reason = f"PowerShell command executed successfully: {command}"
            else:
                reason = f"PowerShell command failed with exit code {result.returncode}: {command}"

            return {
                "success": success,
                "reason": reason,
                "logs": logs,
                "data": {
                    "command": command,
                    "exit_code": result.returncode,
                    "stdout": output,
                    "stderr": error,
                    "success": success
                }
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "reason": f"PowerShell command timed out: {command}",
                "logs": [f"PowerShell command execution exceeded timeout: {command}"],
                "data": {"command": command, "timed_out": True}
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to execute PowerShell command: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"command": command}
            }

    def _get_environment(self, **kwargs) -> Dict[str, Any]:
        """Get environment variables."""
        variable_name = kwargs.get("variable_name")

        try:
            env = dict(os.environ)

            if variable_name:
                # Return specific variable
                value = env.get(variable_name)
                if value is None:
                    return {
                        "success": False,
                        "reason": f"Environment variable not found: {variable_name}",
                        "logs": [f"Environment variable not found: {variable_name}"],
                        "data": None
                    }

                return {
                    "success": True,
                    "reason": f"Environment variable retrieved: {variable_name}",
                    "logs": [f"Retrieved env var: {variable_name}"],
                    "data": {
                        "variable_name": variable_name,
                        "value": value
                    }
                }
            else:
                # Return all environment variables
                return {
                    "success": True,
                    "reason": f"Retrieved {len(env)} environment variables",
                    "logs": [f"Retrieved {len(env)} environment variables"],
                    "data": {
                        "environment_variables": env,
                        "count": len(env)
                    }
                }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to get environment: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"variable_name": variable_name}
            }

    def _set_environment(self, **kwargs) -> Dict[str, Any]:
        """Set environment variables."""
        variable_name = kwargs.get("variable_name")
        value = kwargs.get("value")
        permanent = kwargs.get("permanent", False)

        if not variable_name:
            return {
                "success": False,
                "reason": "variable_name parameter required",
                "logs": ["Please provide variable_name parameter"],
                "data": None
            }

        try:
            # Set in current process environment
            os.environ[variable_name] = str(value) if value is not None else ""

            logs = [f"Set environment variable: {variable_name}"]
            if permanent:
                # Note: Setting permanent environment variables requires registry modification
                # which requires admin privileges and is platform-specific
                logs.append("Warning: Permanent environment variable setting not implemented for security")

            return {
                "success": True,
                "reason": f"Environment variable set: {variable_name}",
                "logs": logs,
                "data": {
                    "variable_name": variable_name,
                    "value": str(value) if value is not None else "",
                    "permanent": permanent
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to set environment: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"variable_name": variable_name, "value": value}
            }

    def _get_current_directory(self, **kwargs) -> Dict[str, Any]:
        """Get current working directory."""
        try:
            cwd = os.getcwd()
            return {
                "success": True,
                "reason": f"Current directory retrieved: {cwd}",
                "logs": [f"Current working directory: {cwd}"],
                "data": {
                    "current_directory": cwd
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to get current directory: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _change_directory(self, **kwargs) -> Dict[str, Any]:
        """Change working directory."""
        path = kwargs.get("path")
        if not path:
            return {
                "success": False,
                "reason": "path parameter required",
                "logs": ["Please provide path parameter"],
                "data": None
            }

        try:
            os.chdir(path)
            new_cwd = os.getcwd()
            return {
                "success": True,
                "reason": f"Directory changed to: {new_cwd}",
                "logs": [f"Changed directory to {new_cwd}"],
                "data": {
                    "previous_directory": os.getcwd(),  # This will be the same as new_cwd after chdir
                    "new_directory": new_cwd
                }
            }
        except FileNotFoundError:
            return {
                "success": False,
                "reason": f"Directory not found: {path}",
                "logs": [f"Directory does not exist: {path}"],
                "data": {"path": path}
            }
        except NotADirectoryError:
            return {
                "success": False,
                "reason": f"Path is not a directory: {path}",
                "logs": [f"Path is not a directory: {path}"],
                "data": {"path": path}
            }
        except PermissionError:
            return {
                "success": False,
                "reason": f"Permission denied to access directory: {path}",
                "logs": [f"Permission denied: {path}"],
                "data": {"path": path}
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to change directory: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"path": path}
            }

    def _list_processes(self, **kwargs) -> Dict[str, Any]:
        """List running processes."""
        try:
            # Use tasklist on Windows or ps on Unix-like systems
            if os.name == 'nt':  # Windows
                command = ["tasklist", "/FO", "CSV"]
            else:  # Unix/Linux/macOS
                command = ["ps", "aux"]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                output = result.stdout
                lines = output.strip().split('\n')

                # Parse output based on platform
                if os.name == 'nt':  # Windows CSV format
                    # Skip header line
                    processes = []
                    for line in lines[1:]:
                        if line.strip():
                            # Simple CSV parsing - in production would use csv module
                            parts = [part.strip('"') for part in line.split('","')]
                            if len(parts) >= 2:
                                processes.append({
                                    "image_name": parts[0] if len(parts) > 0 else "",
                                    "pid": parts[1] if len(parts) > 1 else "",
                                    "session_name": parts[2] if len(parts) > 2 else "",
                                    "session_num": parts[3] if len(parts) > 3 else "",
                                    "mem_usage": parts[4] if len(parts) > 4 else ""
                                })
                else:  # Unix ps format
                    # Skip header line
                    processes = []
                    for line in lines[1:]:
                        if line.strip():
                            parts = line.split(None, 10)  # Split into max 11 parts
                            if len(parts) >= 11:
                                processes.append({
                                    "user": parts[0],
                                    "pid": parts[1],
                                    "cpu": parts[2],
                                    "mem": parts[3],
                                    "vsz": parts[4],
                                    "rss": parts[5],
                                    "tty": parts[6],
                                    "stat": parts[7],
                                    "start": parts[8],
                                    "time": parts[9],
                                    "command": parts[10]
                                })

                return {
                    "success": True,
                    "reason": f"Listed {len(processes)} processes",
                    "logs": [f"Retrieved process list: {len(processes)} processes"],
                    "data": {
                        "processes": processes,
                        "count": len(processes)
                    }
                }
            else:
                return {
                    "success": False,
                    "reason": f"Failed to list processes: {result.stderr}",
                    "logs": [f"Error listing processes: {result.stderr}"],
                    "data": None
                }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to list processes: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _kill_process(self, **kwargs) -> Dict[str, Any]:
        """Kill a process by ID or name."""
        pid = kwargs.get("pid")
        name = kwargs.get("name")

        if not pid and not name:
            return {
                "success": False,
                "reason": "Either pid or name parameter required",
                "logs": ["Please provide either pid or name parameter"],
                "data": None
            }

        try:
            if os.name == 'nt':  # Windows
                if pid:
                    command = ["taskkill", "/PID", str(pid), "/F"]
                else:
                    command = ["taskkill", "/IM", str(name), "/F"]
            else:  # Unix/Linux/macOS
                if pid:
                    command = ["kill", "-9", str(pid)]
                else:
                    # Find processes by name and kill them
                    pgrep_result = subprocess.run(
                        ["pgrep", "-f", str(name)],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if pgrep_result.returncode == 0 and pgrep_result.stdout.strip():
                        pids = pgrep_result.stdout.strip().split('\n')
                        for pid_str in pids:
                            if pid_str.strip():
                                subprocess.run(["kill", "-9", pid_str.strip()],
                                             capture_output=True, timeout=5)
                        return {
                            "success": True,
                            "reason": f"Killed processes matching name: {name}",
                            "logs": [f"Killed processes matching name: {name}"],
                            "data": {
                                "name": name,
                                "killed_pids": pids
                            }
                        }
                    else:
                        return {
                            "success": False,
                            "reason": f"No processes found with name: {name}",
                            "logs": [f"No processes found matching name: {name}"],
                            "data": {"name": name}
                        }

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=10
            )

            success = result.returncode == 0
            if success:
                reason = f"Process {'killed' if pid else 'processes matching name'} terminated successfully"
            else:
                reason = f"Failed to kill process: {result.stderr.strip()}"

            return {
                "success": success,
                "reason": reason,
                "logs": [
                    f"Kill command executed: {'pid ' + str(pid) if pid else 'name ' + str(name)}",
                    f"Exit code: {result.returncode}"
                ],
                "data": {
                    "pid": pid,
                    "name": name,
                    "killed": success
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to kill process: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"pid": pid, "name": name}
            }