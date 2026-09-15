"""Main production dashboard (Section 47). Counters are always re-derived
from the database on each refresh tick -- never incremented in memory
(Section 56).
"""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel, QProgressBar, QVBoxLayout, QWidget

from app.application.app_context import AppContext
from app.database.database import session_scope
from app.database.repositories import JobRepository, ProductRepository


class DashboardWidget(QWidget):
    def __init__(self, context: AppContext, parent=None):
        super().__init__(parent)
        self.context = context
        self.current_job_id: int | None = None

        layout = QVBoxLayout(self)
        header = QGroupBox("Production Control")
        header_layout = QGridLayout(header)

        self.product_label = QLabel("Product: -")
        self.job_label = QLabel("Job: -")
        self.quantity_label = QLabel("Quantity: -")
        self.progress_bar = QProgressBar()
        self.counts_label = QLabel("Completed: 0    Failed: 0    Remaining: 0")
        self.serial_label = QLabel("Current Serial: -")

        header_layout.addWidget(self.product_label, 0, 0)
        header_layout.addWidget(self.job_label, 0, 1)
        header_layout.addWidget(self.quantity_label, 1, 0)
        header_layout.addWidget(self.progress_bar, 2, 0, 1, 2)
        header_layout.addWidget(self.counts_label, 3, 0, 1, 2)
        header_layout.addWidget(self.serial_label, 4, 0, 1, 2)
        layout.addWidget(header)

        printers_box = QGroupBox("Printers")
        self.printers_layout = QGridLayout(printers_box)
        self.printer_status_labels: dict[str, QLabel] = {}
        for col, name in enumerate(context.printer_manager.names()):
            label = QLabel(f"{name}\n(unknown)")
            self.printer_status_labels[name] = label
            self.printers_layout.addWidget(label, 0, col)
        layout.addWidget(printers_box)

        layout.addStretch()

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def set_active_job(self, job_id: int | None) -> None:
        self.current_job_id = job_id
        self.refresh()

    def refresh(self) -> None:
        if self.current_job_id is not None:
            with session_scope() as session:
                job = JobRepository(session).get(self.current_job_id)
                if job is not None:
                    product = ProductRepository(session).get(job.product_id)
                    self.product_label.setText(f"Product: {product.product_name if product else '-'}")
                    self.job_label.setText(f"Job: {job.job_number}")
                    self.quantity_label.setText(f"Quantity: {job.requested_quantity}")
                    total = job.requested_quantity or 1
                    self.progress_bar.setMaximum(total)
                    self.progress_bar.setValue(job.completed_quantity)
                    remaining = job.requested_quantity - job.completed_quantity - job.failed_quantity
                    self.counts_label.setText(
                        f"Completed: {job.completed_quantity}    Failed: {job.failed_quantity}    "
                        f"Remaining: {max(remaining, 0)}"
                    )
                    from app.database.repositories import UnitRepository
                    from app.domain.states import UnitStatus
                    units = UnitRepository(session).list_for_job(job.id)
                    current = next(
                        (u.serial_number for u in units
                         if u.overall_status not in (UnitStatus.COMPLETED.value, UnitStatus.ALLOCATED.value)),
                        None,
                    )
                    self.serial_label.setText(f"Current Serial: {current or '-'}")

        # Read the background monitor's cached status only -- calling a
        # printer adapter's get_status() here would block the UI thread on
        # network I/O (Section 46).
        for name, label in self.printer_status_labels.items():
            status = self.context.printer_monitor.printer_service.last_known_status(name)
            label.setText(f"{name}\n{status.value if status else 'UNKNOWN'}")
