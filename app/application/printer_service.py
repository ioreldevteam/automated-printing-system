"""Printer service (Section 32-36): wraps PrinterManager with DB-backed event
persistence and normalized status, so the rest of the app never touches a
vendor adapter directly.

Important: poll_and_record() must be called with a session whose transaction
is still open, but it does NOT publish to the EventBus itself -- it returns
the events that should fire. Emitting synchronously from inside an open
transaction would let a subscriber (e.g. ProductionController pausing the
job) open a second database transaction while the first is still uncommitted,
which self-deadlocks SQLite's single-writer model. Callers must emit the
returned events only after their `session_scope()` block has exited/committed
(see monitoring/printer_monitor.py).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.repositories import PrinterEventRepository, PrinterRepository
from app.domain.events import EventType
from app.domain.models import PrinterStatusInfo
from app.domain.states import MANUAL_RECOVERY_PRINTER_STATES, PrinterStatus
from app.printers.printer_manager import PrinterManager

PendingEvent = tuple[EventType, dict]


class PrinterService:
    """Long-lived: construct once (per monitor/session-owner) and reuse across
    polls so `_last_status` correctly tracks state changes between calls."""

    def __init__(self, printer_manager: PrinterManager):
        self.printer_manager = printer_manager
        self._last_status: dict[str, PrinterStatus] = {}

    def sync_configured_printers(self, session: Session) -> None:
        """Ensure every configured printer has a DB row (Section 16)."""
        printers = PrinterRepository(session)
        for name in self.printer_manager.names():
            cfg = self.printer_manager.config_for(name)
            printers.upsert(name=cfg.name, type_=cfg.type, model=cfg.model,
                             ip_address=cfg.address, port=cfg.port)

    def test_printer(self, name: str) -> bool:
        printer = self.printer_manager.get(name)
        try:
            printer.connect()
        except Exception:
            return False
        return printer.test_print()

    def poll_and_record(self, session: Session, name: str) -> tuple[PrinterStatusInfo, list[PendingEvent]]:
        """Poll one printer and persist a PrinterEvent on any state change
        (Section 35). Returns the status plus any events the caller should
        emit once its transaction has committed."""
        printer = self.printer_manager.get(name)
        info = printer.get_status()
        db_printer = PrinterRepository(session).get_by_name(name)
        previous = self._last_status.get(name)
        pending: list[PendingEvent] = []

        if previous != info.status:
            self._last_status[name] = info.status
            if db_printer is not None:
                PrinterEventRepository(session).record(
                    printer_id=db_printer.id, event_type="STATUS_CHANGE",
                    status=info.status.value, message=info.detail, error_code=info.fault_code,
                )
            if info.status in MANUAL_RECOVERY_PRINTER_STATES or info.status == PrinterStatus.OFFLINE:
                pending.append((EventType.PRINTER_ERROR,
                                 {"printer_name": name, "status": info.status.value, "detail": info.detail}))
            elif previous is not None and previous in MANUAL_RECOVERY_PRINTER_STATES:
                pending.append((EventType.PRINTER_RECOVERED, {"printer_name": name, "status": info.status.value}))
        return info, pending

    def is_faulted(self, name: str) -> bool:
        status = self._last_status.get(name)
        return status is not None and (status in MANUAL_RECOVERY_PRINTER_STATES)

    def last_known_status(self, name: str) -> PrinterStatus | None:
        """Cached status from the most recent poll -- safe to call from the
        UI thread since it never touches the network (unlike get_status())."""
        return self._last_status.get(name)
