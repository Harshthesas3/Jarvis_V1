"""Thread-safe in-memory event bus implementation."""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import List, Optional, Tuple

from jarvis.interfaces.events import EventBus, EventHandler, EventPriority, EventSubscriber, SystemEvent

logger = logging.getLogger("jarvis.eventbus")


class InMemoryEventBus(EventBus):
    """In-memory event bus with priority-ordered delivery.

    Thread-safe for concurrent publish/subscribe. Supports priority-based
    ordering, async publishing, and global subscribers.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: dict[str, List[Tuple[EventPriority, EventHandler]]] = defaultdict(list)
        self._global_subscribers: List[Tuple[EventPriority, EventHandler]] = []

    def publish(self, event: SystemEvent) -> None:
        handlers = self._get_handlers(event.type)
        for _, handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                logger.exception("Event handler for '%s' failed: %s", event.type, exc)

    def publish_async(self, event: SystemEvent) -> None:
        handlers = self._get_handlers(event.type)
        for _, handler in handlers:
            thread = threading.Thread(target=self._safe_dispatch, args=(handler, event), daemon=True)
            thread.start()

    def subscribe(self, event_type: str, handler: EventHandler, priority: EventPriority = EventPriority.NORMAL) -> None:
        with self._lock:
            self._subscribers[event_type].append((priority, handler))
            self._subscribers[event_type].sort(key=lambda x: x[0].value, reverse=True)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> bool:
        with self._lock:
            before = len(self._subscribers.get(event_type, []))
            self._subscribers[event_type] = [(p, h) for p, h in self._subscribers[event_type] if h is not handler]
            return len(self._subscribers[event_type]) < before

    def subscribe_all(self, handler: EventHandler, priority: EventPriority = EventPriority.NORMAL) -> None:
        with self._lock:
            self._global_subscribers.append((priority, handler))
            self._global_subscribers.sort(key=lambda x: x[0].value, reverse=True)

    def register_subscriber(self, subscriber: EventSubscriber) -> None:
        for event_type, handler in subscriber.get_subscriptions().items():
            self.subscribe(event_type, handler)

    def clear(self) -> None:
        with self._lock:
            self._subscribers.clear()
            self._global_subscribers.clear()

    def _get_handlers(self, event_type: str) -> List[Tuple[EventPriority, EventHandler]]:
        with self._lock:
            handlers = list(self._global_subscribers)
            handlers.extend(self._subscribers.get(event_type, []))
            handlers.sort(key=lambda x: x[0].value, reverse=True)
            return handlers

    def _safe_dispatch(self, handler: EventHandler, event: SystemEvent) -> None:
        try:
            handler(event)
        except Exception as exc:
            logger.exception("Async event handler failed: %s", exc)
