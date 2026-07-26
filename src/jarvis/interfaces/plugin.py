"""Plugin system interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional


class PluginHost(ABC):
    """Provides lifecycle and service access to plugins."""

    @abstractmethod
    def discover(self) -> List[str]:
        """Discover available plugin modules."""

    @abstractmethod
    def load_plugin(self, name: str) -> bool:
        """Load a plugin by name."""

    @abstractmethod
    def unload_plugin(self, name: str) -> bool:
        """Unload a plugin."""

    @abstractmethod
    def reload_plugin(self, name: str) -> bool:
        """Hot-reload a plugin."""

    @abstractmethod
    def get_plugin(self, name: str) -> Optional[Any]:
        """Get a loaded plugin instance by name."""

    @abstractmethod
    def get_all_tools(self) -> Dict[str, Callable]:
        """Get all tool handlers registered by plugins."""


class Plugin(ABC):
    """Base class that all plugins must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin display name."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Plugin version string."""

    @abstractmethod
    def on_load(self, host: PluginHost) -> None:
        """Called when the plugin is loaded."""

    @abstractmethod
    def on_unload(self) -> None:
        """Called when the plugin is unloaded."""

    @abstractmethod
    def on_pause(self) -> None:
        """Called when the system pauses this plugin."""

    @abstractmethod
    def on_resume(self) -> None:
        """Called when the system resumes this plugin."""
