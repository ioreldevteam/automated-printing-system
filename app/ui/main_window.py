"""Main application window (Section 8/9): tab navigation across the
dashboard, production control, printers, job history, and settings. Wires
EventBus notifications (via EventBridge) to recovery/error dialogs.
"""
from __future__ import annotations

from PySide6.QtWidgets import QMainWindow, QMessageBox, QTabWidget

from app.application.app_context import AppContext
from app.application.printer_service import PrinterService
from app.application.recovery_service import RecoveryService
from app.database.database import session_scope
from app.database.models import User
from app.domain.states import Role
from app.ui.dashboard import DashboardWidget
from app.ui.event_bridge import EventBridge
from app.ui.history_view import HistoryViewWidget
from app.ui.jobs_view import JobsViewWidget
from app.ui.printer_view import PrinterViewWidget
from app.ui.production_view import ProductionViewWidget
from app.ui.settings_view import SettingsViewWidget


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext, current_user: User):
        super().__init__()
        self.context = context
        self.current_user = current_user
        self.setWindowTitle(f"{context.config.application.name} - {current_user.username} ({current_user.role})")
        self.resize(1000, 700)

        self.dashboard = DashboardWidget(context)
        self.production_view = ProductionViewWidget(context, current_user)
        self.production_view.job_started.connect(self.dashboard.set_active_job)
        self.printer_view = PrinterViewWidget(context, Role(current_user.role))
        self.jobs_view = JobsViewWidget(context)
        self.history_view = HistoryViewWidget(context)
        self.settings_view = SettingsViewWidget(context, current_user)

        tabs = QTabWidget()
        tabs.addTab(self.dashboard, "Dashboard")
        tabs.addTab(self.production_view, "Production")
        tabs.addTab(self.printer_view, "Printers")
        tabs.addTab(self.jobs_view, "Jobs")
        tabs.addTab(self.history_view, "History")
        tabs.addTab(self.settings_view, "Settings")
        self.setCentralWidget(tabs)

        self.event_bridge = EventBridge(context.event_bus, self)
        self.event_bridge.event_received.connect(self._on_event)

    def _on_event(self, event_type: str, payload: dict) -> None:
        if event_type == "RECOVERY_REQUIRED":
            self._show_recovery_dialog(payload.get("job_id"))
        elif event_type == "JOB_COMPLETED":
            QMessageBox.information(self, "Job Completed", "The production job has completed.")

    def _show_recovery_dialog(self, job_id: int | None) -> None:
        if job_id is None:
            return
        from app.ui.dialogs.recovery_dialog import RecoveryDialog

        with session_scope() as session:
            summary = RecoveryService(session, self.context.printer_manager).build_summary(job_id)

        dialog = RecoveryDialog(summary, self.context.printer_monitor.printer_service,
                                 self.context.production_controller.zebra_printer_name, self)
        dialog.exec()
        if dialog.decision == "resume":
            self.context.production_controller.resume_job(job_id, self.current_user.id)
        elif dialog.decision == "cancel":
            self.context.production_controller.stop_job(job_id, self.current_user.id)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.context.printer_monitor.stop()
        self.context.production_controller.shutdown()
        super().closeEvent(event)
