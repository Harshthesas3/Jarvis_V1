"""Windows-specific skill implementation."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from jarvis.automation import AppLauncher
from jarvis.skills.interfaces import SkillInterface

logger = logging.getLogger("jarvis.skills.windows")


class WindowsSkill(SkillInterface):
    """Skill for Windows system operations."""

    @property
    def name(self) -> str:
        return "windows"

    @property
    def description(self) -> str:
        return "Windows system operations including app launching and management"

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute Windows operations.

        Supported operations:
        - launch_app: Launch an application by name
        - launch_and_verify: Launch and verify app started
        - find_app: Find installed application
        - find_installed_apps: List all installed apps
        - close_app: Close an application

        Args:
            action: Operation to perform
            **kwargs: Operation-specific arguments

        Returns:
            Dictionary with execution results
        """
        action = kwargs.get("action", "").lower()

        try:
            launcher = AppLauncher()

            if action == "launch_app":
                return self._launch_app(launcher, **kwargs)
            elif action == "launch_and_verify":
                return self._launch_and_verify(launcher, **kwargs)
            elif action == "find_app":
                return self._find_app(launcher, **kwargs)
            elif action == "find_installed_apps":
                return self._find_installed_apps(launcher, **kwargs)
            elif action == "close_app":
                return self._close_app(launcher, **kwargs)
            else:
                return {
                    "success": False,
                    "reason": f"Unknown action: {action}",
                    "logs": [f"Available actions: launch_app, launch_and_verify, find_app, find_installed_apps, close_app"],
                    "data": None
                }

        except Exception as e:
            logger.error("WindowsSkill execution failed: %s", e, exc_info=True)
            return {
                "success": False,
                "reason": f"WindowsSkill execution failed: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _launch_app(self, launcher: AppLauncher, **kwargs) -> Dict[str, Any]:
        """Launch an application."""
        app_name = kwargs.get("app_name")
        if not app_name:
            return {
                "success": False,
                "reason": "app_name parameter required",
                "logs": ["Please provide app_name parameter"],
                "data": None
            }

        try:
            success = launcher.launch(app_name)
            return {
                "success": success,
                "reason": f"App launch {'successful' if success else 'failed'}: {app_name}",
                "logs": [f"Launching {app_name}...", f"Result: {'Success' if success else 'Failed'}"],
                "data": {"app_name": app_name, "launched": success}
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to launch app: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"app_name": app_name}
            }

    def _launch_and_verify(self, launcher: AppLauncher, **kwargs) -> Dict[str, Any]:
        """Launch and verify an application."""
        app_name = kwargs.get("app_name")
        wait_for_ui = kwargs.get("wait_for_ui", False)

        if not app_name:
            return {
                "success": False,
                "reason": "app_name parameter required",
                "logs": ["Please provide app_name parameter"],
                "data": None
            }

        try:
            success = launcher.launch_and_verify(app_name, wait_for_ui)
            return {
                "success": success,
                "reason": f"App launch {'successful' if success else 'failed'}: {app_name}",
                "logs": [f"Launching {app_name}...", f"Result: {'Success' if success else 'Failed'}"],
                "data": {"app_name": app_name, "launched": success}
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to launch and verify app: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"app_name": app_name}
            }

    def _find_app(self, launcher: AppLauncher, **kwargs) -> Dict[str, Any]:
        """Find an installed application."""
        app_name = kwargs.get("app_name")
        if not app_name:
            return {
                "success": False,
                "reason": "app_name parameter required",
                "logs": ["Please provide app_name parameter"],
                "data": None
            }

        try:
            app = launcher.find_app(app_name)
            if app:
                return {
                    "success": True,
                    "reason": f"App found: {app_name}",
                    "logs": [f"Found {app_name}", f"Path: {app.get('path', 'N/A')}"],
                    "data": app
                }
            else:
                return {
                    "success": False,
                    "reason": f"App not found: {app_name}",
                    "logs": [f"Could not find {app_name} in installed applications"],
                    "data": None
                }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to find app: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"app_name": app_name}
            }

    def _find_installed_apps(self, launcher: AppLauncher, **kwargs) -> Dict[str, Any]:
        """List all installed applications."""
        try:
            apps = launcher.find_installed_apps()
            return {
                "success": True,
                "reason": f"Found {len(apps)} installed applications",
                "logs": [f"Discovered {len(apps)} applications"],
                "data": {
                    "count": len(apps),
                    "applications": apps[:100]  # Limit to 100 to avoid huge responses
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to list installed apps: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _close_app(self, launcher: AppLauncher, **kwargs) -> Dict[str, Any]:
        """Close an application."""
        app_name = kwargs.get("app_name")
        if not app_name:
            return {
                "success": False,
                "reason": "app_name parameter required",
                "logs": ["Please provide app_name parameter"],
                "data": None
            }

        try:
            success = launcher.close_app(app_name)
            return {
                "success": success,
                "reason": f"App close {'successful' if success else 'failed'}: {app_name}",
                "logs": [f"Closing {app_name}...", f"Result: {'Success' if success else 'Failed'}"],
                "data": {"app_name": app_name, "closed": success}
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to close app: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"app_name": app_name}
            }
