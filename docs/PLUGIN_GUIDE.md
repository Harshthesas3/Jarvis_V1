# Plugin Guide

## Overview

JARVIS's plugin system allows extending functionality without modifying core code. Plugins are Python modules that can register tools, event handlers, voice commands, and message interceptors.

## Architecture

```
PluginManager
  ├── Discovers plugins in plugins/ directory
  ├── Loads each plugin dynamically
  ├── Injects dependencies (speak, memory, settings, logger, apps, chat)
  ├── Registers tools/commands/handlers
  ├── Supports hot-reload
  └── Persists disabled state to disabled_plugins.json
```

## Getting Started

### Creating a Plugin

Create a Python file in `plugins/` directory. Each plugin must:

1. Import `Plugin` and `PluginMetadata` from `plugins`
2. Create a class that inherits from `Plugin`
3. Set `self.metadata` in `__init__`
4. Export `PluginClass` pointing to your class

### Minimal Plugin

```python
# plugins/hello_world.py
from plugins import Plugin, PluginMetadata

class HelloWorldPlugin(Plugin):
    def __init__(self, context):
        super().__init__(context)
        self.metadata = PluginMetadata(
            name="HelloWorld",
            version="1.0.0",
            description="A hello world plugin",
            author="You",
            plugin_type="tool",
        )

PluginClass = HelloWorldPlugin
```

## Plugin Types

### Tool Plugins

Tools are callable by the planner. They receive a plan dict and return a TTS string.

```python
class MyToolPlugin(Plugin):
    def __init__(self, context):
        super().__init__(context)
        self.metadata = PluginMetadata(
            name="MyTools",
            version="1.0.0",
            description="My tool plugin",
            plugin_type="tool",
        )

    def register_tools(self):
        return {
            "my_tool_name": self.handle_my_tool,
        }

    def handle_my_tool(self, plan: dict) -> str:
        param = plan.get("param", "")
        return f"Tool executed with {param}, sir."
```

The tool name (`my_tool_name`) is automatically registered with the planner. The LLM planner will discover it and can route requests to it.

### Handler Plugins

Handlers respond to system events.

```python
class MyHandlerPlugin(Plugin):
    def register_handlers(self):
        return {
            "periodic_check": self.on_periodic_check,
        }

    def on_periodic_check(self, event_data: dict) -> None:
        print(f"Periodic check: {event_data}")
```

### Command Plugins

Commands are triggered by exact phrase matching, bypassing the planner entirely.

```python
class MyCommandPlugin(Plugin):
    def register_commands(self):
        return {
            "hello world": self.cmd_hello,
        }

    def cmd_hello(self, args: str) -> str:
        return "Hello world, sir!"
```

### Hook Plugins

Hooks intercept every user message. Return a string to override the normal response, or `None` to let processing continue.

```python
class MyHookPlugin(Plugin):
    def on_message(self, text: str) -> str | None:
        if "secret" in text:
            return "Access granted, sir."
        return None
```

## Plugin Metadata Reference

```python
self.metadata = PluginMetadata(
    name="PluginName",              # Display name
    version="1.0.0",                # Semantic version
    description="What it does",     # Short description
    author="Author Name",           # Your name
    permissions=["network"],        # Required capabilities
    dependencies=["OtherPlugin"],   # Plugin dependencies
    enabled=True,                   # Loaded by default
    plugin_type="tool",             # tool, handler, command, hook
    min_jarvis_version="2.0.0",    # Minimum JARVIS version
)
```

### Permission Types

| Permission | Description |
|------------|-------------|
| `network` | Internet access |
| `filesystem` | File read/write |
| `system` | System commands/processes |
| `audio` | Microphone/speaker access |
| `ui` | GUI automation |
| `clipboard` | Clipboard read/write |

## Dependency Injection

Plugins receive a `context` dictionary on initialization:

| Key | Type | Description |
|-----|------|-------------|
| `speak` | `callable(str) -> None` | Text-to-speech function |
| `memory` | `JARVISMemory` | Memory module (load/save) |
| `settings` | `SettingsManager` | Config manager |
| `logger` | `logging.Logger` | Configured logger |
| `apps` | `list[dict]` | Installed applications |
| `chat` | `callable(str) -> str` | LLM chat function |

Access in handlers:

```python
def my_handler(self, plan):
    speak = self.context.get("speak")
    memory = self.context.get("memory")
    settings = self.context.get("settings")
    logger = self.context.get("logger")
    logger.info("Handler called")
    speak("Processing request, sir.")
```

## Plugin Lifecycle

### Loading

1. `PluginManager.discover()` scans `plugins/*.py`
2. `load_plugin()` imports the module dynamically
3. Finds `PluginClass` (subclass of `Plugin`)
4. Checks version compatibility and dependencies
5. Calls `plugin.on_load()` — return `False` to reject
6. Registers tools, handlers, and commands
7. Plugin is now active

### Unloading

1. `unload_plugin()` calls `plugin.on_unload()`
2. Removes all registered tools/handlers/commands
3. Removes plugin from internal registry

### Hot Reload

Allows updating plugins without restarting JARVIS:

```python
# Reload a single plugin
pm.hot_reload("my_plugin")

# Reload all plugins
pm.hot_reload_all()
```

**Note**: Hot reload unloads then reloads the module. State is preserved in the context but lost in plugin instance variables.

## Managing Plugins

### Enabling/Disabling

```python
pm = PluginManager(context)

# Disable (persisted to disabled_plugins.json)
pm.disable_plugin("my_plugin")

# Enable
pm.enable_plugin("my_plugin")
```

### Listing

```python
plugins = pm.list_plugins()
for p in plugins:
    print(f"{p['name']}: loaded={p['loaded']}, enabled={p['enabled']}")
```

### Voice Commands for Plugin Management

- "Enable plugin [name]"
- "Disable plugin [name]"
- "List plugins"
- "Reload plugins"

## Best Practices

1. **Return strings from tool handlers** — all tool handlers must return a TTS-friendly string
2. **Handle errors gracefully** — return error messages instead of raising exceptions
3. **Declare permissions** — always declare what capabilities your plugin needs
4. **Keep state minimal** — use context services (memory, settings) for persistence
5. **Test independently** — plugins should work in isolation
6. **Use semantic versioning** — version your plugins for compatibility tracking
7. **Lazy import heavy libraries** — import inside handler functions to keep plugin loading fast
8. **Use the injected logger** — `self.context.get("logger")` for consistent logging

## Example: Weather Plugin

```python
from plugins import Plugin, PluginMetadata

class WeatherPlugin(Plugin):
    def __init__(self, context):
        super().__init__(context)
        self.metadata = PluginMetadata(
            name="Weather",
            version="1.0.0",
            description="Weather information",
            permissions=["network"],
            plugin_type="tool",
        )

    def register_tools(self):
        return {
            "get_weather": self.get_weather,
        }

    def get_weather(self, plan: dict) -> str:
        city = plan.get("city", "your location")
        # Call a weather API here
        return f"The weather in {city} is 22°C and sunny, sir."

PluginClass = WeatherPlugin
```

## Example: System Monitor Plugin

```python
from plugins import Plugin, PluginMetadata

class SystemMonitorPlugin(Plugin):
    def __init__(self, context):
        super().__init__(context)
        self.metadata = PluginMetadata(
            name="SystemMonitor",
            version="1.0.0",
            description="Monitors system resources",
            permissions=["system"],
            plugin_type="handler",
        )

    def register_tools(self):
        return {"check_system": self.check_system}

    def on_message(self, text: str) -> str | None:
        if "system status" in text.lower():
            return self.check_system({})
        return None

    def check_system(self, plan: dict) -> str:
        import psutil
        cpu = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        return f"CPU: {cpu}%, Memory: {memory.percent}%, sir."

PluginClass = SystemMonitorPlugin
```

## Security Considerations

- Plugins run with full process permissions
- Only install plugins from trusted sources
- Review requested permissions before enabling
- The permissions system is informational; enforcement is planned
- Plugins can access the file system, network, and system commands through injected services
