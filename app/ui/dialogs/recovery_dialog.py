"""Recovery screen (Section 36/50). Shown whenever production pauses --
either from a live printer fault or from an application-restart reconciliation
scan. Actions: test the printer, retry the current unit, resume, or cancel.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from app.application.printer_service import PrinterService
from app.application.recovery_service import RecoverySummary


class RecoveryDialog(QDialog):
    def __init__(self, summary: RecoverySummary, printer_service: PrinterService, printer_name: str,
                 parent=None):
        super().__init__(parent)
        self.summary = summary
        self.printer_service = printer_service
        self.printer_name = printer_name
        self.decision: str | None = None  # "resume" | "cancel"

        self.setWindowTitle("Production Paused")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)

        layout.addWidget(self._title_label("PRODUCTION PAUSED"))
        layout.addWidget(QLabel(f"Job: {summary.job_number}"))
        layout.addWidget(QLabel(f"Completed: {summary.completed}    Failed: {summary.failed}    "
                                 f"Remaining: {summary.remaining}"))
        if summary.current_serial:
            layout.addWidget(QLabel(f"Current Unit: {summary.current_serial}"))

        if summary.needs_operator_review:
            layout.addWidget(self._title_label("Needs Your Decision"))
            self.review_list = QListWidget()
            for result in summary.needs_operator_review:
                item = QListWidgetItem(f"{result.serial_number}: {result.reason}")
                item.setData(Qt.ItemDataRole.UserRole, result.unit_id)
                self.review_list.addItem(item)
            layout.addWidget(self.review_list)

            review_buttons = QHBoxLayout()
            printed_button = QPushButton("Mark Selected as Printed")
            printed_button.clicked.connect(lambda: self._apply_decision("printed"))
            not_printed_button = QPushButton("Mark Selected as Not Printed")
            not_printed_button.clicked.connect(lambda: self._apply_decision("not_printed"))
            review_buttons.addWidget(printed_button)
            review_buttons.addWidget(not_printed_button)
            layout.addLayout(review_buttons)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        action_buttons = QHBoxLayout()
        test_button = QPushButton("TEST PRINTER")
        test_button.clicked.connect(self._test_printer)
        resume_button = QPushButton("RESUME")
        resume_button.clicked.connect(self._resume)
        cancel_button = QPushButton("CANCEL JOB")
        cancel_button.clicked.connect(self._cancel)
        action_buttons.addWidget(test_button)
        action_buttons.addWidget(resume_button)
        action_buttons.addWidget(cancel_button)
        layout.addLayout(action_buttons)

    @staticmethod
    def _title_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-weight: bold;")
        return label

    def _apply_decision(self, decision: str) -> None:
        from app.database.database import session_scope
        from app.application.recovery_service import RecoveryService

        item = self.review_list.currentItem()
        if item is None:
            return
        unit_id = item.data(Qt.ItemDataRole.UserRole)
        with session_scope() as session:
            RecoveryService(session).apply_decision(unit_id, decision)
        self.review_list.takeItem(self.review_list.row(item))
        self.status_label.setText(f"Recorded decision for unit.")

    def _test_printer(self) -> None:
        ok = self.printer_service.test_printer(self.printer_name)
        self.status_label.setText("Printer test: OK" if ok else "Printer test: FAILED")

    def _resume(self) -> None:
        self.decision = "resume"
        self.accept()

    def _cancel(self) -> None:
        self.decision = "cancel"
        self.accept()
