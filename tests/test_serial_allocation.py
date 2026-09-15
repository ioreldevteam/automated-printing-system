import pytest

from app.application.job_service import JobService
from app.application.serial_service import SerialService
from app.config.loader import ApiConfig
from app.database.database import session_scope
from app.database.repositories import ProductRepository, UnitRepository


def test_allocation_creates_unique_serials(seeded_product):
    with session_scope() as session:
        job = JobService(session).create_job("PROD-A", 50, created_by=None)
        product = ProductRepository(session).get(seeded_product)
        result = SerialService(session, ApiConfig(mode="local")).allocate_for_job(job, product)
        assert result.quantity == 50
        assert len(set(result.serials)) == 50

        units = UnitRepository(session).list_for_job(job.id)
        assert len(units) == 50
        assert all(u.overall_status == "QUEUED" for u in units)


def test_allocation_is_idempotent(seeded_product):
    with session_scope() as session:
        job = JobService(session).create_job("PROD-A", 10, created_by=None)
        product = ProductRepository(session).get(seeded_product)
        service = SerialService(session, ApiConfig(mode="local"))
        first = service.allocate_for_job(job, product)
        second = service.allocate_for_job(job, product)
        assert first.serial_batch_id == second.serial_batch_id
        assert first.serials == second.serials

        units = UnitRepository(session).list_for_job(job.id)
        assert len(units) == 10  # not duplicated


def test_duplicate_serial_rejected_by_db(seeded_product):
    from sqlalchemy.exc import IntegrityError

    with session_scope() as session:
        job = JobService(session).create_job("PROD-A", 5, created_by=None)
        units = UnitRepository(session)
        units.bulk_create(job.id, ["SN0000001"], start_sequence=1)

    with pytest.raises(IntegrityError):
        with session_scope() as session:
            job2 = JobService(session).create_job("PROD-A", 5, created_by=None)
            UnitRepository(session).bulk_create(job2.id, ["SN0000001"], start_sequence=1)
