"""Thread-safe dependency injection container with lazy resolution and lifecycle management."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, Optional, Set, Type, TypeVar

logger = logging.getLogger("jarvis.di")

T = TypeVar("T")

Factory = Callable[["ServiceContainer"], Any]


class ServiceRegistration:
    """Registration record for a service in the container."""

    def __init__(
        self,
        interface: Type,
        factory: Factory,
        *,
        singleton: bool = True,
    ) -> None:
        self.interface = interface
        self.factory = factory
        self.singleton = singleton
        self._instance: Any = None
        self._resolved = False

    def resolve(self, container: "ServiceContainer") -> Any:
        if self.singleton and self._resolved:
            return self._instance
        instance = self.factory(container)
        if self.singleton:
            self._instance = instance
            self._resolved = True
        return instance


class ServiceContainer:
    """Thread-safe DI container for service registration and resolution.

    Supports singleton/transient services, lazy/eager init, factory functions,
    service aliasing, lifecycle hooks, and parent container fallback.
    """

    def __init__(self, parent: Optional["ServiceContainer"] = None) -> None:
        self._registrations: Dict[Type, ServiceRegistration] = {}
        self._aliases: Dict[str, Type] = {}
        self._lock = threading.RLock()
        self._parent = parent
        self._initialized: Set[Type] = set()
        self._shutdown_hooks: list[Callable[[], None]] = []

    def register(
        self,
        interface: Type[T],
        factory: Factory,
        *,
        singleton: bool = True,
        eager: bool = False,
        alias: Optional[str] = None,
    ) -> None:
        """Register a service implementation."""
        with self._lock:
            registration = ServiceRegistration(interface, factory, singleton=singleton)
            self._registrations[interface] = registration
            if alias:
                self._aliases[alias] = interface
            logger.debug("Registered %s (singleton=%s, eager=%s)", interface.__name__, singleton, eager)
        if eager:
            self.resolve(interface)

    def register_instance(self, interface: Type[T], instance: T, alias: Optional[str] = None) -> None:
        """Register an already-constructed instance as a singleton."""

        def _factory(_container: ServiceContainer) -> T:
            return instance

        self.register(interface, _factory, singleton=True, alias=alias)

    def resolve(self, interface: Type[T]) -> T:
        """Resolve a service by its interface type."""
        with self._lock:
            registration = self._registrations.get(interface)
            if registration is None and self._parent is not None:
                return self._parent.resolve(interface)
            if registration is None:
                raise KeyError(f"Service not registered: {interface.__name__}")

            instance = registration.resolve(self)

            if interface not in self._initialized:
                self._initialized.add(interface)
                if hasattr(instance, "on_init"):
                    try:
                        instance.on_init()
                    except Exception as exc:
                        logger.error("Service %s.on_init() failed: %s", interface.__name__, exc)

            return instance

    def resolve_by_alias(self, alias: str) -> Any:
        """Resolve a service by its string alias."""
        with self._lock:
            interface = self._aliases.get(alias)
            if interface is None and self._parent is not None:
                return self._parent.resolve_by_alias(alias)
            if interface is None:
                raise KeyError(f"No service registered with alias: {alias}")
            return self.resolve(interface)

    def try_resolve(self, interface: Type[T], default: Optional[T] = None) -> Optional[T]:
        try:
            return self.resolve(interface)
        except KeyError:
            return default

    def is_registered(self, interface: Type) -> bool:
        with self._lock:
            return interface in self._registrations

    def on_shutdown(self, hook: Callable[[], None]) -> None:
        self._shutdown_hooks.append(hook)

    def shutdown(self) -> None:
        for hook in self._shutdown_hooks:
            try:
                hook()
            except Exception as exc:
                logger.warning("Shutdown hook failed: %s", exc)
        self._registrations.clear()
        self._aliases.clear()

    def create_scope(self) -> "ServiceContainer":
        return ServiceContainer(parent=self)

    def register_all(self, mappings: Dict[Type, Factory]) -> None:
        for interface, factory in mappings.items():
            self.register(interface, factory)
