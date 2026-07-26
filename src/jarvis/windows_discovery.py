"""Windows Application Resolver for Voice-First JARVIS.

Native Windows application discovery and resolution for Voice-First mode.
No external package managers - pure Windows-native implementation.
"""

from __future__ import annotations

import os
import re
import json
import logging
import time
import itertools
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Any
from pathlib import Path

logger = logging.getLogger("jarvis.windows_discovery")


@dataclass
class DiscoveredApp:
    """Discovered Windows application."""
    name: str
    path: str
    display_name: str
    app_id: Optional[str] = None
    description: Optional[str] = None
    aliases: List[str] = None

    def __post_init__(self):
        if self.aliases is None:
            self.aliases = []

    def matches(self, query: str) -> bool:
        """Check if application matches query."""
        query_lower = query.lower()
        return (query_lower == self.name.lower() or
                query_lower == self.display_name.lower() or
                any(query_lower == alias.lower() for alias in self.aliases) or
                query_lower in self.name.lower() or

                query_lower in self.display_name.lower())


class ApplicationResolver:
    """
    Native Windows application resolver for Voice-First JARVIS.

    Discovers applications from:
    - Start Menu shortcuts
    - Desktop shortcuts
    - PATH executables
    - App Execution Aliases
    - Installed Programs registry
    - WindowsApps folder
    - Known installation directories

    Maintains persistent in-memory cache with automatic refresh.
    Supports fuzzy matching and aliases for robust app launching.
    """

    def __init__(self, cache_duration: int = 3600):
        """
        Initialize ApplicationResolver.

        Args:
            cache_duration: Cache duration in seconds (default: 1 hour)
        """
        self.cache_duration = cache_duration
        self._apps_cache: Dict[str, List[DiscoveredApp]] = {}
        self._last_refresh: Dict[str, float] = {}
        # Load asynchronously to avoid blocking the API server or voice loop
        import threading
        threading.Thread(target=self._initial_load, daemon=True).start()

    def _initial_load(self):
        """Initial load of application caches."""
        logger.info("Loading application cache from Windows sources...")
        self.refresh_cache()

    def refresh_cache(self):
        """Refresh application cache from all sources."""
        current_time = time.time()
        
        sources = [
            ("start_menu", self._load_start_menu_apps),
            ("desktop", self._load_desktop_apps),
            ("path", self._load_path_executables),
            ("app_aliases", self._load_app_execution_aliases),
            ("installed_programs", self._load_installed_programs),
            ("windowsapps", self._load_windowsapps),
            ("common_programs", self._load_common_programs),
        ]
        
        for source_name, loader in sources:
            try:
                apps = loader()
                self._apps_cache[source_name] = apps
                self._last_refresh[source_name] = current_time
                logger.info("Loaded %d apps from %s", len(apps), source_name)
            except Exception as e:
                logger.warning("Failed to load apps from %s: %s", source_name, e)

    def _load_start_menu_apps(self) -> List[DiscoveredApp]:
        """Load applications from Start Menu."""
        apps = []
        
        # Common Start Menu paths
        start_menu_paths = [
            Path(os.path.expanduser("~")) / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu",
            Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu",
            Path(os.environ.get("ALLUSERSPROFILE", "")) / "Start Menu",
        ]
        
        for start_menu_path in start_menu_paths:
            if not start_menu_path.exists():
                continue
                
            for exe_file in start_menu_path.glob("*.lnk"):
                try:
                    import win32com.shell
                    shell_item = win32com.shell.ShellItem.CreateFromParsingName(str(exe_file))
                    display_name = shell_item.DisplayName
                    target_path = self._extract_target_from_lnk(str(exe_file))

                    if display_name and target_path:
                        app_name = self._normalize_app_name(display_name)
                        alias_set = self._generate_app_aliases(app_name)

                        app = DiscoveredApp(
                            name=app_name,
                            path=target_path,
                            display_name=display_name,
                            app_id=exe_file.stem,
                            aliases=list(alias_set)
                        )
                        apps.append(app)
                except Exception as e:
                    logger.debug("Failed to read shortcut %s: %s", exe_file, e)

        return apps

    def _load_desktop_apps(self) -> List[DiscoveredApp]:
        """Load applications from Desktop."""
        apps = []
        desktop_path = Path(os.path.expanduser("~")) / "Desktop"

        if not desktop_path.exists():
            return apps

        for item in desktop_path.iterdir():
            if item.is_file() and item.suffix == ".lnk":
                try:
                    display_name = os.path.splitext(item.stem)[0]
                    target_path = self._extract_target_from_lnk(str(item))

                    if display_name and target_path:
                        app_name = self._normalize_app_name(display_name)

                        app = DiscoveredApp(
                            name=app_name,
                            path=target_path,
                            display_name=display_name,
                            app_id=item.stem,
                            aliases=[]
                        )
                        apps.append(app)
                except Exception as e:
                    logger.debug("Failed to read desktop shortcut %s: %s", item, e)

        return apps

    def _load_path_executables(self) -> List[Dict[str, str]]:
        """Load executables from PATH."""
        apps = []
        try:
            path_env = os.environ.get("PATH", "")
            paths = path_env.split(os.pathsep)

            for path_dir in paths:
                path_dir = path_dir.strip()
                if not path_dir or not os.path.isdir(path_dir):
                    continue

                for exe_file in os.scandir(path_dir):
                    if exe_file.name.lower().endswith(".exe"):
                        try:
                            app_name = os.path.splitext(exe_file.name)[0]
                            resolved_path = self._resolve_app_with_preferences(app_name)

                            app = DiscoveredApp(
                                name=app_name,
                                path=resolved_path,
                                display_name=self._format_app_display_name(app_name, resolved_path),
                                app_id=exe_file.name,
                                aliases=self._generate_app_aliases(app_name)
                            )
                            apps.append(app)
                        except Exception as e:
                            logger.debug("Failed to scan %s: %s", exe_file.path, e)

        except Exception as e:
            logger.warning("Failed to load PATH executables: %s", e)

        return apps

    def _load_app_execution_aliases(self) -> List[DiscoveredApp]:
        """Load App Execution Aliases (Windows 10/11)."""
        apps = []
        aliases_path = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "AppExecution"

        if not aliases_path.exists():
            return apps

        for alias_file in aliases_path.glob("*.json"):
            try:
                with open(alias_file, "r") as f:
                    data = json.load(f)

                executable = data.get("executable")
                alias = data.get("alias")
                display_name = data.get("displayName", alias)

                if executable and alias:
                    # Resolve executable path
                    resolved_path = self._resolve_app_with_preferences(executable)

                    app = DiscoveredApp(
                        name=alias,
                        path=resolved_path,
                        display_name=display_name,
                        app_id=alias,
                        aliases=[executable]
                    )
                    apps.append(app)
            except Exception as e:
                logger.debug("Failed to read alias %s: %s", alias_file, e)

        return apps

    def _load_installed_programs(self) -> List[DiscoveredApp]:
        """Load applications from Installed Programs registry."""
        apps = []
        try:
            import win32api

            # Registry path for installed programs
            reg_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"

            for exe_path in win32api.RegEnumKey(win32api.HKEY_LOCAL_MACHINE, reg_path):
                try:
                    exe_key = f"{reg_path}\\${exe_path}"
                    display_name = win32api.RegQueryValueEx(win32api.HKEY_LOCAL_MACHINE, exe_key)[0]

                    app_name = os.path.splitext(exe_path)[0]
                    alias_set = self._generate_app_aliases(app_name)

                    app = DiscoveredApp(
                        name=app_name,
                        path=exe_path,
                        display_name=display_name,
                        app_id=exe_path,
                        aliases=list(alias_set)
                    )
                    apps.append(app)
                except Exception as e:
                    logger.debug("Failed to read registry entry %s: %s", exe_path, e)

        except ImportError:
            logger.warning("win32api not available, skipping registry load")

        return apps

    def _load_windowsapps(self) -> List[DiscoveredApp]:
        """Load applications from WindowsApps folder (UWP/MSIX)."""
        apps = []
        windowsapps_paths = []

        program_files = os.environ.get("PROGRAMFILESX86") or os.environ.get("PROGRAMFILES")
        if program_files:
            windowsapps_paths.append(Path(program_files) / "WindowsApps")

        appdata_local = os.environ.get("LOCALAPPDATA")
        if appdata_local:
            windowsapps_paths.append(Path(appdata_local) / "Packages")

        for base_path in windowsapps_paths:
            if not base_path.exists():
                continue

            for package_dir in base_path.glob("*/"):
                manifest_path = package_dir / "AppXManifest.xml"
                if manifest_path.exists():
                    try:
                        import xml.etree.ElementTree as ET
                        tree = ET.parse(manifest_path)
                        root = tree.getroot()

                        # XML namespace handling
                        namespace = {"": "http://schemas.microsoft.com/appx/manifest/foundation/1.1"}
                        display_name = root.find(f'.//{namespace[""]}Applications/{namespace[""]}Application/{namespace[""]}DisplayName')

                        if display_name is not None:
                            app_name = display_name.text
                            executable = root.find(f'.//{namespace[""]}Applications/{namespace[""]}Application/{namespace[""]}Executable')

                            if executable is not None:
                                exe_path = executable.text
                                if exe_path:
                                    # Resolve UWP executable
                                    resolved_path = self._resolve_uwp_executable(str(package_dir), exe_path)

                                    app = DiscoveredApp(
                                        name=app_name,
                                        path=resolved_path,
                                        display_name=app_name,
                                        app_id=str(package_dir),
                                        aliases=[app_name]
                                    )
                                    apps.append(app)
                    except Exception as e:
                        logger.debug("Failed to parse UWP manifest %s: %s", manifest_path, e)

        return apps

    def _load_common_programs(self) -> List[DiscoveredApp]:
        """Load common system programs."""
        common_programs = [
            ("notepad", "notepad.exe"),
            ("calculator", "calc.exe"),
            ("paint", "mspaint.exe"),
            ("chrome", "chrome.exe"),
            ("firefox", "firefox.exe"),
            ("edge", "msedge.exe"),
            ("terminal", "wt.exe"),
            ("powershell", "powershell.exe"),
            ("cmd", "cmd.exe"),
            ("explorer", "explorer.exe"),
            ("discord", "Discord.exe"),
            ("teams", "Teams.exe"),
            ("slack", "slack.exe"),
            ("zoom", "zoom.exe"),
            ("git", "git.exe"),
            ("vscode", "code.exe"),
            ("python", "python.exe"),
            ("node", "node.exe"),
            ("npm", "npm.cmd"),
            ("docker", "docker.exe"),
            ("git bash", "bash.exe"),
        ]

        apps = []
        for app_name, exe_name in common_programs:
            resolved_path = self._find_executable_path(exe_name)
            if resolved_path:
                app = DiscoveredApp(
                    name=app_name,
                    path=resolved_path,
                    display_name=self._format_app_display_name(app_name, resolved_path),
                    app_id=exe_name,
                    aliases=self._generate_app_aliases(app_name)
                )
                apps.append(app)

        return apps

    def _normalize_app_name(self, name: str) -> str:
        """Normalize application name for consistency."""
        normalized = name.lower()

        # Common normalization rules
        normalized = re.sub(r"\s+(?:corp|llc|ltd|group|company|inc|incorporated)\s*$", "", normalized)
        normalized = re.sub(r"\s+(?:the|\&)\s+", " ", normalized)
        normalized = re.sub(r"\s+from\s+.*$", "", normalized)
        normalized = re.sub(r"\s+\(.*\)$", "", normalized)

        return normalized.strip()

    def _generate_app_aliases(self, app_name: str) -> Set[str]:
        """Generate common aliases for an application."""
        aliases = set()

        # Lowercase version
        aliases.add(app_name)

        # Common variations
        variations = [
            app_name.replace(" ", ""),
            app_name.replace(" ", ""),
            app_name.replace(" ", ""),
            app_name.upper(),
            app_name.title(),
        ]

        for variation in variations:
            aliases.add(variation.lower())

        # Special case for common apps
        if app_name == "visual studio code":
            aliases.update(["vs code", "vscode", "vsc"])
        elif app_name == "microsoft edge":
            aliases.update(["edge", "msedge"])
        elif app_name == "google chrome":
            aliases.update(["chrome", "google chrome"])
        elif app_name == "notepad++":
            aliases.update(["npp"])
        elif app_name == "file explorer":
            aliases.update(["explorer", "file explorer"])
        elif app_name == "windows terminal":
            aliases.update(["terminal", "wt", "windows terminal"])
        elif app_name == "microsoft store":
            aliases.update(["store", "ms store"])

        return aliases

    def _extract_target_from_lnk(self, lnk_path: str) -> Optional[str]:
        """Extract target path from Windows .lnk file."""
        try:
            import pythoncom
            from win32com.shell import shell

            shell_link = pythoncom.CoCreateInstance(
                shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER)
            persist_file = shell_link.QueryInterface(pythoncom.IID_IPersistFile)

            persist_file.Load(str(lnk_path))

            resolved_path = shell_link.GetPath(pythoncom.DESKTOP_ITEMIDLIST_ALL)
            return resolved_path
        except Exception as e:
            logger.debug("Failed to extract target from %s: %s", lnk_path, e)
            return None

    def _resolve_app_with_preferences(self, app_name: str) -> str:
        """Resolve application with preference for known installations."""
        # Check common installation directories
        common_paths = [
            Path("C:/Program Files"),
            Path("C:/Program Files (x86)"),
            Path(os.path.expanduser("~")) / "AppData" / "Local",
        ]

        for base_path in common_paths:
            # Try different executable naming patterns
            for pattern in [f"{app_name}.exe", f"{app_name}.lnk"]:
                exe_path = base_path / pattern
                if exe_path.exists():
                    return str(exe_path.resolve())

                # Search recursively for executables with similar names
                for exe_file in base_path.glob(f"**/{pattern}"):
                    if exe_file.is_file():
                        return str(exe_file.resolve())

        # Last resort: use PATH search
        resolved = self._find_executable_path(f"{app_name}.exe")
        if resolved:
            return resolved

        # Return placeholder - will be resolved on launch
        return f"{app_name}.exe"

    def _resolve_uwp_executable(self, package_dir: str, exe_in_manifest: str) -> str:
        """Resolve UWP/MSIX executable path."""
        try:
            # UWP executables are typically in the package directory
            exe_filename = os.path.basename(exe_in_manifest)
            exe_path = Path(package_dir) / exe_filename

            if exe_path.exists():
                return str(exe_path.resolve())

            # Try common UWP executable locations
            possible_paths = [
                exe_path,
                Path(package_dir) / "Files" / exe_filename,
                Path(package_dir) / "rootfs" / exe_filename,
            ]

            for path in possible_paths:
                if path.exists():
                    return str(path.resolve())

        except Exception as e:
            logger.debug("Failed to resolve UWP executable: %s", e)

        return exe_in_manifest

    def _find_executable_path(self, exe_name: str) -> Optional[str]:
        """Find executable path in PATH or common directories."""
        # Check PATH
        for path_dir in os.environ.get("PATH", "").split(os.pathsep):
            path_dir = path_dir.strip()
            exe_path = Path(path_dir) / exe_name
            if exe_path.exists():
                return str(exe_path.resolve())

        # Check common program files
        program_files = ["C:/Program Files", "C:/Program Files (x86)"]
        for base_dir in program_files:
            exe_path = Path(base_dir) / exe_name
            if exe_path.exists():
                return str(exe_path.resolve())

        return None

    def _format_app_display_name(self, app_name: str, path: str) -> str:
        """Format application display name."""
        # Clean up app name for display
        display_name = app_name

        # Remove common technical suffixes
        replacements = {
            "_64": " 64-bit",
            "x64": " 64-bit",
            "x86": " 32-bit",
            "x32": " 32-bit",
            "64bit": " 64-bit",
            "86bit": " 32-bit",
            "x86_64": " 64-bit",
            "amd64": " 64-bit",
        }

        for suffix, readable in replacements.items():
            if suffix in display_name.lower():
                display_name = display_name.replace(suffix, readable)

        return display_name

    def find_app(self, query: str) -> Optional[DiscoveredApp]:
        """
        Find application matching query.

        Args:
            query: Search query (app name, alias, partial name)

        Returns:
            DiscoveredApp if found, None otherwise
        """
        if not query:
            return None

        query_lower = query.lower().strip()

        # First try exact matches
        for source_name, apps in self._apps_cache.items():
            for app in apps:
                if app.matches(query):
                    return app

        # Then try partial matches
        for source_name, apps in self._apps_cache.items():
            for app in apps:
                if (query_lower in app.name.lower() or
                    query_lower in app.display_name.lower() or
                    any(query_lower == alias.lower() for alias in app.aliases)):
                    return app

        return None

    def get_all_apps(self) -> List[DiscoveredApp]:
        """
        Get all discovered applications.

        Returns:
            List of all discovered applications
        """
        all_apps = []
        for apps in self._apps_cache.values():
            all_apps.extend(apps)

        # Remove duplicates based on path
        seen = set()
        unique_apps = []
        for app in all_apps:
            if app.path not in seen:
                seen.add(app.path)
                unique_apps.append(app)

        return unique_apps

    def get_apps_by_category(self, category: str) -> List[DiscoveredApp]:
        """
        Get applications by category.

        Args:
            category: Application category (start_menu, desktop, path, etc.)

        Returns:
            List of applications in category
        """
        return self._apps_cache.get(category, [])

    def search_apps(self, query: str, limit: int = 10) -> List[DiscoveredApp]:
        """
        Search for applications by query.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching applications
        """
        if not query:
            return []

        query_lower = query.lower()
        results = []

        for source_name, apps in self._apps_cache.items():
            for app in apps:
                if (query_lower in app.name.lower() or
                    query_lower in app.display_name.lower() or
                    any(query_lower == alias.lower() for alias in app.aliases)):
                    results.append(app)
                    if len(results) >= limit:
                        return results

        return results

    def get_popular_apps(self, limit: int = 20) -> List[DiscoveredApp]:
        """
        Get popular/frequently used applications.

        Args:
            limit: Maximum number of results

        Returns:
            List of popular applications
        """
        all_apps = self.get_all_apps()

        # Sort by common application names (they tend to be popular)
        def popularity_score(app: DiscoveredApp) -> float:
            name = app.name.lower()
            # Common popular apps get higher scores
            if name in ["chrome", "firefox", "safari", "edge", "browser"]:
                return 10
            elif name in ["vscode", "vim", "emacs", "sublime", "notepad"]:
                return 9
            elif name in ["spotify", "vlc", "youtube", "netflix"]:
                return 8
            elif name in ["steam", "epic", "gog", "itch"]:
                return 7
            elif name in ["discord", "teams", "slack", "whatsapp"]:
                return 6
            elif name in ["photoshop", "illustrator", "gimp"]:
                return 5
            else:
                return 1

        sorted_apps = sorted(all_apps, key=popularity_score, reverse=True)
        return sorted_apps[:limit]

    def is_apps_cache_valid(self) -> bool:
        """
        Check if application cache is valid.

        Returns:
            True if cache is valid and fresh
        """
        current_time = time.time()
        for source_name, last_refresh in self._last_refresh.items():
            if current_time - last_refresh > self.cache_duration:
                return False
        return True


def get_application_resolver() -> ApplicationResolver:
    """
    Get global ApplicationResolver instance.

    Returns:
        ApplicationResolver instance
    """
    if not hasattr(get_application_resolver, "_instance"):
        get_application_resolver._instance = ApplicationResolver()
    return get_application_resolver._instance


def refresh_application_cache():
    """
    Refresh global application cache.

    This can be called periodically to update application list.
    """
    resolver = get_application_resolver()
    resolver.refresh_cache()
    logger.info("Application cache refreshed")
