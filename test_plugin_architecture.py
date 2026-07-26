"""
Plugin Architecture Integration Test
Tests discovery, loading, tool registration, hot reload, and shutdown.
"""

import logging
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from plugins import (
    PluginManager, Plugin, PluginMetadata,
    init_plugin_manager, get_plugin_manager, shutdown_plugins
)

print("Plugin imports: OK")

# Create a mock context
ctx = {
    "speak": lambda x: None,
    "memory": None,
    "settings": None,
    "logger": logging.getLogger("test"),
}

# Initialize plugin manager
pm = init_plugin_manager(ctx)
print("Plugin manager initialized: OK")

# Discover plugins
plugins = pm.discover()
print(f"Discovered plugins: {plugins}")

# Load all
loaded = pm.load_all()
print(f"Loaded: {loaded}")

# List
for p in pm.list_plugins():
    print(f"  - {p['name']}: loaded={p['loaded']}, enabled={p['enabled']}")

# Get tools
tools = pm.get_all_tools()
print(f"Available tools: {list(tools.keys())}")

# Test a tool
result = pm.call_tool("get_weather", {"city": "London"})
print(f"Weather tool result: {result}")

result = pm.call_tool("check_system", {})
print(f"System check tool result: {result}")

# Hot reload
pm.hot_reload("weather")
print("Weather hot reloaded: OK")

# Test enable/disable
pm.disable_plugin("system_monitor")
print("System monitor disabled: OK")
pm.enable_plugin("system_monitor")
print("System monitor enabled: OK")

# Test backward compat methods
all_tools = pm.get_all_tools()
print(f"get_all_tools() count: {len(all_tools)}")

loaded_count = pm.discover_and_load()
print(f"discover_and_load() returned: {loaded_count}")

# Shutdown
shutdown_plugins()
print("Plugin shutdown: OK")
print("ALL PLUGIN ARCHITECTURE TESTS PASSED")
