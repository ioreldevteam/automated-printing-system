"""Plain value objects shared across layers (not ORM entities — see database/models.py)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.domain.states import PrinterStatus


@dataclass
class PrinterStatusInfo:
    """Normalized printer status (Section 34) independent of vendor protocol."""

    status: PrinterStatus
    connected: bool
    raw_state: str = ""
    detail: str = ""
    fault_code: Optional[str] = None
    read_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class LabelData:
    product_name: str
    serial_number: str
    batch_number: str = ""
    date: str = ""
    expiry_date: str = ""
    extra: dict = field(default_factory=dict)

    def as_substitution_map(self) -> dict:
        merged = {
            "PRODUCT_NAME": self.product_name,
            "SERIAL_NUMBER": self.serial_number,
            "BATCH_NUMBER": self.batch_number,
            "DATE": self.date,
            "EXPIRY_DATE": self.expiry_date,
        }
        merged.update(self.extra)
        return merged


@dataclass
class SerialAllocationResult:
    serial_batch_id: str
    job_number: str
    quantity: int
    serials: list[str]


@dataclass
class ReconciliationResult:
    """Outcome of Section 40's reconciliation process for one UNKNOWN unit."""

    unit_id: int
    serial_number: str
    outcome: str  # "COMPLETED" | "RETRY" | "OPERATOR_DECISION"
    reason: str
