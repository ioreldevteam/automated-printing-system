"""Durable queue backed by SQLite (Section 44). There is no separate queue
table -- `production_units.overall_status` *is* the queue, so a crash never
loses queue position. These helpers just name the two queries the workers
need.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.database.models import ProductionUnit
from app.database.repositories import UnitRepository


def next_unit_for_anser(session: Session, job_id: int) -> ProductionUnit | None:
    return UnitRepository(session).next_queued(job_id)


def next_unit_for_zebra(session: Session, job_id: int) -> ProductionUnit | None:
    return UnitRepository(session).next_anser_printed_awaiting_zebra(job_id)
