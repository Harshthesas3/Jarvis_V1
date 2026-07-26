"""Event system interfaces for event-driven communication."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict
from enum import Enum


class EventPriority(Enum):
    """Priority levels for event delivery."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass(frozen=True)
class SystemEvent:
    """A typed event in the system event bus."""
    type: str
    source: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    priority: EventPriority = EventPriority.NORMAL


EventHandler = Callable[["SystemEvent"], None]


class EventBus(ABC):
    """System-wide event bus for decoupled communication."""

    @abstractmethod
    def publish(self, event: SystemEvent) -> None:
        """Publish an event to the bus."""

    @abstractmethod
    def subscribe(self, event_type: str, handler: EventHandler, priority: EventPriority = EventPriority.NORMAL) -> None:
        """Subscribe to events of a specific type."""

    @abstractmethod
    def unsubscribe(self, event_type: str, handler: EventHandler) -> bool:
        """Remove a subscription."""

    @abstractmethod
    def publish_async(self, event: SystemEvent) -> None:
        """Publish an event asynchronously (non-blocking)."""


class EventSubscriber(ABC):
    """Components that subscribe to events implement this."""

    @abstractmethod
    def get_subscriptions(self) -> Dict[str, EventHandler]:
        """Return event_type -> handler mappings for auto-subscription."""
