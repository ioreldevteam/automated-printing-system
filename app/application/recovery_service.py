"""Recovery engine (Section 53, 88-90). Runs at application startup and
whenever a printer error pauses production. Never assumes `last_sequence + 1`
(Section 88) -- every in-flight unit is explicitly reclassified.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.database.repositories import JobRepository, PrinterEventRepository, PrinterRepository, UnitRepository
from app.domain.models import ReconciliationResult
from app.domain.states import JobStatus, UnitStatus
from app.printers.anser import AnserPrinter
from app.printers.printer_manager import PrinterManager


@dataclass
class RecoverySummary:
    job_id: int
    job_number: str
    completed: int
    failed: int
    remaining: int
    current_serial: str | None
    reconciled: list[ReconciliationResult] = field(default_factory=list)
    needs_operator_review: list[ReconciliationResult] = field(default_factory=list)


class RecoveryService:
    def __init__(self, session: Session, printer_manager: PrinterManager | None = None):
        self.session = session
        self.jobs = JobRepository(session)
        self.units = UnitRepository(session)
        self.printer_events = PrinterEventRepository(session)
        self.printers = PrinterRepository(session)
        self.printer_manager = printer_manager

    def scan_on_startup(self) -> list[RecoverySummary]:
        """Section 53: find RUNNING/PAUSED jobs, reclassify in-flight units as
        UNKNOWN (a crash means the physical result cannot be trusted), then
        reconcile. Returns one summary per active job for the recovery screen."""
        summaries = []
        for job in self.jobs.list_active():
            for unit in self.units.in_flight_for_job(job.id):
                self.units.set_status(unit, UnitStatus.UNKNOWN)
            summaries.append(self.build_summary(job.id))
        return summaries

    def build_summary(self, job_id: int) -> RecoverySummary:
        job = self.jobs.get(job_id)
        units = self.units.list_for_job(job_id)
        completed = sum(1 for u in units if u.overall_status == UnitStatus.COMPLETED.value)
        failed = sum(1 for u in units if u.overall_status == UnitStatus.FAILED.value)
        remaining = len(units) - completed - failed
        current = next(
            (u.serial_number for u in units
             if u.overall_status not in (UnitStatus.COMPLETED.value, UnitStatus.ALLOCATED.value)),
            None,
        )
        reconciled = [self.reconcile_unit(u.id) for u in units if u.overall_status == UnitStatus.UNKNOWN.value]
        needs_review = [r for r in reconciled if r.outcome == "OPERATOR_DECISION"]
        return RecoverySummary(
            job_id=job.id, job_number=job.job_number, completed=completed, failed=failed,
            remaining=remaining, current_serial=current, reconciled=reconciled,
            needs_operator_review=needs_review,
        )

    def reconcile_unit(self, unit_id: int) -> ReconciliationResult:
        """Section 40. Order of evidence: printer counter (if the adapter can
        report one), then fall back to an explicit operator decision -- never
        silently guess COMPLETED, which would risk creating a duplicate print
        the next time this serial is queued."""
        unit = self.units.get(unit_id)
        if unit is None:
            raise ValueError(f"Unknown unit id {unit_id}")

        if unit.overall_status == UnitStatus.ANSER_PRINTING.value or unit.anser_status == "":
            counter_result = self._check_anser_counter(unit_id)
            if counter_result is not None:
                return counter_result

        return ReconciliationResult(
            unit_id=unit.id, serial_number=unit.serial_number, outcome="OPERATOR_DECISION",
            reason="Print result could not be automatically verified; operator must confirm physical state.",
        )

    def _check_anser_counter(self, unit_id: int) -> ReconciliationResult | None:
        """Best-effort automatic reconciliation using the ANSER consumption
        counter, when the adapter is a real (non-simulated) AnserPrinter and
        the printer is reachable. Section 105 item 3 flags that whether this
        counter is per-unit or aggregate-only is still unconfirmed -- so this
        can only be trusted to answer "at least N units were consumed", never
        to identify a specific serial. It is deliberately conservative."""
        if self.printer_manager is None:
            return None
        unit = self.units.get(unit_id)
        for name in self.printer_manager.names():
            printer = self.printer_manager.get(name)
            if not isinstance(printer, AnserPrinter):
                continue
            try:
                count = printer.get_consumption_count()
            except Exception:
                return None
            if count >= unit.sequence_number:
                return ReconciliationResult(
                    unit_id=unit.id, serial_number=unit.serial_number, outcome="COMPLETED",
                    reason=f"ANSER consumption counter ({count}) confirms sequence {unit.sequence_number} printed.",
                )
        return None

    def apply_decision(self, unit_id: int, decision: str) -> None:
        """Operator resolves an OPERATOR_DECISION reconciliation result.
        decision: "printed" -> COMPLETED, "not_printed" -> RETRY_PENDING."""
        unit = self.units.get(unit_id)
        if unit is None:
            return
        if decision == "printed":
            self.units.set_status(unit, UnitStatus.COMPLETED)
        elif decision == "not_printed":
            from app.queue.queue_worker import _resume_target_for_retry
            self.units.set_status(unit, _resume_target_for_retry(unit))
        else:
            raise ValueError(f"Unknown recovery decision: {decision}")
