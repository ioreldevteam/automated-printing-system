"""Job list (recent and active jobs)."""
from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import select

from app.application.app_context import AppContext
from app.database.database import session_scope
from app.database.models import Product
from app.database.repositories import JobRepository
from app.domain.states import JobStatus


class JobsViewWidget(QWidget):
    COLUMNS = ["Job Number", "Product", "Status", "Requested", "Completed", "Failed", "Started"]

    def __init__(self, context: AppContext, parent=None):
        super().__init__(parent)
        self.context = context

        layout = QVBoxLayout(self)
        filter_box = QGroupBox("Job Filters")
        filters = QFormLayout(filter_box)
        self.range_combo = QComboBox()
        self.range_combo.addItems(["All Time", "Today", "Last 7 Days", "Last 30 Days"])
        self.status_combo = QComboBox()
        self.status_combo.addItem("All Statuses", None)
        for status in JobStatus:
            self.status_combo.addItem(status.value, status.value)
        self.product_combo = QComboBox()
        self.product_combo.addItem("All Products", None)
        with session_scope() as session:
            products = session.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.product_name)).all()
            for product in products:
                self.product_combo.addItem(product.product_name, product.id)
        for control in (self.range_combo, self.status_combo, self.product_combo):
            control.currentIndexChanged.connect(self.refresh)
        filters.addRow("Date", self.range_combo)
        filters.addRow("Status", self.status_combo)
        filters.addRow("Product", self.product_combo)
        layout.addWidget(filter_box)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def refresh(self) -> None:
        with session_scope() as session:
            jobs = JobRepository(session).list_history(limit=200)
            if self.range_combo.currentText() != "All Time":
                since = datetime.utcnow()
                if self.range_combo.currentText() == "Today":
                    since = since.replace(hour=0, minute=0, second=0, microsecond=0)
                elif self.range_combo.currentText() == "Last 7 Days":
                    since -= timedelta(days=7)
                else:
                    since -= timedelta(days=30)
                jobs = [job for job in jobs if job.created_at >= since]
            selected_status = self.status_combo.currentData()
            if selected_status is not None:
                jobs = [job for job in jobs if job.status == selected_status]
            selected_product = self.product_combo.currentData()
            if selected_product is not None:
                jobs = [job for job in jobs if job.product_id == selected_product]

            self.table.setRowCount(len(jobs))
            for row, job in enumerate(jobs):
                product = session.get(Product, job.product_id)
                values = [
                    job.job_number,
                    product.product_name if product else "-",
                    job.status,
                    str(job.requested_quantity),
                    str(job.completed_quantity),
                    str(job.failed_quantity),
                    job.started_at.isoformat(sep=" ", timespec="seconds") if job.started_at else "-",
                ]
                for col, value in enumerate(values):
                    self.table.setItem(row, col, QTableWidgetItem(str(value)))
