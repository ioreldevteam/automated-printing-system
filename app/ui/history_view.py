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

        printer_box = QGroupBox("Printer Report")
        printer_layout = QVBoxLayout(printer_box)
        self.printer_table = QTableWidget(0, 2)
        self.printer_table.setHorizontalHeaderLabels(["Printer", "Fault Events"])
        self.printer_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.printer_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        printer_layout.addWidget(self.printer_table)
        layout.addWidget(printer_box)

        self.refresh()

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
