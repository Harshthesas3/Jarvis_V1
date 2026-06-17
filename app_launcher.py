"""
app_launcher.py
Production-grade application launcher that can open ANY app on Windows.
"""

import os
import subprocess
import time
import logging
import psutil
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from enum import Enum
import winreg
import glob

logger = logging.getLogger("jarvis.app_launcher")

class LaunchStatus(Enum):
    SUCCESS = "success"
    PROCESS_NOT_FOUND = "process_not_found"
    WINDOW_NOT_FOUND = "window_not_found"
    FOCUS_FAILED = "focus_failed"
    UI_NOT_READY = "ui_not_ready"
    LAUNCH_FAILED = "launch_failed"

@dataclass
class LaunchResult:
    status: LaunchStatus
    message: str
    process_id: Optional[int] = None
    window_title: Optional[str] = None
    hwnd: Optional[int] = None
    search_ready: bool = False


class AppDiscovery:
    """Discovers ALL installed applications on Windows."""
    
    @staticmethod
    def discover_all_apps() -> Dict[str, Dict[str, Any]]:
        """Discover all installed applications from multiple sources."""
        apps = {}
        
        # 1. Start Menu shortcuts
        apps.update(AppDiscovery._scan_start_menu())
        
        # 2. Registry App Paths
        apps.update(AppDiscovery._scan_registry_app_paths())
        
        # 3. UWP/Store Apps
        apps.update(AppDiscovery._scan_uwp_apps())
        
        # 4. Common install locations
        apps.update(AppDiscovery._scan_common_locations())
        
        return apps
    
    @staticmethod
    def _scan_start_menu() -> Dict[str, Dict[str, Any]]:
        """Scan Start Menu for shortcuts."""
        apps = {}
        start_menu_paths = [
            os.path.join(os.environ.get("PROGRAMDATA", "C:\\ProgramData"), 
                        "Microsoft", "Windows", "Start Menu", "Programs"),
            os.path.join(os.environ.get("APPDATA", ""), 
                        "Microsoft", "Windows", "Start Menu", "Programs"),
            r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
        ]
        
        for base in start_menu_paths:
            if not os.path.isdir(base):
                continue
            
            for root, dirs, files in os.walk(base):
                for file in files:
                    if file.lower().endswith(".lnk"):
                        name = os.path.splitext(file)[0].strip()
                        if name and name.lower() not in apps:
                            apps[name.lower()] = {
                                "name": name,
                                "type": "shortcut",
                                "path": os.path.join(root, file),
                                "launch_method": "shortcut"
                            }
        return apps
    
    @staticmethod
    def _scan_registry_app_paths() -> Dict[str, Dict[str, Any]]:
        """Scan Windows Registry for installed applications."""
        apps = {}
        registry_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        ]
        
        for hive, path in registry_paths:
            try:
                with winreg.OpenKey(hive, path) as key:
                    for i in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            name = os.path.splitext(subkey_name)[0].strip()
                            if name and name.lower() not in apps:
                                with winreg.OpenKey(key, subkey_name) as sk:
                                    try:
                                        exe_path, _ = winreg.QueryValueEx(sk, "")
                                        if os.path.exists(exe_path):
                                            apps[name.lower()] = {
                                                "name": name,
                                                "type": "registry",
                                                "path": exe_path,
                                                "launch_method": "exe"
                                            }
                                    except:
                                        pass
                        except:
                            continue
            except:
                pass
        return apps
    
    @staticmethod
    def _scan_uwp_apps() -> Dict[str, Dict[str, Any]]:
        """Scan for UWP/Store apps using PowerShell."""
        apps = {}
        try:
            # Get UWP apps via PowerShell
            cmd = [
                "powershell", "-NoProfile", "-Command",
                "Get-StartApps | ConvertTo-Json"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0 and result.stdout:
                import json
                try:
                    start_apps = json.loads(result.stdout)
                    if isinstance(start_apps, list):
                        for app in start_apps:
                            name = app.get('Name', '')
                            app_id = app.get('AppID', '')
                            if name and name.lower() not in apps:
                                apps[name.lower()] = {
                                    "name": name,
                                    "type": "uwp",
                                    "appid": app_id,
                                    "launch_method": "uwp"
                                }
                except:
                    pass
        except:
            pass
        return apps
    
    @staticmethod
    def _scan_common_locations() -> Dict[str, Dict[str, Any]]:
        """Scan common installation directories."""
        apps = {}
        common_paths = [
            r"C:\Program Files",
            r"C:\Program Files (x86)",
            r"C:\Users\*\AppData\Local\Programs",
            r"C:\Users\*\AppData\Local",
        ]
        
        exe_patterns = ["*.exe"]
        
        for base_pattern in common_paths:
            for path in glob.glob(base_pattern):
                if not os.path.isdir(path):
                    continue
                
                for exe_pattern in exe_patterns:
                    for exe_path in glob.glob(os.path.join(path, "**", exe_pattern), recursive=True):
                        try:
                            name = os.path.splitext(os.path.basename(exe_path))[0]
                            # Filter out common non-app executables
                            skip_patterns = ["uninstall", "installer", "setup", "update", "crash", "report"]
                            if any(skip in name.lower() for skip in skip_patterns):
                                continue
                            if len(name) < 3:
                                continue
                            
                            if name.lower() not in apps:
                                apps[name.lower()] = {
                                    "name": name,
                                    "type": "exe",
                                    "path": exe_path,
                                    "launch_method": "exe"
                                }
                        except:
                            continue
        return apps


class SmartAppLauncher:
    """Intelligent app launcher that can open ANY application."""
    
    def __init__(self):
        self.app_cache = None
        self._refresh_cache()
    
    def _refresh_cache(self):
        """Refresh the app discovery cache."""
        logger.info("Refreshing app discovery cache...")
        self.app_cache = AppDiscovery.discover_all_apps()
        logger.info(f"Discovered {len(self.app_cache)} applications")
    
    def find_app(self, app_name: str) -> Optional[Dict[str, Any]]:
        """Find an application by name (fuzzy matching)."""
        if not self.app_cache:
            self._refresh_cache()
        
        target = app_name.lower().strip()
        
        # Exact match
        if target in self.app_cache:
            return self.app_cache[target]
        
        # Remove common words and try again
        clean_name = target.replace("microsoft", "").replace("apple", "").strip()
        if clean_name and clean_name in self.app_cache:
            return self.app_cache[clean_name]
        
        # Fuzzy matching
        best_match = None
        best_score = 0
        
        for cached_name, app_info in self.app_cache.items():
            score = 0
            
            # Exact word match
            if target == cached_name:
                score = 100
            # Contains match
            elif target in cached_name:
                score = 70 + (len(target) / len(cached_name)) * 30
            # Cached name contains target
            elif cached_name in target:
                score = 60 + (len(cached_name) / len(target)) * 30
            # Word boundary matching
            elif any(word in cached_name for word in target.split()):
                score = 50
            
            if score > best_score:
                best_score = score
                best_match = app_info
        
        if best_score >= 60:
            logger.info(f"Found match for '{app_name}': {best_match['name']} (score: {best_score:.0f})")
            return best_match
        
        return None
    
    def launch_app(self, app_name: str) -> LaunchResult:
        """Launch any application by name."""
        
        # First, try to find the app
        app_info = self.find_app(app_name)
        
        if not app_info:
            # Try common aliases
            aliases = {
                "apple music": ["Apple Music", "Music"],
                "microsoft store": ["Microsoft Store", "Store", "Windows Store"],
                "vs code": ["Visual Studio Code", "Code"],
                "word": ["Microsoft Word", "WinWord"],
                "excel": ["Microsoft Excel", "Excel"],
                "powerpoint": ["Microsoft PowerPoint", "PowerPoint"],
                "outlook": ["Microsoft Outlook", "Outlook"],
            }
            
            for key, alias_list in aliases.items():
                if app_name.lower() in key or key in app_name.lower():
                    for alias in alias_list:
                        app_info = self.find_app(alias)
                        if app_info:
                            break
                if app_info:
                    break
        
        if not app_info:
            return LaunchResult(
                status=LaunchStatus.LAUNCH_FAILED,
                message=f"Could not find '{app_name}' on your system, sir."
            )
        
        # Launch using appropriate method
        launch_method = app_info.get("launch_method", "exe")
        
        try:
            if launch_method == "uwp":
                # UWP app
                app_id = app_info.get("appid")
                if app_id:
                    subprocess.Popen(f'explorer.exe shell:AppsFolder\\{app_id}', shell=True)
                    logger.info(f"Launched UWP app: {app_info['name']}")
                else:
                    return LaunchResult(
                        status=LaunchStatus.LAUNCH_FAILED,
                        message=f"Could not launch {app_info['name']}, sir."
                    )
            
            elif launch_method == "shortcut":
                # LNK shortcut
                shortcut_path = app_info.get("path")
                os.startfile(shortcut_path)
                logger.info(f"Launched shortcut: {shortcut_path}")
            
            else:
                # Direct executable
                exe_path = app_info.get("path")
                if exe_path and os.path.exists(exe_path):
                    subprocess.Popen([exe_path], shell=False)
                    logger.info(f"Launched EXE: {exe_path}")
                else:
                    return LaunchResult(
                        status=LaunchStatus.LAUNCH_FAILED,
                        message=f"Could not find executable for {app_info['name']}, sir."
                    )
            
            # Wait for app to start
            time.sleep(2.0)
            
            # Try to find the window
            window_info = self._wait_for_window(app_info['name'], timeout=15.0)
            
            if window_info:
                return LaunchResult(
                    status=LaunchStatus.SUCCESS,
                    message=f"Opening {app_info['name']}, sir.",
                    window_title=window_info.get('title'),
                    hwnd=window_info.get('hwnd')
                )
            else:
                # App launched but window not found yet
                return LaunchResult(
                    status=LaunchStatus.SUCCESS,
                    message=f"Opening {app_info['name']}, sir.",
                )
                
        except Exception as e:
            logger.error(f"Launch failed: {e}")
            return LaunchResult(
                status=LaunchStatus.LAUNCH_FAILED,
                message=f"Failed to launch {app_name}, sir. {str(e)}"
            )
    
    def _wait_for_window(self, app_name: str, timeout: float) -> Optional[Dict[str, Any]]:
        """Wait for app window to appear."""
        from ui_core import WindowManager, _get_process_name
        
        wm = WindowManager()
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # Look for windows with app name in title
            for window in wm.find_windows():
                if window.title and app_name.lower() in window.title.lower():
                    return {
                        'hwnd': window.hwnd,
                        'title': window.title,
                        'class': window.class_name
                    }
            time.sleep(0.5)
        
        return None


# Global instance
smart_launcher = SmartAppLauncher()


# Legacy compatibility
class AppLauncher:
    @staticmethod
    def launch_and_verify(app_name: str, wait_for_ui: bool = True) -> LaunchResult:
        """Legacy compatibility method."""
        return smart_launcher.launch_app(app_name)


app_launcher = AppLauncher()