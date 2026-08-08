"""VS Code skill implementation."""

from __future__ import annotations

import logging
import subprocess
import time
from typing import Any, Dict, List, Optional

from jarvis.windows_discovery import get_application_resolver
from jarvis.skills.interfaces import SkillInterface

logger = logging.getLogger("jarvis.skills.vscode")


class VSCodeSkill(SkillInterface):
    """Skill for VS Code operations."""

    @property
    def name(self) -> str:
        return "vscode"

    @property
    def description(self) -> str:
        return "VS Code editor operations including launching, file opening, and workspace management"

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute VS Code operations.

        Supported operations:
        - launch: Launch VS Code
        - open_file: Open a file in VS Code
        - open_folder: Open a folder in VS Code
        - open_workspace: Open a workspace in VS Code
        - install_extension: Install a VS Code extension
        - list_extensions: List installed extensions
        - run_command: Run a VS Code command

        Args:
            action: Operation to perform
            **kwargs: Operation-specific arguments

        Returns:
            Dictionary with execution results
        """
        start_time = time.time()
        action = kwargs.get("action", "").lower()

        try:
            resolver = get_application_resolver()

            if action == "launch":
                result = self._launch_vscode(resolver, **kwargs)
            elif action == "open_file":
                result = self._open_file(resolver, **kwargs)
            elif action == "open_folder":
                result = self._open_folder(resolver, **kwargs)
            elif action == "open_workspace":
                result = self._open_workspace(resolver, **kwargs)
            elif action == "install_extension":
                result = self._install_extension(resolver, **kwargs)
            elif action == "list_extensions":
                result = self._list_extensions(resolver, **kwargs)
            elif action == "run_command":
                result = self._run_command(resolver, **kwargs)
            else:
                result = {
                    "success": False,
                    "reason": f"Unknown action: {action}",
                    "logs": [
                        f"Available actions: launch, open_file, open_folder, open_workspace, "
                        f"install_extension, list_extensions, run_command"
                    ],
                    "data": None
                }

            # Add execution time to result
            result["execution_time"] = time.time() - start_time
            return result

        except Exception as e:
            logger.error("VSCodeSkill execution failed: %s", e, exc_info=True)
            return {
                "success": False,
                "reason": f"VSCodeSkill execution failed: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None,
                "execution_time": time.time() - start_time
            }

    def _launch_vscode(self, resolver, **kwargs) -> Dict[str, Any]:
        """Launch VS Code."""
        try:
            app = resolver.find_app("vscode")
            if not app:
                return {
                    "success": False,
                    "reason": "VS Code not found",
                    "logs": ["VS Code not found in installed applications"],
                    "data": None
                }

            # Launch VS Code using the app launcher
            from jarvis.automation import AppLauncher
            launcher = AppLauncher()
            success = launcher.launch(app.name)

            return {
                "success": success,
                "reason": f"VS Code launch {'successful' if success else 'failed'}",
                "logs": [f"Launching VS Code ({app.name})..."],
                "data": {
                    "app_name": app.name,
                    "app_path": app.path,
                    "launched": success
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to launch VS Code: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _open_file(self, resolver, **kwargs) -> Dict[str, Any]:
        """Open a file in VS Code."""
        file_path = kwargs.get("file_path")
        if not file_path:
            return {
                "success": False,
                "reason": "file_path parameter required",
                "logs": ["Please provide file_path parameter"],
                "data": None
            }

        try:
            # Import path handling
            from pathlib import Path
            path_obj = Path(file_path)
            if not path_obj.exists():
                return {
                    "success": False,
                    "reason": f"File does not exist: {file_path}",
                    "logs": [f"File not found: {file_path}"],
                    "data": None
                }

            app = resolver.find_app("vscode")
            if not app:
                return {
                    "success": False,
                    "reason": "VS Code not found",
                    "logs": ["VS Code not found in installed applications"],
                    "data": None
                }

            # Launch VS Code with file argument
            from jarvis.automation import AppLauncher
            launcher = AppLauncher()
            success = launcher.launch(f"{app.name} \"{file_path}\"")

            return {
                "success": success,
                "reason": f"File opened in VS Code: {file_path}" if success else f"Failed to open file: {file_path}",
                "logs": [f"Opening {file_path} in VS Code..."],
                "data": {
                    "file_path": str(path_obj.resolve()),
                    "opened": success
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to open file: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"file_path": file_path}
            }

    def _open_folder(self, resolver, **kwargs) -> Dict[str, Any]:
        """Open a folder in VS Code."""
        folder_path = kwargs.get("folder_path")
        if not folder_path:
            return {
                "success": False,
                "reason": "folder_path parameter required",
                "logs": ["Please provide folder_path parameter"],
                "data": None
            }

        try:
            from pathlib import Path
            path_obj = Path(folder_path)
            if not path_obj.exists():
                return {
                    "success": False,
                    "reason": f"Folder does not exist: {folder_path}",
                    "logs": [f"Folder not found: {folder_path}"],
                    "data": None
                }

            if not path_obj.is_dir():
                return {
                    "success": False,
                    "reason": f"Path is not a directory: {folder_path}",
                    "logs": [f"Path is a file, not directory: {folder_path}"],
                    "data": None
                }

            app = resolver.find_app("vscode")
            if not app:
                return {
                    "success": False,
                    "reason": "VS Code not found",
                    "logs": ["VS Code not found in installed applications"],
                    "data": None
                }

            # Launch VS Code with folder argument
            from jarvis.automation import AppLauncher
            launcher = AppLauncher()
            success = launcher.launch(f"{app.name} \"{folder_path}\"")

            return {
                "success": success,
                "reason": f"Folder opened in VS Code: {folder_path}" if success else f"Failed to open folder: {folder_path}",
                "logs": [f"Opening {folder_path} in VS Code..."],
                "data": {
                    "folder_path": str(path_obj.resolve()),
                    "opened": success
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to open folder: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"folder_path": folder_path}
            }

    def _open_workspace(self, resolver, **kwargs) -> Dict[str, Any]:
        """Open a workspace in VS Code."""
        workspace_path = kwargs.get("workspace_path")
        if not workspace_path:
            return {
                "success": False,
                "reason": "workspace_path parameter required",
                "logs": ["Please provide workspace_path parameter"],
                "data": None
            }

        try:
            from pathlib import Path
            path_obj = Path(workspace_path)
            if not path_obj.exists():
                return {
                    "success": False,
                    "reason": f"Workspace does not exist: {workspace_path}",
                    "logs": [f"Workspace not found: {workspace_path}"],
                    "data": None
                }

            if not path_obj.is_file() or path_obj.suffix.lower() != ".code-workspace":
                return {
                    "success": False,
                    "reason": f"Path is not a VS Code workspace file: {workspace_path}",
                    "logs": [f"Expected .code-workspace file, got: {path_obj.suffix}"],
                    "data": None
                }

            app = resolver.find_app("vscode")
            if not app:
                return {
                    "success": False,
                    "reason": "VS Code not found",
                    "logs": ["VS Code not found in installed applications"],
                    "data": None
                }

            # Launch VS Code with workspace argument
            from jarvis.automation import AppLauncher
            launcher = AppLauncher()
            success = launcher.launch(f"{app.name} \"{workspace_path}\"")

            return {
                "success": success,
                "reason": f"Workspace opened in VS Code: {workspace_path}" if success else f"Failed to open workspace: {workspace_path}",
                "logs": [f"Opening {workspace_path} in VS Code..."],
                "data": {
                    "workspace_path": str(path_obj.resolve()),
                    "opened": success
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to open workspace: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"workspace_path": workspace_path}
            }

    def _install_extension(self, resolver, **kwargs) -> Dict[str, Any]:
        """Install a VS Code extension."""
        extension_id = kwargs.get("extension_id")
        if not extension_id:
            return {
                "success": False,
                "reason": "extension_id parameter required",
                "logs": ["Please provide extension_id parameter"],
                "data": None
            }

        try:
            app = resolver.find_app("vscode")
            if not app:
                return {
                    "success": False,
                    "reason": "VS Code not found",
                    "logs": ["VS Code not found in installed applications"],
                    "data": None
                }

            # Use code command line interface to install extension
            result = subprocess.run(
                ["code", "--install-extension", extension_id],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "reason": f"Extension installed: {extension_id}",
                    "logs": [f"Extension installation successful: {extension_id}"],
                    "data": {
                        "extension_id": extension_id,
                        "installed": True,
                        "output": result.stdout.strip()[:200]  # Limit output size
                    }
                }
            else:
                return {
                    "success": False,
                    "reason": f"Extension installation failed: {result.stderr.strip()}",
                    "logs": [
                        f"Extension installation failed: {extension_id}",
                        f"Error: {result.stderr.strip()}"
                    ],
                    "data": {
                        "extension_id": extension_id,
                        "installed": False,
                        "error": result.stderr.strip()[:200]
                    }
                }
        except FileNotFoundError:
            return {
                "success": False,
                "reason": "VS Code CLI not found in PATH",
                "logs": ["VS Code command line interface not available"],
                "data": {"extension_id": extension_id}
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to install extension: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"extension_id": extension_id}
            }

    def _list_extensions(self, resolver, **kwargs) -> Dict[str, Any]:
        """List installed VS Code extensions."""
        try:
            app = resolver.find_app("vscode")
            if not app:
                return {
                    "success": False,
                    "reason": "VS Code not found",
                    "logs": ["VS Code not found in installed applications"],
                    "data": None
                }

            # Use code command line interface to list extensions
            result = subprocess.run(
                ["code", "--list-extensions"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            if result.returncode == 0:
                extensions = [ext.strip() for ext in result.stdout.strip().split('\n') if ext.strip()]
                return {
                    "success": True,
                    "reason": f"Found {len(extensions)} installed extensions",
                    "logs": [f"Listed {len(extensions)} VS Code extensions"],
                    "data": {
                        "extensions": extensions,
                        "count": len(extensions)
                    }
                }
            else:
                return {
                    "success": False,
                    "reason": f"Failed to list extensions: {result.stderr.strip()}",
                    "logs": [f"Error listing extensions: {result.stderr.strip()}"],
                    "data": None
                }
        except FileNotFoundError:
            return {
                "success": False,
                "reason": "VS Code CLI not found in PATH",
                "logs": ["VS Code command line interface not available"],
                "data": None
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to list extensions: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _run_command(self, resolver, **kwargs) -> Dict[str, Any]:
        """Run a VS Code command."""
        command = kwargs.get("command")
        if not command:
            return {
                "success": False,
                "reason": "command parameter required",
                "logs": ["Please provide command parameter"],
                "data": None
            }

        try:
            app = resolver.find_app("vscode")
            if not app:
                return {
                    "success": False,
                    "reason": "VS Code not found",
                    "logs": ["VS Code not found in installed applications"],
                    "data": None
                }

            # Use code command line interface to run command
            result = subprocess.run(
                ["code", "--command", command],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "reason": f"Command executed: {command}",
                    "logs": [f"VS Code command executed: {command}"],
                    "data": {
                        "command": command,
                        "executed": True,
                        "output": result.stdout.strip()[:200]  # Limit output size
                    }
                }
            else:
                return {
                    "success": False,
                    "reason": f"Command execution failed: {result.stderr.strip()}",
                    "logs": [
                        f"VS Code command failed: {command}",
                        f"Error: {result.stderr.strip()}"
                    ],
                    "data": {
                        "command": command,
                        "executed": False,
                        "error": result.stderr.strip()[:200]
                    }
                }
        except FileNotFoundError:
            return {
                "success": False,
                "reason": "VS Code CLI not found in PATH",
                "logs": ["VS Code command line interface not available"],
                "data": {"command": command}
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to run command: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"command": command}
            }