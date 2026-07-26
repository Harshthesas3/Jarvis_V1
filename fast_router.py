"""
fast_router.py
--------------
Intercepts transcribed text before it hits the LLM planner.
Handles simple, deterministic commands via regex/exact-match so Jarvis
responds in <200ms for everyday tasks like opening apps, volume control,
time/date, screenshots, and system actions.

Returns a TTS-ready string if a fast route was taken, otherwise None
to signal the planner should handle it.
"""

import re
import time
import logging
from typing import Optional

logger = logging.getLogger("jarvis.fast_router")


class FastCommandRouter:
    """Routes simple deterministic commands without hitting the LLM."""

    def __init__(self, context: dict):
        self.context = context
        self.speak = context.get("speak", print)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def route(self, text: str) -> Optional[str]:
        """Returns a TTS-ready result string if a fast route was taken, else None."""
        clean = text.lower().strip()
        clean = re.sub(r"[^\w\s]", "", clean)

        # 1. Time & Date
        if re.search(r"\b(whats the time|what is the time|current time|tell me the time|what time is it)\b", clean):
            return self._get_time()
        if re.search(r"\b(whats today|what is today|whats the date|what is the date|current date|todays date)\b", clean):
            return self._get_date()
        if re.search(r"\bwhat day is it\b", clean):
            return self._get_day()

        # 2. App launching
        app_match = re.match(r"^(open|launch|start)\s+(.+)$", clean)
        if app_match:
            app_name = app_match.group(2).strip()
            return self._launch_app(app_name)

        # 3. Volume control
        if re.search(r"\b(volume up|increase volume|louder|turn it up)\b", clean):
            return self._volume_up()
        if re.search(r"\b(volume down|decrease volume|quieter|turn it down)\b", clean):
            return self._volume_down()
        if re.search(r"\b(mute|mute volume|mute the sound|silence)\b", clean):
            return self._mute()
        vol_pct = re.search(r"\bset volume to (\d{1,3})\s*(?:percent)?\b", clean)
        if vol_pct:
            return self._set_volume(int(vol_pct.group(1)))

        # 4. Screenshot
        if re.search(r"\b(take a screenshot|take screenshot|screenshot|capture screen)\b", clean):
            return self._screenshot()

        # 5. Calculator
        if re.search(r"^(calculator|open calculator|launch calculator)$", clean):
            return self._launch_app("calculator")

        # 6. Sleep / lock
        if re.search(r"\block(?: the)? (?:pc|computer|screen)\b", clean):
            return self._lock_pc()
        if re.search(r"\bput(?: the)? (?:pc|computer) to sleep\b", clean):
            return self._sleep_pc()
        if re.search(r"^sleep(?: the)? (?:pc|computer)$", clean):
            return self._sleep_pc()

        # 7. Clipboard
        if re.search(r"\bclear(?: the)? clipboard\b", clean):
            return self._clear_clipboard()

        # 8. Show desktop
        if re.search(r"\b(show(?: the)? desktop|minimize all(?: windows)?)\b", clean):
            return self._show_desktop()

        return None

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _get_time(self) -> str:
        now = time.localtime()
        hour = now.tm_hour
        minute = now.tm_min
        ampm = "AM" if hour < 12 else "PM"
        hour12 = hour % 12 or 12
        return f"The time is {hour12}:{minute:02d} {ampm}, sir."

    def _get_date(self) -> str:
        import datetime
        today = datetime.date.today()
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        month_names = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]
        return (
            f"Today is {day_names[today.weekday()]}, "
            f"{month_names[today.month - 1]} {today.day}, {today.year}, sir."
        )

    def _get_day(self) -> str:
        import datetime
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return f"Today is {day_names[datetime.date.today().weekday()]}, sir."

    def _launch_app(self, app_name: str) -> str:
        try:
            from app_launcher import get_smart_launcher
            result = get_smart_launcher().launch_app(app_name)
            return result.message
        except Exception as e:
            logger.error("Fast router launch failed for '%s': %s", app_name, e)
            return f"I couldn't launch {app_name}, sir."

    def _volume_up(self) -> str:
        try:
            import pyautogui
            for _ in range(5):
                pyautogui.press("volumeup")
            return "Volume increased, sir."
        except Exception as e:
            logger.error("Volume up failed: %s", e)
            return "I couldn't adjust the volume, sir."

    def _volume_down(self) -> str:
        try:
            import pyautogui
            for _ in range(5):
                pyautogui.press("volumedown")
            return "Volume decreased, sir."
        except Exception as e:
            logger.error("Volume down failed: %s", e)
            return "I couldn't adjust the volume, sir."

    def _mute(self) -> str:
        try:
            import pyautogui
            pyautogui.press("volumemute")
            return "Audio muted, sir."
        except Exception as e:
            logger.error("Mute failed: %s", e)
            return "I couldn't mute the audio, sir."

    def _set_volume(self, pct: int) -> str:
        pct = max(0, min(100, pct))
        try:
            import subprocess
            # Use nircmd if on PATH, otherwise PowerShell audio COM
            import shutil
            if shutil.which("nircmd"):
                subprocess.run(["nircmd", "setsysvolume", str(int(pct / 100 * 65535))],
                               capture_output=True, timeout=5)
            else:
                # Key-press method: reset to 0 then press up N times
                import pyautogui
                for _ in range(50):
                    pyautogui.press("volumedown")
                for _ in range(pct // 2):
                    pyautogui.press("volumeup")
            return f"Volume set to {pct} percent, sir."
        except Exception as e:
            logger.error("Set volume failed: %s", e)
            return f"I couldn't set the volume to {pct} percent, sir."

    def _screenshot(self) -> str:
        try:
            import os
            import pyautogui
            settings = self.context.get("settings")
            screenshot_dir = settings.get("paths.screenshot_dir", "Screenshots") if settings else "Screenshots"
            os.makedirs(screenshot_dir, exist_ok=True)
            path = os.path.join(screenshot_dir, f"screenshot_{int(time.time())}.png")
            pyautogui.screenshot(path)
            return "Screenshot saved, sir."
        except Exception as e:
            logger.error("Screenshot failed: %s", e)
            return "Failed to take the screenshot, sir."

    def _lock_pc(self) -> str:
        try:
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            return "Locking the PC, sir."
        except Exception as e:
            logger.error("Lock PC failed: %s", e)
            return "I couldn't lock the PC, sir."

    def _sleep_pc(self) -> str:
        try:
            import subprocess
            subprocess.Popen(
                [
                    "powershell", "-NoProfile", "-Command",
                    "Add-Type -Assembly System.Windows.Forms; "
                    "[System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)",
                ],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return "Putting the PC to sleep, sir."
        except Exception as e:
            logger.error("Sleep PC failed: %s", e)
            return "I couldn't put the PC to sleep, sir."

    def _clear_clipboard(self) -> str:
        try:
            import subprocess
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $null"],
                capture_output=True, timeout=5,
            )
            return "Clipboard cleared, sir."
        except Exception as e:
            logger.error("Clear clipboard failed: %s", e)
            return "I couldn't clear the clipboard, sir."

    def _show_desktop(self) -> str:
        try:
            import pyautogui
            pyautogui.hotkey("win", "d")
            return "Showing the desktop, sir."
        except Exception as e:
            logger.error("Show desktop failed: %s", e)
            return "I couldn't show the desktop, sir."

