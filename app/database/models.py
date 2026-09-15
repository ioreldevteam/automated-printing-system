"""SQLAlchemy ORM models. Table list matches Section 13; column lists match
Sections 14-21 with the additions from Sections 92-93 (product routing) and
Section 67 (job snapshot) needed to make those sections actually persistable.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    product_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)


class Printer(Base):
    __tablename__ = "printers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # ANSER | ZEBRA | SIMULATION
    model: Mapped[str] = mapped_column(String(64), default="")
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    port: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    location: Mapped[str] = mapped_column(String(128), default="")
    configuration_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)


class PrinterTemplate(Base):
    __tablename__ = "printer_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    printer_type: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("name", "version", name="uq_template_name_version"),)


class ProductRoute(Base):
    """Section 92-93: repeatable production recipes per product."""

    __tablename__ = "product_routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    anser_printer_id: Mapped[int | None] = mapped_column(ForeignKey("printers.id"), nullable=True)
    zebra_printer_id: Mapped[int | None] = mapped_column(ForeignKey("printers.id"), nullable=True)
    anser_template_id: Mapped[int | None] = mapped_column(ForeignKey("printer_templates.id"), nullable=True)
    zebra_template_id: Mapped[int | None] = mapped_column(ForeignKey("printer_templates.id"), nullable=True)
    verification_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ProductionJob(Base):
    __tablename__ = "production_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)

    requested_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    allocated_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Section 67: production job snapshot, captured at start so history survives
    # later template/printer configuration changes.
    anser_printer_id: Mapped[int | None] = mapped_column(ForeignKey("printers.id"), nullable=True)
    zebra_printer_id: Mapped[int | None] = mapped_column(ForeignKey("printers.id"), nullable=True)
    anser_template_version: Mapped[str] = mapped_column(String(32), default="")
    zebra_template_version: Mapped[str] = mapped_column(String(32), default="")
    serial_batch_id: Mapped[str] = mapped_column(String(64), default="")

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    units: Mapped[list["ProductionUnit"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class ProductionUnit(Base):
    __tablename__ = "production_units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("production_jobs.id"), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    serial_number: Mapped[str] = mapped_column(String(64), nullable=False)

    anser_status: Mapped[str] = mapped_column(String(32), default="")
    anser_printed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    zebra_status: Mapped[str] = mapped_column(String(32), default="")
    zebra_printed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    verification_status: Mapped[str] = mapped_column(String(32), default="")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    overall_status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    job: Mapped["ProductionJob"] = relationship(back_populates="units")

    __table_args__ = (
        UniqueConstraint("job_id", "sequence_number", name="uq_unit_job_sequence"),
        UniqueConstraint("serial_number", name="uq_unit_serial_number"),
    )


class SerialBatch(Base):
    __tablename__ = "serial_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    job_id: Mapped[int] = mapped_column(ForeignKey("production_jobs.id"), nullable=False)
    client_job_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="local")  # local | remote
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class PrintAttempt(Base):
    __tablename__ = "print_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    production_unit_id: Mapped[int] = mapped_column(ForeignKey("production_units.id"), nullable=False)
    printer_id: Mapped[int | None] = mapped_column(ForeignKey("printers.id"), nullable=True)
    print_stage: Mapped[str] = mapped_column(String(16), nullable=False)  # ANSER | ZEBRA

    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    request_payload_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # SUCCESS | FAILED | UNKNOWN

    error_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PrinterEvent(Base):
    __tablename__ = "printer_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    printer_id: Mapped[int] = mapped_column(ForeignKey("printers.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class SystemEvent(Base):
    __tablename__ = "system_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, default="")
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), default="")
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class ApplicationSetting(Base):
    __tablename__ = "application_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)
