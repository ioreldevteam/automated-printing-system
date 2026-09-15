"""Event-driven design (Section 72). A lightweight in-process event bus lets the
production controller, monitors, and UI stay decoupled without importing PySide6
into non-UI layers.
"""
from __future__ import annotations

import enum
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


class EventType(str, enum.Enum):
    PRODUCT_SELECTED = "PRODUCT_SELECTED"
    JOB_CREATED = "JOB_CREATED"
    SERIALS_ALLOCATED = "SERIALS_ALLOCATED"

    PRODUCTION_STARTED = "PRODUCTION_STARTED"
    PRODUCTION_PAUSED = "PRODUCTION_PAUSED"
    PRODUCTION_RESUMED = "PRODUCTION_RESUMED"
    PRODUCTION_STOPPED = "PRODUCTION_STOPPED"

    PRINTER_CONNECTED = "PRINTER_CONNECTED"
    PRINTER_DISCONNECTED = "PRINTER_DISCONNECTED"
    PRINTER_ERROR = "PRINTER_ERROR"
    PRINTER_RECOVERED = "PRINTER_RECOVERED"

    UNIT_QUEUED = "UNIT_QUEUED"
    UNIT_PRINT_STARTED = "UNIT_PRINT_STARTED"
    UNIT_PRINT_COMPLETED = "UNIT_PRINT_COMPLETED"
    UNIT_VERIFICATION_FAILED = "UNIT_VERIFICATION_FAILED"
    UNIT_COMPLETED = "UNIT_COMPLETED"

    JOB_COMPLETED = "JOB_COMPLETED"
    JOB_PAUSED = "JOB_PAUSED"

    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


@dataclass(frozen=True)
class Event:
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EventBus:
    """Thread-safe publish/subscribe bus. Subscribers are called synchronously
    on the publishing thread — UI subscribers must marshal onto the Qt thread
    themselves (see ui/main_window.py bridging via Qt signals).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: dict[EventType, list[Callable[[Event], None]]] = {}
        self._global_subscribers: list[Callable[[Event], None]] = []

    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]) -> None:
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(handler)

    def subscribe_all(self, handler: Callable[[Event], None]) -> None:
        with self._lock:
            self._global_subscribers.append(handler)

    def publish(self, event: Event) -> None:
        with self._lock:
            handlers = list(self._subscribers.get(event.type, ())) + list(self._global_subscribers)
        for handler in handlers:
            handler(event)

    def emit(self, event_type: EventType, **payload: Any) -> None:
        self.publish(Event(type=event_type, payload=payload))
