"""System health snapshot for the dashboard (Section 61/84): distinguishes
LOCAL OPERATION (database + printers) from EXTERNAL API CONNECTIVITY so the
UI can show, e.g., "API: OFFLINE, Local serial buffer: 100, Printer: ONLINE,
Production: RUNNING" without conflating the two.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config.loader import AppConfig
from app.database.repositories import JobRepository, UnitRepository
from app.domain.states import JobStatus, UnitStatus
from app.monitoring.network_monitor import check_network_status


@dataclass
class HealthSnapshot:
    database_ok: bool
    api_reachable: bool
    printer_reachable: dict[str, bool]
    serial_buffer_remaining: int


def get_health_snapshot(session: Session, config: AppConfig, job_id: int | None) -> HealthSnapshot:
    database_ok = True
    try:
        JobRepository(session).list_active()
    except Exception:
        database_ok = False

    network = check_network_status(config.api, config.printers)

    buffer_remaining = 0
    if job_id is not None:
        units = UnitRepository(session).list_for_job(job_id)
        buffer_remaining = sum(
            1 for u in units if u.overall_status in (UnitStatus.QUEUED.value, UnitStatus.ANSER_PRINTED.value)
        )

    return HealthSnapshot(
        database_ok=database_ok,
        api_reachable=network.api_reachable,
        printer_reachable=network.printer_reachable,
        serial_buffer_remaining=buffer_remaining,
    )
