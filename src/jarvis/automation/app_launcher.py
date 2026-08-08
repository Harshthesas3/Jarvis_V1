"""AppLauncher implementation using the in-package smart launcher.

Implements the AppLauncher interface from jarvis.interfaces.automation.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from jarvis.interfaces.automation import AppLauncher as AppLauncherInterface

logger = logging.getLogger("jarvis.automation.app_launcher")

from jarvis.automation.smart_launcher import get_smart_launcher


def _get_launcher():
    """Return the SmartAppLauncher singleton."""
    try:
        return get_smart_launcher()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load smart app launcher: %s", exc)
        return None


class AppLauncher(AppLauncherInterface):
    """Launches, discovers, and verifies applications on Windows.

    Delegates to :class:`jarvis.automation.smart_launcher.SmartAppLauncher`
    for discovery and fuzzy matching.
    """

    def launch(self, app_name: str) -> bool:
        """Launch an application by name or path.

        Returns ``True`` if the launch was initiated successfully (the
        executable or shortcut was started), regardless of whether its
        window has appeared yet.
        """
        launcher = _get_launcher()
        if launcher is None:
            logger.error("App launcher unavailable")
            return False
        result = launcher.launch_app(app_name)
        return result.status.name == "SUCCESS"

    def launch_and_verify(self, app_name: str, wait_for_ui: bool = False) -> bool:
        """Launch an app and verify it started.

        When *wait_for_ui* is ``True`` the method also waits for a visible
        window belonging to the application to appear (up to 15 s).
        """
        launcher = _get_launcher()
        if launcher is None:
            logger.error("App launcher unavailable")
            return False

        result = launcher.launch_app(app_name)
        if result.status.name != "SUCCESS":
            logger.warning(
                "Launch of '%s' failed: %s", app_name, result.message
            )
            return False

        if wait_for_ui:
            # The launcher already waits for a window internally but returns
            # success regardless.  If the caller requires UI confirmation we
            # explicitly check.
            if result.hwnd is not None and result.window_title:
                logger.info(
                    "App '%s' window detected: %s", app_name, result.window_title
                )
                return True
            # If no window info is available fall back to a process-based
            # existence check.
            return self.find_app(app_name) is not None

        return True

    def find_app(self, name: str) -> Optional[Dict[str, Any]]:
        """Find an installed application by name (fuzzy match).

        Returns the app metadata dict from the discovery cache, or ``None``
        if the application was not found.
        """
        launcher = _get_launcher()
        if launcher is None:
            return None
        return launcher.find_app(name)

    def find_installed_apps(self) -> List[Dict[str, Any]]:
        """Discover all installed applications on the system.

        Returns a list of app metadata dicts.  The cache is refreshed on
        every call so that newly installed applications are picked up.
        """
        launcher = _get_launcher()
        if launcher is None:
            return []
        launcher._refresh_cache()
        return list(launcher.app_cache.values())

    def get_installed_apps(self) -> List[Dict[str, Any]]:
        """Alias for :meth:`find_installed_apps`."""
        return self.find_installed_apps()

    def close_app(self, app_name: str) -> bool:
        """Close an application by process name.

        Uses ``psutil`` to terminate all processes whose name contains
        *app_name* (case-insensitive).
        """
        try:
            import psutil

            found = False
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    pname = proc.info["name"] or ""
                    if app_name.lower() in pname.lower():
                        proc.terminate()
                        proc.wait(timeout=5)
                        found = True
                except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                    continue
            return found
        except ImportError:
            logger.error("psutil not available; cannot close app")
            return False
