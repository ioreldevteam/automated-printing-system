"""Marshals EventBus events (published from background worker threads) onto
the Qt GUI thread. PySide6 automatically queues a signal emitted from a
foreign thread to slots owned by a QObject that lives on the GUI thread, so
this is the one safe crossing point between app/* business logic threads and
app/ui/* widgets (Section 46: never touch widgets directly from a
background thread).
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from app.domain.events import Event, EventBus


class EventBridge(QObject):
    event_received = Signal(str, dict)

    def __init__(self, event_bus: EventBus, parent=None):
        super().__init__(parent)
        self.event_bus = event_bus
        event_bus.subscribe_all(self._on_event)

    def _on_event(self, event: Event) -> None:
        self.event_received.emit(event.type.value, dict(event.payload))
