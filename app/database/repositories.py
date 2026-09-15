"""Repository layer. Each repository takes a Session and performs queries /
mutations against one aggregate. Callers control the transaction boundary via
database.session_scope(); repositories never commit themselves so multiple
repository calls can be composed into one atomic transaction (Section 55).
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    ApplicationSetting,
    AuditLog,
    PrintAttempt,
    Printer,
    PrinterEvent,
    PrinterTemplate,
    Product,
    ProductionJob,
    ProductionUnit,
    ProductRoute,
    SerialBatch,
    SystemEvent,
    User,
)
from app.domain.states import JobStatus, UnitStatus, UNIT_IN_FLIGHT_STATES


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_username(self, username: str) -> Optional[User]:
        return self.session.scalar(select(User).where(User.username == username))

    def get(self, user_id: int) -> Optional[User]:
        return self.session.get(User, user_id)

    def create(self, username: str, password_hash: str, role: str) -> User:
        user = User(username=username, password_hash=password_hash, role=role, active=True)
        self.session.add(user)
        self.session.flush()
        return user

    def list_active(self) -> Sequence[User]:
        return self.session.scalars(select(User).where(User.active.is_(True))).all()

    def touch_login(self, user: User) -> None:
        user.last_login_at = datetime.utcnow()
        self.session.flush()


class ProductRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, product_id: int) -> Optional[Product]:
        return self.session.get(Product, product_id)

    def get_by_code(self, product_code: str) -> Optional[Product]:
        return self.session.scalar(select(Product).where(Product.product_code == product_code))

    def list_active(self) -> Sequence[Product]:
        return self.session.scalars(select(Product).where(Product.active.is_(True))).all()

    def create(self, product_code: str, product_name: str, external_product_id: str | None = None,
               description: str = "") -> Product:
        product = Product(
            product_code=product_code,
            product_name=product_name,
            external_product_id=external_product_id,
            description=description,
            active=True,
        )
        self.session.add(product)
        self.session.flush()
        return product

    def get_route(self, product_id: int) -> Optional[ProductRoute]:
        return self.session.scalar(
            select(ProductRoute).where(ProductRoute.product_id == product_id, ProductRoute.active.is_(True))
        )


class PrinterRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, printer_id: int) -> Optional[Printer]:
        return self.session.get(Printer, printer_id)

    def get_by_name(self, name: str) -> Optional[Printer]:
        return self.session.scalar(select(Printer).where(Printer.name == name))

    def list_enabled(self) -> Sequence[Printer]:
        return self.session.scalars(select(Printer).where(Printer.enabled.is_(True))).all()

    def upsert(self, name: str, type_: str, model: str, ip_address: str, port: int,
               configuration: dict | None = None) -> Printer:
        printer = self.get_by_name(name)
        if printer is None:
            printer = Printer(name=name, type=type_)
            self.session.add(printer)
        printer.model = model
        printer.ip_address = ip_address
        printer.port = port
        printer.enabled = True
        if configuration is not None:
            printer.configuration_json = json.dumps(configuration)
        self.session.flush()
        return printer

    def get_template(self, printer_type: str, version: str | None = None) -> Optional[PrinterTemplate]:
        stmt = select(PrinterTemplate).where(
            PrinterTemplate.printer_type == printer_type, PrinterTemplate.active.is_(True)
        )
        if version:
            stmt = stmt.where(PrinterTemplate.version == version)
        stmt = stmt.order_by(PrinterTemplate.id.desc())
        return self.session.scalar(stmt)


class JobRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, job_id: int) -> Optional[ProductionJob]:
        return self.session.get(ProductionJob, job_id)

    def get_by_job_number(self, job_number: str) -> Optional[ProductionJob]:
        return self.session.scalar(select(ProductionJob).where(ProductionJob.job_number == job_number))

    def create(self, job_number: str, product_id: int, requested_quantity: int,
               created_by: int | None) -> ProductionJob:
        job = ProductionJob(
            job_number=job_number,
            product_id=product_id,
            requested_quantity=requested_quantity,
            status=JobStatus.CREATED.value,
            created_by=created_by,
        )
        self.session.add(job)
        self.session.flush()
        return job

    def list_active(self) -> Sequence[ProductionJob]:
        active_states = [JobStatus.RUNNING.value, JobStatus.PAUSED.value, JobStatus.RECOVERING.value,
                          JobStatus.QUEUED.value, JobStatus.READY.value]
        return self.session.scalars(select(ProductionJob).where(ProductionJob.status.in_(active_states))).all()

    def list_history(self, limit: int = 200) -> Sequence[ProductionJob]:
        return self.session.scalars(
            select(ProductionJob).order_by(ProductionJob.created_at.desc()).limit(limit)
        ).all()

    def set_status(self, job: ProductionJob, status: JobStatus) -> None:
        job.status = status.value
        now = datetime.utcnow()
        if status == JobStatus.RUNNING and job.started_at is None:
            job.started_at = now
        if status == JobStatus.RUNNING:
            job.resumed_at = now
        if status == JobStatus.PAUSED:
            job.paused_at = now
        if status in (JobStatus.COMPLETED, JobStatus.STOPPED, JobStatus.FAILED, JobStatus.CANCELLED):
            job.completed_at = now
        self.session.flush()

    def recompute_counters(self, job: ProductionJob) -> None:
        """Derive counters from unit rows -- never trust in-memory increments (Section 56)."""
        completed_count = len(
            self.session.scalars(
                select(ProductionUnit.id).where(
                    ProductionUnit.job_id == job.id, ProductionUnit.overall_status == UnitStatus.COMPLETED.value
                )
            ).all()
        )
        failed_count = len(
            self.session.scalars(
                select(ProductionUnit.id).where(
                    ProductionUnit.job_id == job.id, ProductionUnit.overall_status == UnitStatus.FAILED.value
                )
            ).all()
        )
        job.completed_quantity = completed_count
        job.failed_quantity = failed_count
        self.session.flush()


class UnitRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, unit_id: int) -> Optional[ProductionUnit]:
        return self.session.get(ProductionUnit, unit_id)

    def get_by_serial(self, serial_number: str) -> Optional[ProductionUnit]:
        return self.session.scalar(select(ProductionUnit).where(ProductionUnit.serial_number == serial_number))

    def bulk_create(self, job_id: int, serials: Sequence[str], start_sequence: int = 1) -> list[ProductionUnit]:
        units = []
        for offset, serial in enumerate(serials):
            unit = ProductionUnit(
                job_id=job_id,
                sequence_number=start_sequence + offset,
                serial_number=serial,
                overall_status=UnitStatus.ALLOCATED.value,
                anser_status="",
                zebra_status="",
                verification_status="",
            )
            self.session.add(unit)
            units.append(unit)
        self.session.flush()
        return units

    def list_for_job(self, job_id: int) -> Sequence[ProductionUnit]:
        return self.session.scalars(
            select(ProductionUnit).where(ProductionUnit.job_id == job_id).order_by(ProductionUnit.sequence_number)
        ).all()

    def next_queued(self, job_id: int) -> Optional[ProductionUnit]:
        return self.session.scalar(
            select(ProductionUnit)
            .where(ProductionUnit.job_id == job_id, ProductionUnit.overall_status == UnitStatus.QUEUED.value)
            .order_by(ProductionUnit.sequence_number)
            .limit(1)
        )

    def next_anser_printed_awaiting_zebra(self, job_id: int) -> Optional[ProductionUnit]:
        return self.session.scalar(
            select(ProductionUnit)
            .where(ProductionUnit.job_id == job_id, ProductionUnit.overall_status == UnitStatus.ANSER_PRINTED.value)
            .order_by(ProductionUnit.sequence_number)
            .limit(1)
        )

    def in_flight_for_job(self, job_id: int) -> Sequence[ProductionUnit]:
        in_flight = [s.value for s in UNIT_IN_FLIGHT_STATES]
        return self.session.scalars(
            select(ProductionUnit).where(ProductionUnit.job_id == job_id, ProductionUnit.overall_status.in_(in_flight))
        ).all()

    def unknown_for_job(self, job_id: int) -> Sequence[ProductionUnit]:
        return self.session.scalars(
            select(ProductionUnit).where(
                ProductionUnit.job_id == job_id, ProductionUnit.overall_status == UnitStatus.UNKNOWN.value
            )
        ).all()

    def set_status(self, unit: ProductionUnit, status: UnitStatus) -> None:
        unit.overall_status = status.value
        self.session.flush()

    def exists_serial(self, serial_number: str) -> bool:
        return self.get_by_serial(serial_number) is not None


class SerialBatchRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_client_job_id(self, client_job_id: str) -> Optional[SerialBatch]:
        return self.session.scalar(select(SerialBatch).where(SerialBatch.client_job_id == client_job_id))

    def create(self, batch_id: str, job_id: int, client_job_id: str, quantity: int, source: str) -> SerialBatch:
        batch = SerialBatch(
            batch_id=batch_id, job_id=job_id, client_job_id=client_job_id, quantity=quantity, source=source
        )
        self.session.add(batch)
        self.session.flush()
        return batch


class PrintAttemptRepository:
    def __init__(self, session: Session):
        self.session = session

    def record(self, production_unit_id: int, printer_id: int | None, print_stage: str,
               attempt_number: int, status: str, error_code: str | None = None,
               error_message: str | None = None, request_payload_hash: str = "",
               completed: bool = True) -> PrintAttempt:
        attempt = PrintAttempt(
            production_unit_id=production_unit_id,
            printer_id=printer_id,
            print_stage=print_stage,
            attempt_number=attempt_number,
            request_payload_hash=request_payload_hash,
            status=status,
            error_code=error_code,
            error_message=error_message,
            completed_at=datetime.utcnow() if completed else None,
        )
        self.session.add(attempt)
        self.session.flush()
        return attempt

    def count_for_unit_stage(self, production_unit_id: int, print_stage: str) -> int:
        return len(
            self.session.scalars(
                select(PrintAttempt.id).where(
                    PrintAttempt.production_unit_id == production_unit_id,
                    PrintAttempt.print_stage == print_stage,
                )
            ).all()
        )


class PrinterEventRepository:
    def __init__(self, session: Session):
        self.session = session

    def record(self, printer_id: int, event_type: str, status: str, message: str = "",
               error_code: str | None = None) -> PrinterEvent:
        event = PrinterEvent(
            printer_id=printer_id, event_type=event_type, status=status, message=message, error_code=error_code
        )
        self.session.add(event)
        self.session.flush()
        return event

    def recent_for_printer(self, printer_id: int, limit: int = 50) -> Sequence[PrinterEvent]:
        return self.session.scalars(
            select(PrinterEvent)
            .where(PrinterEvent.printer_id == printer_id)
            .order_by(PrinterEvent.created_at.desc())
            .limit(limit)
        ).all()


class SystemEventRepository:
    def __init__(self, session: Session):
        self.session = session

    def record(self, event_type: str, message: str = "", details: dict | None = None) -> SystemEvent:
        event = SystemEvent(
            event_type=event_type, message=message, details_json=json.dumps(details or {})
        )
        self.session.add(event)
        self.session.flush()
        return event


class AuditLogRepository:
    def __init__(self, session: Session):
        self.session = session

    def record(self, user_id: int | None, action: str, entity_type: str = "", entity_id: str = "",
               details: str = "") -> AuditLog:
        entry = AuditLog(
            user_id=user_id, action=action, entity_type=entity_type, entity_id=entity_id, details=details
        )
        self.session.add(entry)
        self.session.flush()
        return entry

    def recent(self, limit: int = 200) -> Sequence[AuditLog]:
        return self.session.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()


class SettingsRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, key: str, default: str = "") -> str:
        setting = self.session.get(ApplicationSetting, key)
        return setting.value if setting else default

    def set(self, key: str, value: str) -> None:
        setting = self.session.get(ApplicationSetting, key)
        if setting is None:
            setting = ApplicationSetting(key=key, value=value)
            self.session.add(setting)
        else:
            setting.value = value
        self.session.flush()
