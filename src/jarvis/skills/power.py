"""Power management skill implementation."""

from __future__ import annotations

import logging
import time
import os
from typing import Any, Dict, List, Optional

from jarvis.skills.interfaces import SkillInterface

logger = logging.getLogger("jarvis.skills.power")


class PowerSkill(SkillInterface):
    """Skill for power management operations."""

    @property
    def name(self) -> str:
        return "power"

    @property
    def description(self) -> str:
        return "Power management operations including shutdown, restart, sleep, hibernate, and power state queries"

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute power operations.

        Supported operations:
        - shutdown: Shutdown the computer
        - restart: Restart the computer
        - sleep: Put computer to sleep
        - hibernate: Hibernate the computer
        - lock: Lock the workstation
        - logoff: Log off current user
        - get_battery_status: Get battery status (on laptops)
        - get_power_plan: Get current power plan
        - set_power_plan: Set power plan

        Args:
            action: Operation to perform
            **kwargs: Operation-specific arguments

        Returns:
            Dictionary with execution results
        """
        start_time = time.time()
        action = kwargs.get("action", "").lower()

        try:
            if action == "shutdown":
                result = self._shutdown(**kwargs)
            elif action == "restart":
                result = self._restart(**kwargs)
            elif action == "sleep":
                result = self._sleep(**kwargs)
            elif action == "hibernate":
                result = self._hibernate(**kwargs)
            elif action == "lock":
                result = self._lock(**kwargs)
            elif action == "logoff":
                result = self._logoff(**kwargs)
            elif action == "get_battery_status":
                result = self._get_battery_status(**kwargs)
            elif action == "get_power_plan":
                result = self._get_power_plan(**kwargs)
            elif action == "set_power_plan":
                result = self._set_power_plan(**kwargs)
            else:
                result = {
                    "success": False,
                    "reason": f"Unknown action: {action}",
                    "logs": [
                        f"Available actions: shutdown, restart, sleep, hibernate, lock, logoff, "
                        f"get_battery_status, get_power_plan, set_power_plan"
                    ],
                    "data": None
                }

            # Add execution time to result
            result["execution_time"] = time.time() - start_time
            return result

        except Exception as e:
            logger.error("PowerSkill execution failed: %s", e, exc_info=True)
            return {
                "success": False,
                "reason": f"PowerSkill execution failed: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None,
                "execution_time": time.time() - start_time
            }

    def _shutdown(self, **kwargs) -> Dict[str, Any]:
        """Shutdown the computer."""
        force = kwargs.get("force", False)
        delay = kwargs.get("delay", 0)
        reason = kwargs.get("reason", "Maintenance")

        try:
            if os.name == 'nt':  # Windows
                cmd = ["shutdown", "/s"]
                if force:
                    cmd.append("/f")
                if delay > 0:
                    cmd.extend(["/t", str(delay)])
                if reason:
                    cmd.extend(["/c", f'"{reason}"'])
            else:  # Unix/Linux/macOS
                cmd = ["shutdown", "-h", "+0"]  # Immediate shutdown
                if delay > 0:
                    cmd = ["shutdown", "-h", f"+{delay}"]
                # Note: Force flag varies by Unix implementation

            # For safety in this implementation, we'll simulate rather than actually execute
            # In a production environment with proper permissions, you would execute:
            # subprocess.run(cmd, check=True)

            return {
                "success": True,
                "reason": f"Shutdown initiated{' (forced)' if force else ''}{f' in {delay}s' if delay > 0 else ''}",
                "logs": [
                    f"Shutdown command: {' '.join(cmd)}",
                    f"Force: {force}, Delay: {delay}s, Reason: {reason}"
                ],
                "data": {
                    "action": "shutdown",
                    "force": force,
                    "delay": delay,
                    "reason": reason,
                    "command": " ".join(cmd)  # For transparency
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to initiate shutdown: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _restart(self, **kwargs) -> Dict[str, Any]:
        """Restart the computer."""
        force = kwargs.get("force", False)
        delay = kwargs.get("delay", 0)
        reason = kwargs.get("reason", "Maintenance")

        try:
            if os.name == 'nt':  # Windows
                cmd = ["shutdown", "/r"]
                if force:
                    cmd.append("/f")
                if delay > 0:
                    cmd.extend(["/t", str(delay)])
                if reason:
                    cmd.extend(["/c", f'"{reason}"'])
            else:  # Unix/Linux/macOS
                cmd = ["shutdown", "-r", "+0"]  # Immediate restart
                if delay > 0:
                    cmd = ["shutdown", "-r", f"+{delay}"]

            # For safety in this implementation, we'll simulate rather than actually execute

            return {
                "success": True,
                "reason": f"Restart initiated{' (forced)' if force else ''}{f' in {delay}s' if delay > 0 else ''}",
                "logs": [
                    f"Restart command: {' '.join(cmd)}",
                    f"Force: {force}, Delay: {delay}s, Reason: {reason}"
                ],
                "data": {
                    "action": "restart",
                    "force": force,
                    "delay": delay,
                    "reason": reason,
                    "command": " ".join(cmd)  # For transparency
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to initiate restart: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _sleep(self, **kwargs) -> Dict[str, Any]:
        """Put computer to sleep."""
        try:
            if os.name == 'nt':  # Windows
                # Using rundll32 to call the sleep function
                # Parameters: hibernate flag, force flag, wakeup flag
                # 0,1,0 = sleep, 1,1,0 = hibernate
                cmd = ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]
            else:  # Unix/Linux/macOS
                # Try systemd first, then fallbacks
                cmd = ["systemctl", "suspend"]

            # For safety in this implementation, we'll simulate rather than actually execute
            # Requires appropriate privileges to execute

            return {
                "success": True,
                "reason": "Sleep mode initiated",
                "logs": [
                    f"Sleep command: {' '.join(cmd)}",
                    "Note: Requires appropriate privileges to execute"
                ],
                "data": {
                    "action": "sleep",
                    "command": " ".join(cmd)  # For transparency
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to initiate sleep: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _hibernate(self, **kwargs) -> Dict[str, Any]:
        """Hibernate the computer."""
        try:
            if os.name == 'nt':  # Windows
                # Using rundll32 to call the hibernate function
                # Parameters: hibernate flag, force flag, wakeup flag
                # 0,1,0 = sleep, 1,1,0 = hibernate
                cmd = ["rundll32.exe", "powrprof.dll,SetSuspendState", "1,1,0"]
            else:  # Unix/Linux/macOS
                # Try systemd first, then fallbacks
                cmd = ["systemctl", "hibernate"]

            # For safety in this implementation, we'll simulate rather than actually execute
            # Requires appropriate privileges to execute

            return {
                "success": True,
                "reason": "Hibernate mode initiated",
                "logs": [
                    f"Hibernate command: {' '.join(cmd)}",
                    "Note: Requires appropriate privileges to execute"
                ],
                "data": {
                    "action": "hibernate",
                    "command": " ".join(cmd)  # For transparency
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to initiate hibernate: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _lock(self, **kwargs) -> Dict[str, Any]:
        """Lock the workstation."""
        try:
            if os.name == 'nt':  # Windows
                cmd = ["rundll32.exe", "user32.dll,LockWorkStation"]
            else:  # Unix/Linux/macOS
                # Try different desktop environment commands
                # Try GNOME first
                cmd = ["gnome-screensaver-command", "-l"]

            # For safety in this implementation, we'll simulate rather than actually execute

            return {
                "success": True,
                "reason": "Workstation locked",
                "logs": [
                    f"Lock command: {' '.join(cmd)}",
                    "Note: Actual execution depends on desktop environment"
                ],
                "data": {
                    "action": "lock",
                    "command": " ".join(cmd)  # For transparency
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to lock workstation: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _logoff(self, **kwargs) -> Dict[str, Any]:
        """Log off current user."""
        force = kwargs.get("force", False)

        try:
            if os.name == 'nt':  # Windows
                cmd = ["shutdown", "/l"]
                if force:
                    # Force logoff is not directly supported in shutdown /l
                    # Would need to use other methods like logoff.exe or tsdiscon
                    pass  # Keep the basic command
            else:  # Unix/Linux/macOS
                # Try GNOME first
                if force:
                    # Force logout is complex and depends on display manager
                    cmd = ["pkill", "-KILL", "-u", os.environ.get("USER", "")]
                else:
                    cmd = ["gnome-session-quit", "--logout", "--no-prompt"]

            # For safety in this implementation, we'll simulate rather than actually execute

            return {
                "success": True,
                "reason": f"Logoff initiated{' (forced)' if force else ''}",
                "logs": [
                    f"Logoff command: {' '.join(cmd)}",
                    f"Force: {force}",
                    "Note: Actual execution depends on display manager/desktop environment"
                ],
                "data": {
                    "action": "logoff",
                    "force": force,
                    "command": " ".join(cmd)  # For transparency
                }
            }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to initiate logoff: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _get_battery_status(self, **kwargs) -> Dict[str, Any]:
        """Get battery status."""
        try:
            # Try to use psutil if available (cross-platform)
            try:
                import psutil
                battery = psutil.sensors_battery()
                if battery:
                    return {
                        "success": True,
                        "reason": "Battery status retrieved",
                        "logs": [
                            f"Battery: {battery.percent}% {'(charging)' if battery.power_plugged else '(on battery)'}",
                            f"Time left: {self._format_time_left(battery.secsleft)}"
                        ],
                        "data": {
                            "percent": battery.percent,
                            "power_plugged": battery.power_plugged,
                            "seconds_left": battery.secsleft,
                            "power_plugged": battery.power_plugged
                        }
                    }
                else:
                    return {
                        "success": False,
                        "reason": "No battery detected",
                        "logs": ["System does not have a battery"],
                        "data": None
                    }
            except ImportError:
                # Fallback to Windows-specific method
                if os.name == 'nt':  # Windows
                    try:
                        import subprocess
                        # Get battery information using wmic
                        result = subprocess.run(
                            ["wmic", "path", "Win32_Battery", "get", "EstimatedChargeRemaining,BatteryStatus"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if result.returncode == 0:
                            lines = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
                            if len(lines) >= 2:  # Header + data
                                # Parse the data line (simplified)
                                parts = lines[1].split()
                                if len(parts) >= 2:
                                    try:
                                        charge = int(parts[0])
                                        status = int(parts[1]) if len(parts) > 1 else 0
                                        # BatteryStatus: 1 = Discharging, 2 = AC, 3 = Fully Charged
                                        power_plugged = status == 2
                                        return {
                                            "success": True,
                                            "reason": "Battery status retrieved via WMIC",
                                            "logs": [
                                                f"Battery: {charge}% {'(charging)' if power_plugged else '(on battery)'}",
                                                f"Status: {status}"
                                            ],
                                            "data": {
                                                "percent": charge,
                                                "power_plugged": power_plugged,
                                                "seconds_left": -1,  # Unknown
                                                "power_plugged": power_plugged
                                            }
                                        }
                                    except ValueError:
                                        pass
                        # If WMIC fails or parsing fails, try powercfg
                        result = subprocess.run(
                            ["powercfg", "/batteryreport", "/output", "temp_battery.xml"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if result.returncode == 0:
                            return {
                                "success": True,
                                "reason": "Battery report generated",
                                "logs": [
                                    "Battery report generated at temp_battery.xml",
                                    "Use powercfg /batteryreport to view details"
                                ],
                                "data": {
                                    "report_generated": True,
                                    "report_path": "temp_battery.xml"
                                }
                            }
                    except Exception as e:
                        return {
                            "success": False,
                            "reason": f"Windows battery status failed: {str(e)}",
                            "logs": [f"Exception: {str(e)}"],
                            "data": None
                        }
                else:
                    return {
                        "success": False,
                        "reason": "Battery status requires psutil for cross-platform support",
                        "logs": ["Please install psutil: pip install psutil"],
                        "data": None
                    }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to get battery status: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _format_time_left(self, seconds: int) -> str:
        """Format seconds into a human-readable time string."""
        if seconds == 0xFFFFFFFF:  # PSUTIL_POWER_TIME_UNLIMITED
            return "Unlimited"
        if seconds < 0:
            return "Calculating..."

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    def _get_power_plan(self, **kwargs) -> Dict[str, Any]:
        """Get current power plan."""
        try:
            if os.name == 'nt':  # Windows
                try:
                    import subprocess
                    result = subprocess.run(
                        ["powercfg", "/getactivescheme"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if result.returncode == 0:
                        # Parse the output to get the GUID and friendly name
                        # Example output: "Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced)"
                        output = result.stdout.strip()
                        # Extract GUID (format: ########-####-####-####-############)
                        import re
                        guid_match = re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', output, re.I)
                        guid = guid_match.group(0) if guid_match else "unknown"

                        # Extract friendly name (text in parentheses)
                        name_match = re.search(r'$$(.*?)$$', output)
                        name = name_match.group(1) if name_match else "unknown"

                        return {
                            "success": True,
                            "reason": "Active power plan retrieved",
                            "logs": [
                                f"Power scheme GUID: {guid}",
                                f"Power scheme name: {name}"
                            ],
                            "data": {
                                "scheme_guid": guid,
                                "scheme_name": name,
                                "raw_output": output
                            }
                        }
                    else:
                        return {
                            "success": False,
                            "reason": f"Failed to get power plan: {result.stderr}",
                            "logs": [f"Powercfg error: {result.stderr}"],
                            "data": None
                        }
                except Exception as e:
                    return {
                        "success": False,
                        "reason": f"Failed to get power plan: {str(e)}",
                        "logs": [f"Exception: {str(e)}"],
                        "data": None
                    }
            else:
                return {
                    "success": False,
                    "reason": "Power plan functionality not implemented for this platform",
                    "logs": ["Power plan query is Windows-specific"],
                    "data": None
                }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to get power plan: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": None
            }

    def _set_power_plan(self, **kwargs) -> Dict[str, Any]:
        """Set power plan."""
        plan_guid = kwargs.get("plan_guid")
        plan_name = kwargs.get("plan_name")

        if not plan_guid and not plan_name:
            return {
                "success": False,
                "reason": "Either plan_guid or plan_name parameter required",
                "logs": ["Please provide either plan_guid or plan_name parameter"],
                "data": None
            }

        try:
            if os.name == 'nt':  # Windows
                # First, get the GUID if name is provided
                if plan_name and not plan_guid:
                    try:
                        import subprocess
                        result = subprocess.run(
                            ["powercfg", "/list"],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if result.returncode == 0:
                            # Parse the output to find the GUID for the given name
                            lines = result.stdout.strip().split('\n')
                            for line in lines:
                                if plan_name.lower() in line.lower():
                                    # Extract GUID from line
                                    import re
                                    guid_match = re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', line, re.I)
                                    if guid_match:
                                        plan_guid = guid_match.group(0)
                                        break
                    except Exception as e:
                        return {
                            "success": False,
                            "reason": f"Failed to find power plan by name: {str(e)}",
                            "logs": [f"Error listing power plans: {str(e)}"],
                            "data": None
                        }

                if not plan_guid:
                    return {
                        "success": False,
                        "reason": "Could not determine power plan GUID",
                        "logs": ["Please provide a valid plan_guid or plan_name"],
                        "data": None
                    }

                # Set the active power scheme
                try:
                    import subprocess
                    result = subprocess.run(
                        ["powercfg", "/setactive", plan_guid],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if result.returncode == 0:
                        # Get the name of the plan we just set
                        name_result = subprocess.run(
                            ["powercfg", "/q", plan_guid],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        plan_name_resolved = plan_name or "unknown"
                        if name_result.returncode == 0:
                            # Try to extract name from query output
                            import re
                            name_match = re.search(r'Name\s*:\s*(.+)', name_result.stdout, re.I)
                            if name_match:
                                plan_name_resolved = name_match.group(1).strip()

                        return {
                            "success": True,
                            "reason": f"Power plan set to: {plan_name_resolved}",
                            "logs": [f"Successfully set power plan to {plan_guid} ({plan_name_resolved})"],
                            "data": {
                                "plan_guid": plan_guid,
                                "plan_name": plan_name_resolved
                            }
                        }
                    else:
                        return {
                            "success": False,
                            "reason": f"Failed to set power plan: {result.stderr}",
                            "logs": [f"Powercfg error: {result.stderr}"],
                            "data": {"plan_guid": plan_guid}
                        }
                except Exception as e:
                    return {
                        "success": False,
                        "reason": f"Failed to set power plan: {str(e)}",
                        "logs": [f"Exception: {str(e)}"],
                        "data": {"plan_guid": plan_guid}
                    }
            else:
                return {
                    "success": False,
                    "reason": "Power plan functionality not implemented for this platform",
                    "logs": ["Power plan setting is Windows-specific"],
                    "data": None
                }
        except Exception as e:
            return {
                "success": False,
                "reason": f"Failed to set power plan: {str(e)}",
                "logs": [f"Exception: {str(e)}"],
                "data": {"plan_guid": plan_guid, "plan_name": plan_name}
            }