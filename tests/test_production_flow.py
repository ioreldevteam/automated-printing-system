"""End-to-end recovery test (Section 79/80/101): run a batch through the real
ProductionController + background queue workers using SimulationPrinter,
inject a printer fault partway through, resume, and verify no duplicate or
missing serials -- the acceptance criterion in Section 80.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.application.job_service import JobService
from app.application.production_service import ProductionController
from app.application.recovery_service import RecoveryService
from app.application.serial_service import SerialService
from app.config.loader import ApiConfig, AnserModbusConfig, PrinterConfig
from app.database.database import session_scope
from app.database.repositories import JobRepository, PrintAttemptRepository, ProductRepository, UnitRepository
from app.domain.events import EventBus
from app.domain.states import JobStatus, UnitStatus, PrintStage
from app.printers.printer_manager import PrinterManager
from app.printers.simulation import SimulationPrinter

TEMPLATE_PATH = str(
    Path(__file__).resolve().parents[1] / "app" / "templates" / "zpl" / "sticker_label_v1.zpl"
)


def _wait_for(predicate, timeout=15.0, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def _build_controller(event_bus: EventBus) -> tuple[ProductionController, PrinterManager]:
    printer_manager = PrinterManager()
    printer_manager.load_from_config([
        PrinterConfig(name="ANSER-01", type="ANSER", address="127.0.0.1", port=502, simulate=True,
                      anser_modbus=AnserModbusConfig()),
        PrinterConfig(name="ZEBRA-01", type="ZEBRA", address="127.0.0.1", port=9100, simulate=True),
    ])
    printer_manager.connect_all()
    controller = ProductionController(
        printer_manager=printer_manager, event_bus=event_bus, max_retries=3,
        anser_printer_name="ANSER-01", zebra_printer_name="ZEBRA-01",
        zebra_template_path=TEMPLATE_PATH,
    )
    return controller, printer_manager


def _create_and_start_job(seeded_product, quantity: int) -> int:
    with session_scope() as session:
        job = JobService(session).create_job("PROD-A", quantity, created_by=None)
        product = ProductRepository(session).get(seeded_product)
        SerialService(session, ApiConfig(mode="local")).allocate_for_job(job, product)
        job_service = JobService(session)
        job_service.mark_serials_allocated(job, None)
        job_service.mark_ready(job, None)
        job_service.start_job(job, None)
        return job.id


def test_full_batch_completes_without_duplicates_or_gaps(seeded_product, seeded_printers):
    quantity = 25
    event_bus = EventBus()
    controller, printer_manager = _build_controller(event_bus)
    job_id = _create_and_start_job(seeded_product, quantity)

    try:
        controller.start_job(job_id)

        def job_completed():
            with session_scope() as session:
                job = JobRepository(session).get(job_id)
                return job.status == JobStatus.COMPLETED.value

        assert _wait_for(job_completed, timeout=20.0), "job did not complete in time"

        with session_scope() as session:
            units = UnitRepository(session).list_for_job(job_id)
            statuses = [u.overall_status for u in units]
            serials = [u.serial_number for u in units]

        assert len(serials) == len(set(serials)) == quantity
        assert all(s == UnitStatus.COMPLETED.value for s in statuses)
    finally:
        controller.shutdown()


def test_printer_fault_pauses_and_resume_finishes_without_duplication(seeded_product, seeded_printers):
    quantity = 20
    fail_at_zebra_call = 8  # inject after a handful of units have completed

    event_bus = EventBus()
    controller, printer_manager = _build_controller(event_bus)
    job_id = _create_and_start_job(seeded_product, quantity)

    zebra_sim: SimulationPrinter = printer_manager.get("ZEBRA-01")  # type: ignore[assignment]
    zebra_sim.inject_failure("media_out", at_call=fail_at_zebra_call)

    try:
        controller.start_job(job_id)

        def job_paused():
            with session_scope() as session:
                job = JobRepository(session).get(job_id)
                return job is not None and job.status == JobStatus.PAUSED.value

        assert _wait_for(job_paused, timeout=20.0), "job did not pause after simulated fault"

        with session_scope() as session:
            units = UnitRepository(session).list_for_job(job_id)
            retry_units = [u for u in units if u.overall_status == UnitStatus.RETRY_PENDING.value]
            assert len(retry_units) == 1
            stuck_unit_id = retry_units[0].id
            # The unit that failed already succeeded at the ANSER stage.
            assert retry_units[0].anser_status == UnitStatus.ANSER_PRINTED.value

        # Operator "replaces media" and resumes.
        zebra_sim.clear_failures()
        controller.resume_job(job_id, None)

        def job_completed():
            with session_scope() as session:
                job = JobRepository(session).get(job_id)
                return job is not None and job.status == JobStatus.COMPLETED.value

        assert _wait_for(job_completed, timeout=20.0), "job did not complete after resume"

        with session_scope() as session:
            units = UnitRepository(session).list_for_job(job_id)
            serials = [u.serial_number for u in units]
            assert len(serials) == len(set(serials)) == quantity
            assert all(u.overall_status == UnitStatus.COMPLETED.value for u in units)

            attempts_repo = PrintAttemptRepository(session)
            zebra_attempts = attempts_repo.count_for_unit_stage(stuck_unit_id, PrintStage.ZEBRA.value)
            # One failed attempt, one successful retry -- not a silent duplicate completion.
            assert zebra_attempts == 2
    finally:
        controller.shutdown()


def test_crash_recovery_reclassifies_in_flight_units_as_unknown(seeded_product):
    with session_scope() as session:
        job = JobService(session).create_job("PROD-A", 5, created_by=None)
        product = ProductRepository(session).get(seeded_product)
        SerialService(session, ApiConfig(mode="local")).allocate_for_job(job, product)
        job_service = JobService(session)
        job_service.mark_serials_allocated(job, None)
        job_service.mark_ready(job, None)
        job_service.start_job(job, None)

        units = UnitRepository(session).list_for_job(job.id)
        in_flight_unit = units[2]
        in_flight_unit.overall_status = UnitStatus.ZEBRA_PRINTING.value
        session.flush()
        job_id = job.id
        in_flight_unit_id = in_flight_unit.id

    with session_scope() as session:
        job_service = JobService(session)
        job = JobRepository(session).get(job_id)
        job_service.pause_job(job, None, reason="simulated crash")

    with session_scope() as session:
        summaries = RecoveryService(session).scan_on_startup()
        summary = next(s for s in summaries if s.job_id == job_id)
        assert any(r.unit_id == in_flight_unit_id and r.outcome == "OPERATOR_DECISION"
                   for r in summary.needs_operator_review)

        unit = UnitRepository(session).get(in_flight_unit_id)
        assert unit.overall_status == UnitStatus.UNKNOWN.value

        RecoveryService(session).apply_decision(in_flight_unit_id, "not_printed")
        unit = UnitRepository(session).get(in_flight_unit_id)
        assert unit.overall_status == UnitStatus.QUEUED.value


def test_job_pauses_cleanly_when_assigned_printer_is_not_registered(seeded_product):
    """If a job is (mis)assigned to a printer name the PrinterManager doesn't
    actually have -- e.g. the operator's dropdown selection referenced a
    printer that never got registered/connected -- the job must pause with a
    clear PRINTER_001 error instead of hanging forever with units stuck
    mid-print and nothing recorded (the previous behaviour: printer_manager
    .get() raised a bare KeyError that only the generic `except Exception` in
    BaseQueueWorker.run() caught, so it was logged and silently retried
    forever)."""
    event_bus = EventBus()
    printer_manager = PrinterManager()
    printer_manager.load_from_config([
        PrinterConfig(name="ANSER-01", type="ANSER", address="127.0.0.1", port=502, simulate=True,
                      anser_modbus=AnserModbusConfig()),
        # Deliberately no ZEBRA-01/real label printer registered.
    ])
    printer_manager.connect_all()
    controller = ProductionController(
        printer_manager=printer_manager, event_bus=event_bus, max_retries=3,
        anser_printer_name="ANSER-01", zebra_printer_name="MISSING-PRINTER",
        zebra_template_path=TEMPLATE_PATH,
    )

    job_id = _create_and_start_job(seeded_product, 3)

    try:
        controller.start_job(job_id)

        def job_paused():
            with session_scope() as session:
                job = JobRepository(session).get(job_id)
                return job is not None and job.status == JobStatus.PAUSED.value

        assert _wait_for(job_paused, timeout=20.0), "job did not pause for the unregistered printer"

        # The unit stuck at the Zebra stage should be RETRY_PENDING (i.e. a
        # recorded, recoverable failure), not silently abandoned mid-print.
        with session_scope() as session:
            units = UnitRepository(session).list_for_job(job_id)
            assert any(u.overall_status == UnitStatus.RETRY_PENDING.value for u in units)
    finally:
        controller.shutdown()
