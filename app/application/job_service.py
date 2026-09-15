"""Job lifecycle management (Section 17/52). Every transition is validated
against domain/states.py and recorded to the audit log (Section 21).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.database.models import ProductionJob
from app.database.repositories import AuditLogRepository, JobRepository, ProductRepository
from app.domain.exceptions import InvalidStateTransition, ProductionError
from app.domain.states import JobStatus, can_transition_job


class JobService:
    def __init__(self, session: Session):
        self.session = session
        self.jobs = JobRepository(session)
        self.products = ProductRepository(session)
        self.audit = AuditLogRepository(session)

    def create_job(self, product_code: str, requested_quantity: int, created_by: int | None) -> ProductionJob:
        product = self.products.get_by_code(product_code)
        if product is None:
            raise ProductionError(f"Unknown product code: {product_code}", code="SYSTEM_004")
        if requested_quantity <= 0:
            raise ProductionError("Requested quantity must be positive", code="SYSTEM_005")

        job_number = f"JOB-{datetime.utcnow():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
        job = self.jobs.create(job_number=job_number, product_id=product.id,
                                requested_quantity=requested_quantity, created_by=created_by)
        self.audit.record(created_by, "CREATE_JOB", entity_type="production_job", entity_id=job_number)
        return job

    def _transition(self, job: ProductionJob, target: JobStatus, user_id: int | None, action: str) -> None:
        current = JobStatus(job.status)
        if not can_transition_job(current, target):
            raise InvalidStateTransition(f"Cannot move job {job.job_number} from {current} to {target}")
        self.jobs.set_status(job, target)
        self.audit.record(user_id, action, entity_type="production_job", entity_id=job.job_number)

    def mark_serials_allocated(self, job: ProductionJob, user_id: int | None) -> None:
        self._transition(job, JobStatus.SERIALS_ALLOCATED, user_id, "SERIALS_ALLOCATED")

    def mark_ready(self, job: ProductionJob, user_id: int | None) -> None:
        self._transition(job, JobStatus.READY, user_id, "JOB_READY")

    def start_job(self, job: ProductionJob, user_id: int | None) -> None:
        self._transition(job, JobStatus.RUNNING, user_id, "START_JOB")

    def pause_job(self, job: ProductionJob, user_id: int | None, reason: str = "") -> None:
        self._transition(job, JobStatus.PAUSED, user_id, "PAUSE_JOB")
        if reason:
            self.audit.record(user_id, "PAUSE_REASON", entity_type="production_job",
                               entity_id=job.job_number, details=reason)

    def resume_job(self, job: ProductionJob, user_id: int | None) -> None:
        self._transition(job, JobStatus.RUNNING, user_id, "RESUME_JOB")

    def enter_recovery(self, job: ProductionJob, user_id: int | None) -> None:
        self._transition(job, JobStatus.RECOVERING, user_id, "ENTER_RECOVERY")

    def stop_job(self, job: ProductionJob, user_id: int | None) -> None:
        self._transition(job, JobStatus.STOPPING, user_id, "STOP_JOB")
        self._transition(job, JobStatus.STOPPED, user_id, "STOPPED")

    def cancel_job(self, job: ProductionJob, user_id: int | None) -> None:
        self._transition(job, JobStatus.CANCELLED, user_id, "CANCEL_JOB")

    def complete_job(self, job: ProductionJob, user_id: int | None) -> None:
        self._transition(job, JobStatus.COMPLETED, user_id, "JOB_COMPLETED")

    def fail_job(self, job: ProductionJob, user_id: int | None, reason: str) -> None:
        self._transition(job, JobStatus.FAILED, user_id, "JOB_FAILED")
        self.audit.record(user_id, "JOB_FAILED_REASON", entity_type="production_job",
                           entity_id=job.job_number, details=reason)
