"""Background printer health monitor (Section 33). Runs on its own thread --
never the UI thread -- and polls each configured printer on a fixed interval,
delegating persistence/normalization to PrinterService.

Events are collected during the DB transaction and only published to the
EventBus after the transaction commits (see PrinterService docstring) --
publishing mid-transaction risks a subscriber opening a second, blocking
transaction against the same SQLite database.
"""
from __future__ import annotations

import logging
import threading

from app.application.printer_service import PrinterService
from app.database.database import session_scope
from app.domain.events import EventBus
from app.printers.printer_manager import PrinterManager

logger = logging.getLogger("application")


class PrinterMonitor(threading.Thread):
    def __init__(self, printer_manager: PrinterManager, event_bus: EventBus, poll_interval_seconds: float = 1.0):
        super().__init__(daemon=True)
        self.printer_manager = printer_manager
        self.event_bus = event_bus
        self.poll_interval_seconds = poll_interval_seconds
        self.printer_service = PrinterService(printer_manager)
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:  # pragma: no cover - exercised via poll_once in tests
        while not self._stop_event.is_set():
            self.poll_once()
            self._stop_event.wait(self.poll_interval_seconds)

    def poll_once(self) -> None:
        pending_events = []
        try:
            with session_scope() as session:
                for name in self.printer_manager.names():
                    try:
                        _, events = self.printer_service.poll_and_record(session, name)
                        pending_events.extend(events)
                    except Exception:  # noqa: BLE001
                        logger.exception("Failed polling printer %s", name)
        except Exception:  # noqa: BLE001
            logger.exception("Printer monitor iteration failed")
            return

        for event_type, payload in pending_events:
            self.event_bus.emit(event_type, **payload)
