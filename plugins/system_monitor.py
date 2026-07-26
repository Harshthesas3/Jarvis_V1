"""
Sample Plugin: SystemMonitor

Demonstrates a plugin with handlers, commands, and message interception.
"""

from plugins import Plugin, PluginMetadata


class SystemMonitorPlugin(Plugin):
    """A plugin that monitors system resources and provides alerts."""
    
    def __init__(self, context):
        super().__init__(context)
        self.metadata = PluginMetadata(
            name="SystemMonitorPlugin",
            version="1.0.0",
            description="Monitors system resources and provides alerts",
            author="JARVIS Team",
            permissions=["system"],
            plugin_type="handler"
        )
        self._thresholds = {"cpu": 80, "memory": 85}
    
    def on_load(self) -> bool:
        return True
    
    def register_tools(self) -> dict:
        return {
            "check_system": self.check_system,
            "set_threshold": self.set_threshold,
        }
    
    def register_handlers(self) -> dict:
        return {
            "periodic_check": self.periodic_check,
        }
    
    def register_commands(self) -> dict:
        return {
            "system status": self.cmd_system_status,
            "system thresholds": self.cmd_thresholds,
        }
    
    def on_message(self, text: str) -> str | None:
        """Intercept messages about system status."""
        text_lower = text.lower()
        if any(phrase in text_lower for phrase in ["system status", "how is the system", "system health"]):
            return self.check_system({})
        return None
    
    def check_system(self, plan: dict) -> str:
        """Check current system status."""
        import psutil
        
        cpu = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        status = []
        if cpu > self._thresholds["cpu"]:
            status.append(f"CPU HIGH: {cpu}%")
        if memory.percent > self._thresholds["memory"]:
            status.append(f"MEMORY HIGH: {memory.percent}%")
        
        if status:
            return f"Warning, sir: {'; '.join(status)}"
        
        return f"System nominal, sir. CPU: {cpu}%, Memory: {memory.percent}%, Disk: {disk.percent}%"
    
    def set_threshold(self, plan: dict) -> str:
        """Set alert thresholds."""
        metric = plan.get("metric", "").lower()
        value = plan.get("value")
        
        if metric in self._thresholds and value is not None:
            self._thresholds[metric] = int(value)
            return f"Threshold for {metric} set to {value}%, sir."
        return "Invalid threshold specification, sir."
    
    def periodic_check(self) -> None:
        """Called periodically by the main loop."""
        result = self.check_system({})
        if "Warning" in result:
            speak = self.context.get("speak")
            if speak:
                speak(result)
    
    def cmd_system_status(self, args: str) -> str:
        """Command: system status"""
        return self.check_system({})
    
    def cmd_thresholds(self, args: str) -> str:
        """Command: system thresholds"""
        return f"Current thresholds: CPU {self._thresholds['cpu']}%, Memory {self._thresholds['memory']}%, sir."


PluginClass = SystemMonitorPlugin