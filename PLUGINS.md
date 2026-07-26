# JARVIS Plugin Architecture

## Overview

JARVIS v2 includes a powerful plugin architecture that allows extending functionality without modifying core code. Plugins are Python modules that can register tools, event handlers, voice commands, and message interceptors.

## Key Features

- **Automatic Discovery**: Plugins in the `plugins/` directory are automatically detected
- **Metadata-Driven**: Plugins declare metadata (version, permissions, dependencies)
- **Enable/Disable**: Plugins can be toggled at runtime with persistent state
- **Dependency Injection**: Core services (speak, memory, settings, logger) injected at load time
- **Hot Reload**: Reload plugins without restarting JARVIS
- **Permissions System**: Capability-based permission model for security
- **Backward Compatible**: Existing handlers continue to work unchanged

## Quick Start

### 1. Create a Plugin

Create a new file in the `plugins/` directory:

```python
# plugins/my_plugin.py
from plugins import Plugin, PluginMetadata

class MyPlugin(Plugin):
    def __init__(self, context):
        super().__init__(context)
        self.metadata = PluginMetadata(
            name="MyPlugin",
            version="1.0.0",
            description="My custom plugin",
            author="Your Name",
            permissions=["network"],  # Required permissions
            plugin_type="tool"
        )
    
    def register_tools(self):
        return {
            "my_tool": self.handle_my_tool,
        }
    
    def handle_my_tool(self, plan: dict) -> str:
        return "Tool executed successfully, sir."

PluginClass = MyPlugin  # Required: export the plugin class
```

### 2. Restart JARVIS or Hot Reload

```bash
# Option 1: Restart JARVIS
python jarvis_v2.py

# Option 2: Hot reload (in another terminal or via voice command)
# Voice: "reload plugins"
```

## Plugin Types

### Tool Plugins
Register functions callable by the planner:

```python
def register_tools(self):
    return {
        "tool_name": self.handler_function,
    }

def handler_function(self, plan: dict) -> str:
    # plan contains parsed parameters from the user's request
    return "Response for TTS"
```

### Handler Plugins
Register event handlers:

```python
def register_handlers(self):
    return {
        "event_name": self.handler_function,
    }
```

### Command Plugins
Register direct voice commands (bypass planner):

```python
def register_commands(self):
    return {
        "trigger phrase": self.command_handler,
    }

def command_handler(self, args: str) -> str:
    return "Command executed, sir."
```

### Hook Plugins
Intercept user messages:

```python
def on_message(self, text: str) -> str | None:
    # Return a string to override the response
    # Return None to let normal processing continue
    if "secret phrase" in text:
        return "Access granted, sir."
    return None
```

## Dependency Injection

Plugins receive a `context` dictionary with core services:

| Key | Description |
|-----|-------------|
| `speak` | Text-to-speech function |
| `memory` | Persistent memory module |
| `settings` | Settings manager |
| `logger` | Configured logger instance |
| `apps` | Installed applications list |
| `chat` | LLM chat function |

Access in your plugin:
```python
def my_handler(self, plan):
    speak = self.context.get("speak")
    memory = self.context.get("memory")
    settings = self.context.get("settings")
    # ...
```

## Plugin Metadata

```python
self.metadata = PluginMetadata(
    name="PluginName",
    version="1.0.0",
    description="What this plugin does",
    author="Author Name",
    permissions=["network", "filesystem", "system"],
    dependencies=["OtherPlugin"],  # Other plugin names
    enabled=True,
    plugin_type="tool",  # tool, handler, command, hook
    min_jarvis_version="2.0.0"
)
```

### Permission Types
- `network` - Internet access
- `filesystem` - File read/write
- `system` - System commands/processes
- `audio` - Microphone/speaker access
- `ui` - GUI automation

## Managing Plugins

### Enable/Disable
```python
# In code
pm.enable_plugin("my_plugin")
pm.disable_plugin("my_plugin")

# Voice commands
# "Enable plugin my plugin"
# "Disable plugin my plugin"
```

### List Plugins
```python
plugins = pm.list_plugins()
for p in plugins:
    print(f"{p['name']}: {'Loaded' if p['loaded'] else 'Unloaded'}, Enabled: {p['enabled']}")
```

### Hot Reload
```python
# Single plugin
pm.hot_reload("my_plugin")

# All plugins
pm.hot_reload_all()
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    PluginManager                            │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │ Tool Reg.   │ │Handler Reg. │ │Command Reg. │           │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘           │
│         │               │               │                   │
│         ▼               ▼               ▼                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Loaded Plugins                          │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐    │   │
│  │  │ Weather │ │ System  │ │  Your   │ │  ...    │    │   │
│  │  │ Plugin  │ │ Monitor │ │ Plugin  │ │         │    │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘    │   │
│  └─────────────────────────────────────────────────────┘   │
│                            │                                 │
│                            ▼                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Dependency Injection                    │   │
│  │  {speak, memory, settings, logger, apps, chat}      │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Best Practices

1. **Always return strings** from tool handlers for TTS
2. **Handle errors gracefully** - return error messages, don't raise
3. **Use permissions** - declare what you need
4. **Keep state minimal** - use context services for persistence
5. **Test independently** - plugins should work in isolation
6. **Version your plugins** - use semantic versioning

## Security Considerations

- Plugins run with full process permissions
- Only install trusted plugins
- Review permissions before enabling
- The permissions field is informational - enforcement is planned

## Example Plugins

See the `plugins/` directory for examples:
- `weather.py` - Tool plugin with network permission
- `system_monitor.py` - Handler, command, and hook plugin with system permission

## Migration from v1

Existing handlers in `task_executor.py` continue to work. To migrate:

1. Move handler to a plugin file
2. Wrap in a Plugin class
3. Register via `register_tools()`
4. Remove from `task_executor.py` HANDLERS dict

The planner and executor will automatically discover and use plugin tools.