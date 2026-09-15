"""Printer dashboard (Section 48). Read-only status view; the printer test
dialog (Section 75) is reached from here for operators with permission.
"""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel, QPushButton, QVBoxLayout, QWidget

from app.application.app_context import AppContext
from app.domain.states import Role, role_can


class PrinterViewWidget(QWidget):
    def __init__(self, context: AppContext, user_role: Role, parent=None):
        super().__init__(parent)
        self.context = context

        layout = QVBoxLayout(self)
        self.cards: dict[str, dict[str, QLabel]] = {}

        grid_box = QGroupBox("Printers")
        grid = QGridLayout(grid_box)
        for row, name in enumerate(context.printer_manager.names()):
            cfg = context.printer_manager.config_for(name)
            name_label = QLabel(f"{name} ({cfg.type} - {cfg.model or 'unknown model'})")
            status_label = QLabel("Status: UNKNOWN")
            connection_label = QLabel("Connection: UNKNOWN")
            fault_label = QLabel("Fault: NONE")
            grid.addWidget(name_label, row, 0)
            grid.addWidget(status_label, row, 1)
            grid.addWidget(connection_label, row, 2)
            grid.addWidget(fault_label, row, 3)
            self.cards[name] = {
                "status": status_label, "connection": connection_label, "fault": fault_label,
            }
        configured_names = set(context.printer_manager.names())
        for row, printer in enumerate(context.discovered_printers or [], start=len(self.cards)):
            if printer.name in configured_names:
                continue
            details = printer.uri or "No device URI"
            name_label = QLabel(f"{printer.name} (Detected - {printer.model or 'unknown model'})")
            status_label = QLabel("Status: DETECTED")
            connection_label = QLabel(f"Source: {printer.source} | {details}")
            fault_label = QLabel("Configuration: REQUIRED for production")
            grid.addWidget(name_label, row, 0)
            grid.addWidget(status_label, row, 1)
            grid.addWidget(connection_label, row, 2)
            grid.addWidget(fault_label, row, 3)
        layout.addWidget(grid_box)

        if role_can(user_role, "test_printer"):
            test_button = QPushButton("Open Printer Test")
            test_button.clicked.connect(self._open_test_dialog)
            layout.addWidget(test_button)

        layout.addStretch()

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def refresh(self) -> None:
        for name, labels in self.cards.items():
            status = self.context.printer_monitor.printer_service.last_known_status(name)
            if status is None:
                labels["status"].setText("Status: UNKNOWN")
                labels["connection"].setText("Connection: UNKNOWN")
                labels["fault"].setText("Fault: NONE")
                continue
            labels["status"].setText(f"Status: {status.value}")
            from app.domain.states import MANUAL_RECOVERY_PRINTER_STATES, PrinterStatus
            connected = status != PrinterStatus.OFFLINE
            labels["connection"].setText(f"Connection: {'ONLINE' if connected else 'OFFLINE'}")
            fault = status.value if status in MANUAL_RECOVERY_PRINTER_STATES else "NONE"
            labels["fault"].setText(f"Fault: {fault}")

    def _open_test_dialog(self) -> None:
        from app.ui.dialogs.printer_test_dialog import PrinterTestDialog
        dialog = PrinterTestDialog(self.context.printer_manager, self.context.printer_monitor.printer_service, self)
        dialog.exec()
