"""Production controller (Section 73): the central coordinator. It never
contains vendor-specific printer code (Section 73) -- it only starts/stops
queue workers, reacts to printer/job events, and keeps the job's state in
the database in sync with what is actually happening.

Single-line assumption (Section 105 item 10 is unconfirmed): this controller
drives one active job at a time, matching a single ANSER+Zebra production
line. Running multiple simultaneous lines from one instance would need one
ProductionController per line; the class does not assume process-wide
singletons so that extension is possible later.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from app.database.database import session_scope
from app.database.repositories import JobRepository, ProductRepository, PrinterRepository, UnitRepository
from app.domain.events import EventBus, EventType
from app.domain.states import JobStatus, UnitStatus
from app.printers.base import PrinterError
from app.printers.printer_manager import PrinterManager
from app.queue.queue_worker import AnserWorker, WorkerContext, ZebraWorker, _resume_target_for_retry

logger = logging.getLogger("production")


class ProductionController:
    def __init__(self, printer_manager: PrinterManager, event_bus: EventBus,
                 max_retries: int, anser_printer_name: str, zebra_printer_name: str,
                 zebra_template_path: str, verification_required: bool = False):
        self.printer_manager = printer_manager
        self.event_bus = event_bus
        self.max_retries = max_retries
        self.anser_printer_name = anser_printer_name
        self.zebra_printer_name = zebra_printer_name
        self.zebra_template_path = zebra_template_path
        self.verification_required = verification_required

        self._lock = threading.RLock()
        self._active_job_id: Optional[int] = None
        self._anser_worker: Optional[AnserWorker] = None
        self._zebra_worker: Optional[ZebraWorker] = None

        self.event_bus.subscribe(EventType.PRINTER_ERROR, self._on_printer_error)
        self.event_bus.subscribe(EventType.JOB_COMPLETED, self._on_job_completed)

    # --- job control --------------------------------------------------------
    def start_job(self, job_id: int) -> None:
        with self._lock:
            if self._active_job_id is not None and self._active_job_id != job_id:
                raise RuntimeError(f"Another job ({self._active_job_id}) is already active on this line")
            self._active_job_id = job_id
            self._start_workers(job_id)
        self.event_bus.emit(EventType.PRODUCTION_STARTED, job_id=job_id)

    def _start_workers(self, job_id: int) -> None:
        with session_scope() as session:
            job = JobRepository(session).get(job_id)
            anser_name, zebra_name = self._assigned_printer_names(session, job)
        if self._anser_worker is None:
            context = WorkerContext(job_id=job_id, printer_name=anser_name,
                                     max_retries=self.max_retries)
            self._anser_worker = AnserWorker(context, self.printer_manager, self.event_bus,
                                              self._pause_job, self._is_job_running)
            self._anser_worker.start()
        if self._zebra_worker is None:
            context = WorkerContext(job_id=job_id, printer_name=zebra_name,
                                     max_retries=self.max_retries)
            self._zebra_worker = ZebraWorker(context, self.printer_manager, self.event_bus,
                                              self._pause_job, self._is_job_running,
                                              template_path=self.zebra_template_path,
                                              verification_required=self.verification_required)
            self._zebra_worker.start()

    def _assigned_printer_names(self, session, job):
        if job is None:
            return self.anser_printer_name, self.zebra_printer_name
        printers = PrinterRepository(session)
        anser = printers.get(job.anser_printer_id) if job.anser_printer_id else None
        zebra = printers.get(job.zebra_printer_id) if job.zebra_printer_id else None
        return (anser.name if anser else self.anser_printer_name,
                zebra.name if zebra else self.zebra_printer_name)

    def resolve_zebra_printer_name(self, job_id: int | None) -> str:
        """The label printer actually assigned to this job right now, for
        UI surfaces (e.g. the Recovery dialog's TEST PRINTER button) that
        must not fall back to the static config default -- otherwise they'd
        test/report on the wrong printer whenever a job was started against
        an operator-selected printer instead of the default one."""
        if job_id is None:
            return self.zebra_printer_name
        with session_scope() as session:
            job = JobRepository(session).get(job_id)
            _, zebra_name = self._assigned_printer_names(session, job)
            return zebra_name

    def pause_job(self, job_id: int, user_id: int | None) -> None:
        with session_scope() as session:
            jobs = JobRepository(session)
            job = jobs.get(job_id)
            if job is None:
                return
            from app.application.job_service import JobService
            JobService(session).pause_job(job, user_id, reason="Manual pause")
        self.event_bus.emit(EventType.PRODUCTION_PAUSED, job_id=job_id)

    def resume_job(self, job_id: int, user_id: int | None) -> None:
        with session_scope() as session:
            jobs = JobRepository(session)
            units = UnitRepository(session)
            job = jobs.get(job_id)
            if job is None:
                return
            for unit in units.list_for_job(job_id):
                if unit.overall_status == UnitStatus.RETRY_PENDING.value:
                    units.set_status(unit, _resume_target_for_retry(unit))
            from app.application.job_service import JobService
            JobService(session).resume_job(job, user_id)
        self._start_workers(job_id)
        self.event_bus.emit(EventType.PRODUCTION_RESUMED, job_id=job_id)

    def stop_job(self, job_id: int, user_id: int | None) -> None:
        with self._lock:
            self._stop_workers()
            self._active_job_id = None
        with session_scope() as session:
            job = JobRepository(session).get(job_id)
            if job is not None:
                from app.application.job_service import JobService
                JobService(session).stop_job(job, user_id)
        # Whatever labels made it into the buffer before the operator
        # stopped the job should still come out -- otherwise a stop would
        # silently swallow already-completed units' labels.
        self._flush_label_printer(job_id)
        self.event_bus.emit(EventType.PRODUCTION_STOPPED, job_id=job_id)

    def _flush_label_printer(self, job_id: int) -> None:
        """Send everything buffered by the job's label printer as one print
        job. Only Windows/CUPS-style adapters buffer at all (see
        BasePrinter.flush_batch) -- ANSER/Zebra/Simulation print immediately
        and this is a no-op for them."""
        zebra_name = self.resolve_zebra_printer_name(job_id)
        try:
            printer = self.printer_manager.get(zebra_name)
        except KeyError:
            return
        if not printer.supports_batch_printing():
            return
        try:
            printer.flush_batch()
        except PrinterError as exc:
            logger.warning("Failed to flush batched print job for %s: %s", zebra_name, exc)
            self._pause_job(job_id, exc.error_code, str(exc))

    def _stop_workers(self) -> None:
        if self._anser_worker is not None:
            self._anser_worker.stop()
            self._anser_worker = None
        if self._zebra_worker is not None:
            self._zebra_worker.stop()
            self._zebra_worker = None

    def shutdown(self) -> None:
        with self._lock:
            self._stop_workers()
            self._active_job_id = None

    # --- worker callbacks -----------------------------------------------------
    def _is_job_running(self, job_id: int) -> bool:
        with session_scope() as session:
            job = JobRepository(session).get(job_id)
            return job is not None and job.status == JobStatus.RUNNING.value

    def _pause_job(self, job_id: int, error_code: str, message: str) -> None:
        logger.warning("Pausing job %s due to %s: %s", job_id, error_code, message)
        with session_scope() as session:
            job = JobRepository(session).get(job_id)
            if job is None or job.status != JobStatus.RUNNING.value:
                return
            from app.application.job_service import JobService
            JobService(session).pause_job(job, None, reason=f"{error_code}: {message}")
        self.event_bus.emit(EventType.JOB_PAUSED, job_id=job_id, error_code=error_code, message=message)
        self.event_bus.emit(EventType.RECOVERY_REQUIRED, job_id=job_id, error_code=error_code, message=message)

    def _on_printer_error(self, event) -> None:  # noqa: ANN001
        with self._lock:
            job_id = self._active_job_id
        if job_id is not None:
            self._pause_job(job_id, event.payload.get("status", "PRINTER_001"), event.payload.get("detail", ""))

    def _on_job_completed(self, event) -> None:  # noqa: ANN001
        job_id = event.payload.get("job_id")
        with session_scope() as session:
            job = JobRepository(session).get(job_id)
            if job is None or job.status != JobStatus.RUNNING.value:
                return
            from app.application.job_service import JobService
            JobService(session).complete_job(job, None)
        # The full requested quantity is done -- if the assigned label
        # printer is a Windows/CUPS adapter, this is the one point where all
        # of that quantity's labels actually go to the printer, as a single
        # print job/one operator approval instead of one per label.
        self._flush_label_printer(job_id)
        with self._lock:
            if self._active_job_id == job_id:
                self._stop_workers()
                self._active_job_id = None
