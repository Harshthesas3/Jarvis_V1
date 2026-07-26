"""
JARVIS Plugin Architecture

A simple, extensible plugin system for adding capabilities to JARVIS.
Plugins are Python modules that can register tools, handlers, and commands.
"""

from __future__ import annotations
import sys
import importlib.util
import json
import logging
from typing import Dict, List, Any, Callable, Optional
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger("jarvis.plugins")

# Known safe permissions that plugins may request
KNOWN_PERMISSIONS = frozenset({
    "network",       # HTTP/network access
    "system",        # System monitoring (CPU, memory, disk)
    "filesystem",    # Read/write files
    "ui",            # UI automation
    "audio",         # Microphone/speaker
    "clipboard",     # Clipboard access
    "notifications", # Desktop notifications
    "storage",       # Persistent key-value storage
})


@dataclass
class PluginMetadata:
    """Metadata for a plugin."""
    name: str
    version: str
    description: str
    author: str = ""
    permissions: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    enabled: bool = True
    plugin_type: str = "tool"  # tool, handler, command, hook
    min_jarvis_version: str = "2.0.0"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PluginMetadata':
        return cls(**data)


class Plugin:
    """Base class for all JARVIS plugins."""
    
    def __init__(self, context: Dict[str, Any]):
        """
        Initialize the plugin with dependency injection.
        
        Args:
            context: Dictionary of injected dependencies (speak, memory, settings, etc.)
        """
        self.context = context
        self.metadata = PluginMetadata(
            name=self.__class__.__name__,
            version="1.0.0",
            description="Base plugin class"
        )
    
    def on_load(self) -> bool:
        """Called when plugin is loaded. Return False to prevent loading."""
        return True
    
    def on_unload(self) -> None:
        """Called when plugin is unloaded."""
        pass
    
    def register_tools(self) -> Dict[str, Callable[[dict], str]]:
        """
        Register tools that can be called by the planner.
        
        Returns:
            Dictionary mapping tool names to handler functions.
            Handler signature: handler(plan: dict) -> str
        """
        return {}
    
    def register_handlers(self) -> Dict[str, Callable]:
        """
        Register event handlers.
        
        Returns:
            Dictionary mapping event names to handler functions.
        """
        return {}
    
    def register_commands(self) -> Dict[str, Callable[[str], str]]:
        """
        Register direct voice commands.
        
        Returns:
            Dictionary mapping command triggers to handler functions.
            Handler signature: handler(args: str) -> str
        """
        return {}
    
    def on_message(self, text: str) -> Optional[str]:
        """
        Intercept or react to user messages.
        
        Args:
            text: The user's input text
            
        Returns:
            A string to override the response, or None to let it pass through.
        """
        return None


class PluginManager:
    """
    Manages plugin discovery, loading, and lifecycle.
    """
    
    def __init__(self, context: Dict[str, Any], plugin_dir: str = "plugins"):
        self.context = context
        self.plugin_dir = Path(plugin_dir)
        self.plugins: Dict[str, Plugin] = {}
        self.plugin_modules: Dict[str, Any] = {}
        self.tool_registry: Dict[str, Callable] = {}
        self.handler_registry: Dict[str, Callable] = {}
        self.command_registry: Dict[str, Callable] = {}
        self.metadata_cache: Dict[str, PluginMetadata] = {}
        self.disabled_state_file = Path("disabled_plugins.json")
        self.disabled_plugins: set = set()
        self._load_disabled_state()
    
    def _load_disabled_state(self) -> None:
        """Load disabled plugin list from disk."""
        if self.disabled_state_file.exists():
            try:
                with open(self.disabled_state_file, 'r') as f:
                    data = json.load(f)
                    self.disabled_plugins = set(data.get("disabled", []))
            except Exception as e:
                logger.warning(f"Failed to load disabled plugin state: {e}")
                self.disabled_plugins = set()
    
    def _save_disabled_state(self) -> None:
        """Save disabled plugin list to disk."""
        try:
            with open(self.disabled_state_file, 'w') as f:
                json.dump({"disabled": list(self.disabled_plugins)}, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save disabled plugin state: {e}")
    
    def discover(self) -> List[str]:
        """Discover available plugins in the plugin directory."""
        if not self.plugin_dir.exists():
            self.plugin_dir.mkdir(parents=True)
            return []
        
        plugins = []
        for file in self.plugin_dir.glob("*.py"):
            if file.name.startswith("_"):
                continue
            module_name = file.stem
            plugins.append(module_name)
        
        return plugins
    
    def load_plugin(self, module_name: str) -> bool:
        """Load a specific plugin by module name."""
        if module_name in self.plugins:
            logger.warning(f"Plugin {module_name} already loaded")
            return True
        
        # Check if disabled
        if self.disabled_plugins and module_name in self.disabled_plugins:
            logger.info(f"Plugin {module_name} is disabled, skipping")
            return False
        
        try:
            file_path = self.plugin_dir / f"{module_name}.py"
            if not file_path.exists():
                logger.error(f"Plugin file not found: {file_path}")
                return False
            
            # Load the module
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                logger.error(f"Could not load spec for {module_name}")
                return False
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            
            # Find the plugin class
            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, Plugin) and 
                    attr is not Plugin):
                    plugin_class = attr
                    break
            
            if plugin_class is None:
                logger.error(f"No Plugin subclass found in {module_name}")
                return False
            
            # Check version compatibility
            temp_instance = plugin_class(self.context)
            if not self._check_version(temp_instance.metadata):
                logger.error(f"Plugin {module_name} version incompatible")
                return False
            
            # Check dependencies
            if not self._check_dependencies(temp_instance.metadata):
                logger.error(f"Plugin {module_name} dependencies not met")
                return False

            # Validate permissions
            for perm in temp_instance.metadata.permissions:
                if perm not in KNOWN_PERMISSIONS:
                    logger.warning(
                        f"Plugin {module_name} requests unknown permission '{perm}'. "
                        f"Known permissions: {', '.join(sorted(KNOWN_PERMISSIONS))}"
                    )

            # Create the actual instance
            plugin_instance = plugin_class(self.context)
            
            # Call on_load
            if not plugin_instance.on_load():
                logger.warning(f"Plugin {module_name} on_load returned False, skipping")
                return False
            
            # Register tools, handlers, commands
            tools = plugin_instance.register_tools()
            for name, handler in tools.items():
                if name in self.tool_registry:
                    logger.warning(f"Tool {name} already registered, overwriting")
                self.tool_registry[name] = handler
            
            handlers = plugin_instance.register_handlers()
            for name, handler in handlers.items():
                self.handler_registry[name] = handler
            
            commands = plugin_instance.register_commands()
            for name, handler in commands.items():
                self.command_registry[name] = handler
            
            # Store plugin
            self.plugins[module_name] = plugin_instance
            self.plugin_modules[module_name] = module
            self.metadata_cache[module_name] = plugin_instance.metadata
            
            logger.info(f"Plugin loaded: {module_name} (v{plugin_instance.metadata.version})")
            return True
            
        except Exception as e:
            logger.exception(f"Failed to load plugin {module_name}: {e}")
            return False
    
    JARVIS_VERSION = "2.0.0"

    def _check_version(self, metadata: PluginMetadata) -> bool:
        """Check if plugin is compatible with current JARVIS version."""
        if metadata.min_jarvis_version:
            try:
                required = tuple(int(x) for x in metadata.min_jarvis_version.split("."))
                current = tuple(int(x) for x in self.JARVIS_VERSION.split("."))
                # Pad shorter tuples with zeros
                while len(required) < len(current):
                    required += (0,)
                while len(current) < len(required):
                    current += (0,)
                if required > current:
                    logger.warning(
                        f"Plugin requires JARVIS v{metadata.min_jarvis_version}, "
                        f"current is v{self.JARVIS_VERSION}"
                    )
                    return False
            except (ValueError, TypeError):
                logger.warning("Could not parse plugin version requirement: %s", metadata.min_jarvis_version)
        return True
    
    def _check_dependencies(self, metadata: PluginMetadata) -> bool:
        """Check if plugin dependencies are satisfied."""
        for dep in metadata.dependencies:
            if dep not in self.plugins:
                return False
        return True
    
    def unload_plugin(self, module_name: str) -> bool:
        """Unload a plugin."""
        if module_name not in self.plugins:
            return False
        
        plugin = self.plugins[module_name]
        
        try:
            plugin.on_unload()
        except Exception as e:
            logger.warning(f"Error during plugin unload: {e}")
        
        # Remove from registries
        for name, handler in list(self.tool_registry.items()):
            if handler in plugin.register_tools().values():
                del self.tool_registry[name]
        
        for name, handler in list(self.handler_registry.items()):
            if handler in plugin.register_handlers().values():
                del self.handler_registry[name]
        
        for name, handler in list(self.command_registry.items()):
            if handler in plugin.register_commands().values():
                del self.command_registry[name]
        
        del self.plugins[module_name]
        if module_name in self.plugin_modules:
            del self.plugin_modules[module_name]
        if module_name in self.metadata_cache:
            del self.metadata_cache[module_name]
        
        logger.info(f"Plugin unloaded: {module_name}")
        return True
    
    def load_all(self) -> int:
        """Load all discovered plugins."""
        discovered = self.discover()
        loaded = 0
        for module_name in discovered:
            if self.load_plugin(module_name):
                loaded += 1
        return loaded
    
    def hot_reload(self, module_name: str) -> bool:
        """Hot reload a specific plugin."""
        logger.info(f"Hot reloading plugin: {module_name}")
        
        # Unload first
        self.unload_plugin(module_name)
        
        # Remove from sys.modules to force fresh import
        if module_name in sys.modules:
            del sys.modules[module_name]
        
        # Reload from scratch
        return self.load_plugin(module_name)
    
    def hot_reload_all(self) -> int:
        """Hot reload all loaded plugins."""
        logger.info("Hot reloading all plugins...")
        reloaded = 0
        for module_name in list(self.plugins.keys()):
            if self.hot_reload(module_name):
                reloaded += 1
        return reloaded
    
    def enable_plugin(self, module_name: str) -> bool:
        """Enable a plugin (remove from disabled list)."""
        self.disabled_plugins.discard(module_name)
        self._save_disabled_state()
        
        # Try to load it
        if module_name not in self.plugins:
            return self.load_plugin(module_name)
        return True
    
    def disable_plugin(self, module_name: str) -> bool:
        """Disable a plugin (add to disabled list)."""
        self.disabled_plugins.add(module_name)
        self._save_disabled_state()
        
        # Unload it
        return self.unload_plugin(module_name)
    
    def is_enabled(self, module_name: str) -> bool:
        """Check if a plugin is enabled (not in disabled list)."""
        return module_name not in self.disabled_plugins
    
    def get_plugin(self, module_name: str) -> Optional[Plugin]:
        """Get a plugin instance."""
        return self.plugins.get(module_name)
    
    def list_plugins(self) -> List[Dict[str, Any]]:
        """List all plugins with their metadata."""
        discovered = self.discover()
        result = []
        for module_name in discovered:
            meta = self.metadata_cache.get(module_name)
            result.append({
                "name": module_name,
                "loaded": module_name in self.plugins,
                "enabled": self.is_enabled(module_name),
                "metadata": meta.to_dict() if meta else None
            })
        return result
    
    def get_all_tools(self) -> Dict[str, Callable]:
        """Get all registered tools from all plugins. (Backward compat)"""
        return dict(self.tool_registry)
    
    def get_all_handlers(self) -> Dict[str, Callable]:
        """Get all registered handlers from all plugins."""
        return dict(self.handler_registry)
    
    def get_all_commands(self) -> Dict[str, Callable]:
        """Get all registered commands from all plugins."""
        return dict(self.command_registry)
    
    def discover_and_load(self) -> int:
        """Discover and load all plugins. (Backward compat)"""
        return self.load_all()
    
    def get_tool(self, name: str) -> Optional[Callable]:
        """Get a registered tool by name."""
        return self.tool_registry.get(name)
    
    def get_handler(self, name: str) -> Optional[Callable]:
        """Get a registered handler by name."""
        return self.handler_registry.get(name)
    
    def get_command(self, name: str) -> Optional[Callable]:
        """Get a registered command by name."""
        return self.command_registry.get(name)
    
    def call_tool(self, name: str, plan: dict) -> Optional[str]:
        """Call a tool by name with a plan."""
        tool = self.get_tool(name)
        if tool:
            try:
                return tool(plan)
            except Exception as e:
                logger.exception(f"Error calling tool {name}: {e}")
                return f"Error executing {name}: {e}"
        return None
    
    def call_handler(self, name: str, *args, **kwargs) -> Any:
        """Call a handler by name."""
        handler = self.get_handler(name)
        if handler:
            try:
                return handler(*args, **kwargs)
            except Exception as e:
                logger.exception(f"Error calling handler {name}: {e}")
                return None
        return None
    
    def call_command(self, name: str, args: str) -> Optional[str]:
        """Call a command by name."""
        command = self.get_command(name)
        if command:
            try:
                return command(args)
            except Exception as e:
                logger.exception(f"Error calling command {name}: {e}")
                return f"Error executing command {name}: {e}"
        return None


# Global plugin manager instance
_plugin_manager: Optional[PluginManager] = None


def init_plugin_manager(context: Dict[str, Any], plugin_dir: str = "plugins") -> PluginManager:
    """Initialize the global plugin manager."""
    global _plugin_manager
    _plugin_manager = PluginManager(context, plugin_dir)
    return _plugin_manager


def get_plugin_manager() -> Optional[PluginManager]:
    """Get the global plugin manager instance."""
    return _plugin_manager


def shutdown_plugins() -> None:
    """Shutdown all plugins."""
    global _plugin_manager
    if _plugin_manager:
        for module_name in list(_plugin_manager.plugins.keys()):
            _plugin_manager.unload_plugin(module_name)
        _plugin_manager = None