"""Job list (recent and active jobs)."""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.application.app_context import AppContext
from app.database.database import session_scope
from app.database.repositories import JobRepository


class JobsViewWidget(QWidget):
    COLUMNS = ["Job Number", "Status", "Requested", "Completed", "Failed", "Started"]

    def __init__(self, context: AppContext, parent=None):
        super().__init__(parent)
        self.context = context

        layout = QVBoxLayout(self)
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
            jobs = JobRepository(session).list_history(limit=100)
            self.table.setRowCount(len(jobs))
            for row, job in enumerate(jobs):
                values = [
                    job.job_number, job.status, str(job.requested_quantity),
                    str(job.completed_quantity), str(job.failed_quantity),
                    job.started_at.isoformat(sep=" ", timespec="seconds") if job.started_at else "-",
                ]
                for col, value in enumerate(values):
                    self.table.setItem(row, col, QTableWidgetItem(value))
