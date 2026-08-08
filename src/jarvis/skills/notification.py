"""Notification skill implementation."""

from __future__ import annotations

import logging
import time
import os
from typing import Any, Dict, List, Optional

from jarvis.skills.interfaces import SkillInterface

logger = logging.getLogger("jarvis.skills.notification")


class NotificationSkill(SkillInterface):
    """Skill for showing system notifications."""

    @property
    def name(self) -> str:
        return "notification"

    @property
    def description(self) -> str:
        return "System notifications including toast notifications, desktop alerts, and audio cues"

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute notification operations.

        Supported operations:
        - show: Show a notification
        - show_toast: Show a Windows toast notification
        - play_sound: Play a system sound
        - show_alert: Show a simple alert/message box

        Args:
            action: Operation to perform
            **kwargs: Operation-specific arguments

        Returns:
            Dictionary with execution results
        """
        start_time = time.time()
        action = kwargs.get("action", "").lower()

        try:
            if action == "show":
                result = self._show_notification(**kwargs)
            elif action == "show_toast":
                result = self._show_toast(**kwargs)
            elif action == "play_sound":
                result = self._play_sound(**kwargs)
            elif action == "show_alert":
                result = self._show_alert(**kwargs)
            else:
                result = {
                    "success": False,
                    "reason": f"Unknown action: {action}",
                    "logs": [
                        f"Available actions: show, show_toast, play_sound, show_alert"
                    ],
                    "data": None
                }

            # Add execution time to result
            result["execution_time"] = time.time() - start_time
            return result

        except Exception as e:
            logger.error("NotificationSkill execution failed: %s", e, exc_info=True)
            return {
                "success": False,
                "reason": f"NotificationSkill execution failed: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None,
                "execution_time": time.time() - start_time
            }

    def _show_notification(self, **kwargs) -> Dict[str, Any]:
        """Show a notification (general purpose)."""
        title = kwargs.get("title", "Notification")
        message = kwargs.get("message", "")
        duration = kwargs.get("duration", "short")  # short or long
        sound = kwargs.get("sound", False)

        if not message:
            return {
                "success": False,
                "reason": "message parameter required",
                "logs": ["Please provide message parameter"],
                "data": None
            }

        try:
            # Try multiple methods in order of preference
            result = None

            # Method 1: Try win10toast (Windows 10+ toast notifications)
            try:
                result = self._show_toast_win10toast(title, message, duration)
                if result.get("success"):
                    return result
            except ImportError:
                pass
            except Exception as e:
                logger.debug(f"win10toast failed: {e}")

            # Method 2: Try PowerShell BurntToast
            try:
                result = self._show_toast_powershell(title, message, duration)
                if result.get("success"):
                    return result
            except Exception as e:
                logger.debug(f"PowerShell toast failed: {e}")

            # Method 3: Fallback to simple console output
            result = self._show_console_notification(title, message)
            if sound:
                # Try to play a sound
                self._play_system_sound()

            return result
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to show notification: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _show_toast(self, **kwargs) -> Dict[str, Any]:
        """Show a Windows toast notification."""
        title = kwargs.get("title", "Notification")
        message = kwargs.get("message", "")
        duration = kwargs.get("duration", "short")

        if not message:
            return {
                "success": False,
                "reason": "message parameter required",
                "logs": ["Please provide message parameter"],
                "data": None
            }

        # Try win10toast first
        try:
            return self._show_toast_win10toast(title, message, duration)
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"win10toast failed: {e}")

        # Fallback to PowerShell
        try:
            return self._show_toast_powershell(title, message, duration)
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to show toast: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _show_toast_win10toast(self, title: str, message: str, duration: str) -> Dict[str, Any]:
        """Show toast using win10toast library."""
        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()

            # Duration mapping
            duration_map = {"short": 5, "long": 10}
            duration_seconds = duration_map.get(duration.lower(), 5)

            toaster.show_toast(
                title,
                message,
                duration=duration_seconds,
                threaded=True
            )

            return {
                "success": True,
                "reason": f"Toast notification shown: {title}",
                "logs": [
                    f"Displayed toast notification",
                    f"Title: {title}",
                    f"Message: {message[:50]}{'...' if len(message) > 50 else ''}"
                ],
                "data": {
                    "title": title,
                    "message": message,
                    "duration": duration
                }
            }
        except ImportError:
            raise  # Re-raise to try next method
        except Exception as e:
            raise  # Re-raise to try next method

    def _show_toast_powershell(self, title: str, message: str, duration: str) -> Dict[str, Any]:
        """Show toast using PowerShell."""
        try:
            import subprocess

            # Escape quotes for PowerShell
            escaped_title = title.replace('"', '`"')
            escaped_message = message.replace('"', '`"')

            # PowerShell script for toast notification
            ps_script = f"""
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
            $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
            $toastXml = [xml]$template.GetXml()
            $toastXml.GetElementsByTagName('text')[0].AppendChild($toastXml.CreateTextNode('{escaped_title}')) | Out-Null
            $toastXml.GetElementsByTagName('text')[1].AppendChild($toastXml.CreateTextNode('{escaped_message}')) | Out-Null
            $toast = [Windows.UI.Notifications.ToastNotification]::new($toastXml)
            $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('JARVIS')
            $notifier.Show($toast)
            Start-Sleep -Seconds 5
            """

            result = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "reason": f"Toast notification shown via PowerShell: {title}",
                    "logs": [
                        "Displayed toast notification via PowerShell",
                        f"Title: {title}",
                        f"Message: {message[:50]}{'...' if len(message) > 50 else ''}"
                    ],
                    "data": {
                        "title": title,
                        "message": message,
                        "duration": duration
                    }
                }
            else:
                return {
                    "success": False,
                    "reason": f"PowerShell toast failed: {result.stderr}",
                    "logs": [f"PowerShell error: {result.stderr}"],
                    "data": None
                }
        except Exception as e:
            raise  # Re-raise to try next method

    def _show_console_notification(self, title: str, message: str) -> Dict[str, Any]:
        """Show notification via console output."""
        return {
            "success": True,
            "reason": f"Notification shown via console: {title}",
            "logs": [
                f"=== {title} ===",
                message,
                "=" * (len(title) + 4)
            ],
            "data": {
                "title": title,
                "message": message,
                "method": "console"
            }
        }

    def _play_sound(self, **kwargs) -> Dict[str, Any]:
        """Play a system sound."""
        sound_name = kwargs.get("sound_name", "default")
        try:
            # Try to play sound using various methods
            played = False

            # Method 1: Use winsound (Windows)
            try:
                import winsound
                if sound_name == "default":
                    winsound.MessageBeep(winsound.MB_OK)
                elif sound_name == "asterisk":
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                elif sound_name == "exclamation":
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                elif sound_name == "hand":
                    winsound.MessageBeep(winsound.MB_ICONHAND)
                elif sound_name == "question":
                    winsound.MessageBeep(winsound.MB_ICONQUESTION)
                else:
                    winsound.MessageBeep(winsound.MB_OK)
                played = True
            except ImportError:
                pass

            # Method 2: Use PowerShell to play sound
            if not played:
                try:
                    import subprocess
                    # Map sound names to Windows system sounds
                    sound_map = {
                        "default": "*",
                        "asterisk": "Asterisk",
                        "exclamation": "Exclamation",
                        "hand": "Hand",
                        "question": "Question"
                    }
                    ps_sound = sound_map.get(sound_name, "*")
                    ps_script = f'[System.Media.SystemSounds]::{ps_sound}.Play()'

                    result = subprocess.run(
                        ["powershell", "-Command", ps_script],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        played = True
                except Exception:
                    pass

            if played:
                return {
                    "success": True,
                    "reason": f"Sound played: {sound_name}",
                    "logs": [f"Played system sound: {sound_name}"],
                    "data": {
                        "sound_name": sound_name,
                        "played": True
                    }
                }
            else:
                return {
                    "success": False,
                    "reason": f"Could not play sound: {sound_name}",
                    "logs": [f"No sound playback method available for: {sound_name}"],
                    "data": {
                        "sound_name": sound_name,
                        "played": False
                    }
                }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to play sound: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"sound_name": sound_name}
            }

    def _show_alert(self, **kwargs) -> Dict[str, Any]:
        """Show a simple alert/message box."""
        title = kwargs.get("title", "Alert")
        message = kwargs.get("message", "")
        button_type = kwargs.get("button_type", "OK")  # OK, OKCancel, YesNo, etc.

        if not message:
            return {
                "success": False,
                "reason": "message parameter required",
                "logs": ["Please provide message parameter"],
                "data": None
            }

        try:
            # Try to show a message box using various methods
            shown = False

            # Method 1: Use ctypes for Windows MessageBox
            try:
                import ctypes
                # MessageBoxButton constants
                MB_OK = 0x00000000
                MB_OKCANCEL = 0x00000001
                MB_YESNO = 0x00000004
                MB_YESNOCANCEL = 0x00000003
                MB_RETRYCANCEL = 0x00000005

                # Map button types to constants
                button_map = {
                    "OK": MB_OK,
                    "OKCancel": MB_OKCANCEL,
                    "YesNo": MB_YESNO,
                    "YesNoCancel": MB_YESNOCANCEL,
                    "RetryCancel": MB_RETRYCANCEL
                }
                uType = button_map.get(button_type, MB_OK)

                # Show the message box
                result = ctypes.windll.user32.MessageBoxW(0, message, title, uType)
                shown = True

                # Map result back to button pressed
                result_map = {
                    1: "OK",
                    2: "Cancel",
                    3: "Abort",
                    4: "Retry",
                    5: "Ignore",
                    6: "Yes",
                    7: "No"
                }
                button_pressed = result_map.get(result, str(result))

                return {
                    "success": True,
                    "reason": f"Alert shown: {title}",
                    "logs": [
                        f"Displayed message box",
                        f"Title: {title}",
                        f"Message: {message[:50]}{'...' if len(message) > 50 else ''}",
                        f"Button clicked: {button_pressed}"
                    ],
                    "data": {
                        "title": title,
                        "message": message,
                        "button_type": button_type,
                        "button_pressed": button_pressed
                    }
                }
            except Exception as e:
                logger.debug(f"ctypes message box failed: {e}")

            # Method 2: Fallback to console
            if not shown:
                print(f"=== {title} ===")
                print(message)
                print("=" * (len(title) + 4))
                shown = True

                return {
                    "success": True,
                    "reason": f"Alert shown via console: {title}",
                    "logs": [
                        f"Displayed alert via console",
                        f"Title: {title}",
                        f"Message: {message[:50]}{'...' if len(message) > 50 else ''}"
                    ],
                    "data": {
                        "title": title,
                        "message": message,
                        "method": "console"
                    }
                }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to show alert: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _play_system_sound(self) -> None:
        """Play a default system sound."""
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_OK)
        except ImportError:
            try:
                import subprocess
                subprocess.run(
                    ["powershell", "-Command", "[System.Media.SystemSounds]::Asterisk.Play()"],
                    capture_output=True,
                    timeout=3
                )
            except Exception:
                pass  # Silently fail if we can't play sound