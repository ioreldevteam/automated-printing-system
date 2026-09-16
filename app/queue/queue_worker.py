"""Background workers that drive the durable queue (Section 45). Each worker
is a plain Python thread (not a QThread) so the application/queue layers stay
Qt-independent and unit-testable; the UI marshals updates via EventBus and
Qt signals instead (Section 46).

Retry policy (Section 37/38):
  - retryable errors (timeout, busy, connection reset) -> requeue up to
    printing.max_retries, then FAILED.
  - manual-recovery errors (media out, ribbon out, head open, offline) ->
    pause the job; the operator fixes hardware and resumes the same unit.
  - uncertain results (Section 39) -> UNKNOWN, never blindly retried; the
    job pauses and recovery_service.reconcile_unit() decides what happens.

Transaction shape: each DB transaction here is kept short and is followed by
EventBus.emit() / pause_callback() calls made AFTER the `session_scope()`
block has committed and released its write lock. Calling back into the
database (as pause_callback and several event handlers do) while a prior
transaction is still open self-deadlocks SQLite's single-writer model, so
the "claim/do the printer I/O/record the result" phases are deliberately
separated by transaction boundaries.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from app.database.database import session_scope
from app.database.repositories import (
    JobRepository,
    PrintAttemptRepository,
    ProductRepository,
    PrinterRepository,
    UnitRepository,
)
from app.domain.events import EventBus, EventType
from app.domain.models import LabelData
from app.domain.states import PrintStage, UnitStatus
from app.printers.base import PrinterError
from app.printers.printer_manager import PrinterManager
from app.printers.template_engine import load_template

logger = logging.getLogger("production")


@dataclass
class WorkerContext:
    job_id: int
    printer_name: str
    max_retries: int
    poll_interval_seconds: float = 0.2


PauseCallback = Callable[[int, str, str], None]  # (job_id, error_code, message) -> None


def _resume_target_for_retry(unit) -> UnitStatus:
    """A RETRY_PENDING unit resumes to QUEUED (retry ANSER) if ANSER never
    succeeded, or ANSER_PRINTED (retry ZEBRA only) if it already did."""
    return UnitStatus.ANSER_PRINTED if unit.anser_status == UnitStatus.ANSER_PRINTED.value else UnitStatus.QUEUED


class BaseQueueWorker(threading.Thread):
    def __init__(self, context: WorkerContext, printer_manager: PrinterManager, event_bus: EventBus,
                 pause_callback: PauseCallback, is_job_running: Callable[[int], bool]):
        super().__init__(daemon=True)
        self.context = context
        self.printer_manager = printer_manager
        self.event_bus = event_bus
        self.pause_callback = pause_callback
        self.is_job_running = is_job_running
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:  # pragma: no cover - exercised via integration tests calling process_once
        while not self._stop_event.is_set():
            if not self.is_job_running(self.context.job_id):
                time.sleep(self.context.poll_interval_seconds)
                continue
            try:
                processed = self.process_once()
            except Exception:  # noqa: BLE001 - a worker crash must not kill the app
                logger.exception("Unhandled error in %s", self.__class__.__name__)
                processed = False
            if not processed:
                time.sleep(self.context.poll_interval_seconds)

    def process_once(self) -> bool:
        raise NotImplementedError


class AnserWorker(BaseQueueWorker):
    """Pushes the next queued serial into the ANSER X1's FIFO input
    (Section 28.1) and treats a successful push as the print attempt. The
    X1's own photocell/sensor fires the physical print; get_consumption_count
    could be polled separately for stricter confirmation once the real
    register map (Section 105 item 1) is confirmed -- see
    application/recovery_service.py's use of it during reconciliation."""

    def process_once(self) -> bool:
        # Phase 1: claim the next queued unit (short transaction).
        with session_scope() as session:
            units = UnitRepository(session)
            unit = units.next_queued(self.context.job_id)
            if unit is None:
                return False
            units.set_status(unit, UnitStatus.ANSER_PRINTING)
            unit_id = unit.id
            serial_number = unit.serial_number
            db_printer = PrinterRepository(session).get_by_name(self.context.printer_name)
            printer_id = db_printer.id if db_printer else None
            attempt_number = PrintAttemptRepository(session).count_for_unit_stage(unit_id, PrintStage.ANSER.value) + 1

        self.event_bus.emit(EventType.UNIT_PRINT_STARTED, unit_id=unit_id, serial=serial_number, stage="ANSER")

        # Phase 2: the actual printer I/O, outside any open transaction.
        try:
            printer = self.printer_manager.get(self.context.printer_name)
            printer.push_serial(serial_number)
            error: PrinterError | None = None
        except PrinterError as exc:
            error = exc
        except KeyError:
            # The printer this job is assigned to isn't registered with the
            # printer manager (never configured, or a discovered printer
            # that disappeared/was never connected). Without this, the
            # exception was only caught by the generic `except Exception` in
            # run(), which logs it and silently retries forever: the unit
            # stays stuck in ANSER_PRINTING (already committed in Phase 1)
            # and nothing is ever recorded or surfaced to the operator.
            error = PrinterError(
                f"Printer '{self.context.printer_name}' is not configured/connected",
                error_code="PRINTER_001",
            )

        # Phase 3: record the result (short transaction).
        pause_info: tuple[int, str, str] | None = None
        if error is None:
            with session_scope() as session:
                PrintAttemptRepository(session).record(unit_id, printer_id, PrintStage.ANSER.value,
                                                         attempt_number, status="SUCCESS")
                unit = UnitRepository(session).get(unit_id)
                unit.anser_status = UnitStatus.ANSER_PRINTED.value
                unit.anser_printed_at = datetime.utcnow()
                UnitRepository(session).set_status(unit, UnitStatus.ANSER_PRINTED)
            self.event_bus.emit(EventType.UNIT_PRINT_COMPLETED, unit_id=unit_id, serial=serial_number, stage="ANSER")
        else:
            with session_scope() as session:
                PrintAttemptRepository(session).record(
                    unit_id, printer_id, PrintStage.ANSER.value, attempt_number,
                    status="UNKNOWN" if error.uncertain else "FAILED",
                    error_code=error.error_code, error_message=str(error),
                )
                unit = UnitRepository(session).get(unit_id)
                unit.attempt_count += 1
                if error.uncertain:
                    UnitRepository(session).set_status(unit, UnitStatus.UNKNOWN)
                elif error.error_code in ("PRINTER_001", "PRINTER_002", "PRINTER_003", "PRINTER_004"):
                    UnitRepository(session).set_status(unit, UnitStatus.RETRY_PENDING)
                elif unit.attempt_count < self.context.max_retries:
                    UnitRepository(session).set_status(unit, UnitStatus.RETRY_PENDING)
                else:
                    UnitRepository(session).set_status(unit, UnitStatus.FAILED)
            pause_info = (self.context.job_id, error.error_code, str(error))

        if pause_info is not None:
            self.pause_callback(*pause_info)
        return True


class ZebraWorker(BaseQueueWorker):
    def __init__(self, context: WorkerContext, printer_manager: PrinterManager, event_bus: EventBus,
                 pause_callback: PauseCallback, is_job_running: Callable[[int], bool],
                 template_path: str, verification_required: bool = False):
        super().__init__(context, printer_manager, event_bus, pause_callback, is_job_running)
        self.template_path = template_path
        self.verification_required = verification_required
        self._template_cache: Optional[str] = None

    def _template(self) -> str:
        if self._template_cache is None:
            self._template_cache = load_template(self.template_path)
        return self._template_cache

    def process_once(self) -> bool:
        # Phase 1: claim the next ANSER-printed unit awaiting Zebra.
        with session_scope() as session:
            units = UnitRepository(session)
            unit = units.next_anser_printed_awaiting_zebra(self.context.job_id)
            if unit is None:
                return False
            units.set_status(unit, UnitStatus.ZEBRA_PRINTING)
            unit_id = unit.id
            serial_number = unit.serial_number

            job = JobRepository(session).get(self.context.job_id)
            product = ProductRepository(session).get(job.product_id) if job else None
            label = LabelData(product_name=product.product_name if product else "",
                               serial_number=serial_number,
                               batch_number=job.serial_batch_id if job else "")

            db_printer = PrinterRepository(session).get_by_name(self.context.printer_name)
            printer_id = db_printer.id if db_printer else None
            attempt_number = PrintAttemptRepository(session).count_for_unit_stage(unit_id, PrintStage.ZEBRA.value) + 1

        self.event_bus.emit(EventType.UNIT_PRINT_STARTED, unit_id=unit_id, serial=serial_number, stage="ZEBRA")

        # Phase 2: the actual printer I/O, outside any open transaction.
        try:
            printer = self.printer_manager.get(self.context.printer_name)
            printer.print_label(self._template(), label)
            error: PrinterError | None = None
        except PrinterError as exc:
            error = exc
        except KeyError:
            # See AnserWorker.process_once: an unregistered printer name
            # must not fall through to the generic exception handler in
            # run(), or the unit stays stuck mid-print forever with no
            # error ever recorded and nothing visible to the operator.
            error = PrinterError(
                f"Printer '{self.context.printer_name}' is not configured/connected",
                error_code="PRINTER_001",
            )

        # Phase 3: record the result (short transaction).
        pause_info: tuple[int, str, str] | None = None
        job_completed = False
        if error is None:
            with session_scope() as session:
                PrintAttemptRepository(session).record(unit_id, printer_id, PrintStage.ZEBRA.value,
                                                         attempt_number, status="SUCCESS")
                units = UnitRepository(session)
                unit = units.get(unit_id)
                unit.zebra_status = UnitStatus.ZEBRA_PRINTED.value
                unit.zebra_printed_at = datetime.utcnow()

                if self.verification_required:
                    units.set_status(unit, UnitStatus.VERIFYING)
                else:
                    units.set_status(unit, UnitStatus.COMPLETED)

                job = JobRepository(session).get(self.context.job_id)
                if job is not None:
                    JobRepository(session).recompute_counters(job)
                    job_completed = job.completed_quantity >= job.requested_quantity

            if not self.verification_required:
                self.event_bus.emit(EventType.UNIT_COMPLETED, unit_id=unit_id, serial=serial_number)
            if job_completed:
                self.event_bus.emit(EventType.JOB_COMPLETED, job_id=self.context.job_id)
        else:
            with session_scope() as session:
                PrintAttemptRepository(session).record(
                    unit_id, printer_id, PrintStage.ZEBRA.value, attempt_number,
                    status="UNKNOWN" if error.uncertain else "FAILED",
                    error_code=error.error_code, error_message=str(error),
                )
                units = UnitRepository(session)
                unit = units.get(unit_id)
                unit.attempt_count += 1
                if error.uncertain:
                    units.set_status(unit, UnitStatus.UNKNOWN)
                elif error.error_code in ("PRINTER_001", "PRINTER_002", "PRINTER_003", "PRINTER_004"):
                    units.set_status(unit, UnitStatus.RETRY_PENDING)
                elif unit.attempt_count < self.context.max_retries:
                    units.set_status(unit, UnitStatus.RETRY_PENDING)
                else:
                    units.set_status(unit, UnitStatus.FAILED)
            pause_info = (self.context.job_id, error.error_code, str(error))

        if pause_info is not None:
            self.pause_callback(*pause_info)
        return True
