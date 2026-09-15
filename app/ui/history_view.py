"""Reporting (Section 68): daily production and printer summaries, computed
directly from the persistent tables -- there is no separate reporting store.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import func, select

from app.application.app_context import AppContext
from app.database.database import session_scope
from app.database.models import Printer, PrinterEvent, ProductionJob, Product
from app.domain.states import JobStatus


class HistoryViewWidget(QWidget):
    def __init__(self, context: AppContext, parent=None):
        super().__init__(parent)
        self.context = context

        layout = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.range_combo = QComboBox()
        self.range_combo.addItems(["Today", "Last 7 Days", "Last 30 Days"])
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)
        controls.addWidget(self.range_combo)
        controls.addWidget(refresh_button)
        layout.addLayout(controls)

        production_box = QGroupBox("Daily Production")
        production_layout = QVBoxLayout(production_box)
        self.production_table = QTableWidget(0, 5)
        self.production_table.setHorizontalHeaderLabels(
            ["Product", "Requested", "Completed", "Failed", "Jobs"]
        )
        self.production_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.production_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        production_layout.addWidget(self.production_table)
        layout.addWidget(production_box)

        job_box = QGroupBox("Job Details")
        job_layout = QVBoxLayout(job_box)
        job_filters = QHBoxLayout()
        self.product_filter = QComboBox()
        self.product_filter.addItem("All Products", None)
        self.status_filter = QComboBox()
        self.status_filter.addItem("All Statuses", None)
        for status in JobStatus:
            self.status_filter.addItem(status.value, status.value)
        self.product_filter.currentIndexChanged.connect(self.refresh)
        self.status_filter.currentIndexChanged.connect(self.refresh)
        job_filters.addWidget(self.product_filter)
        job_filters.addWidget(self.status_filter)
        job_layout.addLayout(job_filters)

        self.job_table = QTableWidget(0, 7)
        self.job_table.setHorizontalHeaderLabels(
            ["Job Number", "Product", "Status", "Requested", "Completed", "Failed", "Created"]
        )
        self.job_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.job_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        job_layout.addWidget(self.job_table)
        layout.addWidget(job_box)

        printer_box = QGroupBox("Printer Report")
        printer_layout = QVBoxLayout(printer_box)
        self.printer_table = QTableWidget(0, 2)
        self.printer_table.setHorizontalHeaderLabels(["Printer", "Fault Events"])
        self.printer_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.printer_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        printer_layout.addWidget(self.printer_table)
        layout.addWidget(printer_box)

        self.refresh()

    def _reload_product_filter(self, session) -> None:
        current = self.product_filter.currentData()
        products = session.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.product_name)).all()
        self.product_filter.blockSignals(True)
        self.product_filter.clear()
        self.product_filter.addItem("All Products", None)
        for product in products:
            self.product_filter.addItem(product.product_name, product.id)
        index = self.product_filter.findData(current)
        self.product_filter.setCurrentIndex(index if index >= 0 else 0)
        self.product_filter.blockSignals(False)

    def _since(self) -> datetime:
        choice = self.range_combo.currentText()
        if choice == "Today":
            return datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        if choice == "Last 7 Days":
            return datetime.utcnow() - timedelta(days=7)
        return datetime.utcnow() - timedelta(days=30)

    def refresh(self) -> None:
        since = self._since()
        with session_scope() as session:
            self._reload_product_filter(session)
            rows = session.execute(
                select(
                    Product.product_name,
                    func.sum(ProductionJob.requested_quantity),
                    func.sum(ProductionJob.completed_quantity),
                    func.sum(ProductionJob.failed_quantity),
                    func.count(ProductionJob.id),
                )
                .join(Product, Product.id == ProductionJob.product_id)
                .where(ProductionJob.created_at >= since)
                .group_by(Product.product_name)
            ).all()

            self.production_table.setRowCount(len(rows))
            for row_idx, (name, requested, completed, failed, job_count) in enumerate(rows):
                for col, value in enumerate([name, requested or 0, completed or 0, failed or 0, job_count]):
                    self.production_table.setItem(row_idx, col, QTableWidgetItem(str(value)))

            product_id = self.product_filter.currentData()
            status_value = self.status_filter.currentData()
            jobs_query = (
                select(ProductionJob)
                .join(Product, Product.id == ProductionJob.product_id)
                .where(ProductionJob.created_at >= since)
                .order_by(ProductionJob.created_at.desc())
            )
            if product_id is not None:
                jobs_query = jobs_query.where(ProductionJob.product_id == product_id)
            if status_value is not None:
                jobs_query = jobs_query.where(ProductionJob.status == status_value)
            jobs = session.execute(jobs_query.limit(200)).scalars().all()
            self.job_table.setRowCount(len(jobs))
            for row_idx, job in enumerate(jobs):
                product_name = session.get(Product, job.product_id)
                values = [
                    job.job_number,
                    product_name.product_name if product_name else "-",
                    job.status,
                    str(job.requested_quantity),
                    str(job.completed_quantity),
                    str(job.failed_quantity),
                    job.created_at.isoformat(sep=" ", timespec="seconds") if job.created_at else "-",
                ]
                for col, value in enumerate(values):
                    self.job_table.setItem(row_idx, col, QTableWidgetItem(str(value)))

            printer_rows = session.execute(
                select(Printer.name, func.count(PrinterEvent.id))
                .join(PrinterEvent, PrinterEvent.printer_id == Printer.id)
                .where(PrinterEvent.created_at >= since, PrinterEvent.event_type == "STATUS_CHANGE")
                .group_by(Printer.name)
            ).all()
            self.printer_table.setRowCount(len(printer_rows))
            for row_idx, (name, count) in enumerate(printer_rows):
                self.printer_table.setItem(row_idx, 0, QTableWidgetItem(name))
                self.printer_table.setItem(row_idx, 1, QTableWidgetItem(str(count)))
