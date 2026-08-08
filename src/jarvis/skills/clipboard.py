"""Clipboard skill implementation."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from jarvis.skills.interfaces import SkillInterface

logger = logging.getLogger("jarvis.skills.clipboard")


class ClipboardSkill(SkillInterface):
    """Skill for clipboard operations."""

    @property
    def name(self) -> str:
        return "clipboard"

    @property
    def description(self) -> str:
        return "Clipboard operations including getting, setting, and clearing clipboard content"

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute clipboard operations.

        Supported operations:
        - get: Get clipboard content
        - set: Set clipboard content
        - clear: Clear clipboard
        - format_available: Check if a format is available

        Args:
            action: Operation to perform
            **kwargs: Operation-specific arguments

        Returns:
            Dictionary with execution results
        """
        start_time = time.time()
        action = kwargs.get("action", "").lower()

        try:
            if action == "get":
                result = self._get_clipboard(**kwargs)
            elif action == "set":
                result = self._set_clipboard(**kwargs)
            elif action == "clear":
                result = self._clear_clipboard(**kwargs)
            elif action == "format_available":
                result = self._is_format_available(**kwargs)
            else:
                result = {
                    "success": False,
                    "reason": f"Unknown action: {action}",
                    "logs": [
                        f"Available actions: get, set, clear, format_available"
                    ],
                    "data": None
                }

            # Add execution time to result
            result["execution_time"] = time.time() - start_time
            return result

        except Exception as e:
            logger.error("ClipboardSkill execution failed: %s", e, exc_info=True)
            return {
                "success": False,
                "reason": f"ClipboardSkill execution failed: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None,
                "execution_time": time.time() - start_time
            }

    def _get_clipboard(self, **kwargs) -> Dict[str, Any]:
        """Get clipboard content."""
        format_name = kwargs.get("format", "text")
        try:
            # Try to use win32clipboard if available
            try:
                import win32clipboard
                import win32con

                win32clipboard.OpenClipboard()
                try:
                    if format_name == "text":
                        format_id = win32con.CF_TEXT
                    elif format_name == "unicode":
                        format_id = win32con.CF_UNICODETEXT
                    else:
                        # Try to get format ID by name
                        try:
                            format_id = win32clipboard.RegisterClipboardFormat(format_name)
                        except:
                            format_id = win32con.CF_TEXT  # fallback to text

                    if win32clipboard.IsClipboardFormatAvailable(format_id):
                        data = win32clipboard.GetClipboardData(format_id)
                        if isinstance(data, bytes):
                            # Try to decode as UTF-8, fallback to latin-1
                            try:
                                data = data.decode('utf-8')
                            except UnicodeDecodeError:
                                data = data.decode('latin-1')
                        return {
                            "success": True,
                            "reason": f"Clipboard content retrieved ({format_name})",
                            "logs": [f"Retrieved clipboard content: {len(str(data))} characters"],
                            "data": {
                                "content": data,
                                "format": format_name,
                                "size": len(str(data))
                            }
                        }
                    else:
                        return {
                            "success": False,
                            "reason": f"Clipboard format not available: {format_name}",
                            "logs": [f"Format {format_name} not available in clipboard"],
                            "data": None
                        }
                finally:
                    win32clipboard.CloseClipboard()
            except ImportError:
                # Fallback to PowerShell
                import subprocess
                ps_script = 'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Clipboard]::GetText()'
                result = subprocess.run(
                    ["powershell", "-Command", ps_script],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    content = result.stdout.strip()
                    return {
                        "success": True,
                        "reason": "Clipboard content retrieved via PowerShell",
                        "logs": [f"Retrieved clipboard content: {len(content)} characters"],
                        "data": {
                            "content": content,
                            "format": "text",
                            "size": len(content)
                        }
                    }
                else:
                    return {
                        "success": False,
                        "reason": f"Failed to get clipboard via PowerShell: {result.stderr}",
                        "logs": [f"PowerShell error: {result.stderr}"],
                        "data": None
                    }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to get clipboard: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _set_clipboard(self, **kwargs) -> Dict[str, Any]:
        """Set clipboard content."""
        content = kwargs.get("content")
        format_name = kwargs.get("format", "text")

        if content is None:
            return {
                "success": False,
                "reason": "content parameter required",
                "logs": ["Please provide content parameter"],
                "data": None
            }

        try:
            # Try to use win32clipboard if available
            try:
                import win32clipboard
                import win32con

                win32clipboard.OpenClipboard()
                try:
                    win32clipboard.EmptyClipboard()
                    if format_name == "text":
                        format_id = win32con.CF_UNICODETEXT  # Use Unicode for better compatibility
                        win32clipboard.SetClipboardData(format_id, content)
                    else:
                        # Try to get format ID by name
                        try:
                            format_id = win32clipboard.RegisterClipboardFormat(format_name)
                            win32clipboard.SetClipboardData(format_id, content)
                        except:
                            # Fallback to text
                            format_id = win32con.CF_UNICODETEXT
                            win32clipboard.SetClipboardData(format_id, content)
                    return {
                        "success": True,
                        "reason": f"Clipboard content set ({format_name})",
                        "logs": [f"Set clipboard content: {len(str(content))} characters"],
                        "data": {
                            "content": str(content),
                            "format": format_name,
                            "size": len(str(content))
                        }
                    }
                finally:
                    win32clipboard.CloseClipboard()
            except ImportError:
                # Fallback to PowerShell
                import subprocess
                # Escape single quotes in content for PowerShell
                escaped_content = str(content).replace("'", "''")
                ps_script = f'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Clipboard]::SetText(\'{escaped_content}\')'
                result = subprocess.run(
                    ["powershell", "-Command", ps_script],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return {
                        "success": True,
                        "reason": "Clipboard content set via PowerShell",
                        "logs": [f"Set clipboard content: {len(str(content))} characters"],
                        "data": {
                            "content": str(content),
                            "format": format_name,
                            "size": len(str(content))
                        }
                    }
                else:
                    return {
                        "success": False,
                        "reason": f"Failed to set clipboard via PowerShell: {result.stderr}",
                        "logs": [f"PowerShell error: {result.stderr}"],
                        "data": None
                    }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to set clipboard: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _clear_clipboard(self, **kwargs) -> Dict[str, Any]:
        """Clear clipboard content."""
        try:
            # Try to use win32clipboard if available
            try:
                import win32clipboard

                win32clipboard.OpenClipboard()
                try:
                    win32clipboard.EmptyClipboard()
                    return {
                        "success": True,
                        "reason": "Clipboard cleared",
                        "logs": ["Clipboard content cleared"],
                        "data": {"cleared": True}
                    }
                finally:
                    win32clipboard.CloseClipboard()
            except ImportError:
                # Fallback to PowerShell
                import subprocess
                ps_script = 'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Clipboard]::Clear()'
                result = subprocess.run(
                    ["powershell", "-Command", ps_script],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return {
                        "success": True,
                        "reason": "Clipboard cleared via PowerShell",
                        "logs": ["Clipboard content cleared"],
                        "data": {"cleared": True}
                    }
                else:
                    return {
                        "success": False,
                        "reason": f"Failed to clear clipboard via PowerShell: {result.stderr}",
                        "logs": [f"PowerShell error: {result.stderr}"],
                        "data": None
                    }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to clear clipboard: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _is_format_available(self, **kwargs) -> Dict[str, Any]:
        """Check if a clipboard format is available."""
        format_name = kwargs.get("format", "text")
        try:
            # Try to use win32clipboard if available
            try:
                import win32clipboard
                import win32con

                win32clipboard.OpenClipboard()
                try:
                    if format_name == "text":
                        format_id = win32con.CF_TEXT
                    elif format_name == "unicode":
                        format_id = win32con.CF_UNICODETEXT
                    else:
                        # Try to get format ID by name
                        try:
                            format_id = win32clipboard.RegisterClipboardFormat(format_name)
                        except:
                            format_id = win32con.CF_TEXT  # fallback to text

                    available = win32clipboard.IsClipboardFormatAvailable(format_id)
                    return {
                        "success": True,
                        "reason": f"Clipboard format {'available' if available else 'not available'}: {format_name}",
                        "logs": [f"Format {format_name} {'available' if available else 'not available'}"],
                        "data": {
                            "format": format_name,
                            "available": available
                        }
                    }
                finally:
                    win32clipboard.CloseClipboard()
            except ImportError:
                # Fallback - assume text format is usually available
                # This is a simplification but works for basic use cases
                if format_name.lower() in ["text", "unicode", "utf8", "utf-8"]:
                    return {
                        "success": True,
                        "reason": f"Clipboard format assumed available: {format_name}",
                        "logs": [f"Format {format_name} assumed available (PowerShell fallback)"],
                        "data": {
                            "format": format_name,
                            "available": True
                        }
                    }
                else:
                    return {
                        "success": False,
                        "reason": f"Cannot check format availability without win32clipboard: {format_name}",
                        "logs": [f"Format check requires win32clipboard module"],
                        "data": {
                            "format": format_name,
                            "available": False
                        }
                    }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to check clipboard format: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"format": format_name, "available": False}
            }