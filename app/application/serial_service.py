"""Serial allocation service (Section 22-24). Persists the API response
before anything else touches it -- production_units rows are the durable
queue, not an in-memory list (Section 24).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.api.serial_api import SerialApiClient, build_serial_api_client
from app.config.loader import ApiConfig
from app.database.models import Product, ProductionJob
from app.database.repositories import JobRepository, UnitRepository
from app.domain.models import SerialAllocationResult


class SerialService:
    def __init__(self, session: Session, api_config: ApiConfig):
        self.session = session
        self.api_config = api_config
        self.units = UnitRepository(session)
        self.jobs = JobRepository(session)

    def allocate_for_job(self, job: ProductionJob, product: Product) -> SerialAllocationResult:
        client: SerialApiClient = build_serial_api_client(self.api_config, self.session)
        result = client.allocate(
            client_job_id=job.job_number, job_id=job.id,
            product_code=product.product_code, quantity=job.requested_quantity,
        )

        already_allocated = job.serial_batch_id == result.serial_batch_id and job.allocated_quantity > 0
        if not already_allocated:
            self.units.bulk_create(job_id=job.id, serials=result.serials, start_sequence=1)
            job.serial_batch_id = result.serial_batch_id
            job.allocated_quantity = result.quantity
            self.session.flush()

            for unit in self.units.list_for_job(job.id):
                if unit.overall_status == "ALLOCATED":
                    unit.overall_status = "QUEUED"
            self.session.flush()

        return result
