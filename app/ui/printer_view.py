"""Printer dashboard (Section 48). Read-only status view; the printer test
dialog (Section 75) is reached from here for operators with permission.

Also owns live printer discovery: printers connected to the host (USB or
network, via CUPS) are detected at startup and are re-detected on a timer
(and on demand via the Rescan button) so the operator doesn't have to
restart the application to use a printer that was plugged in later.
"""
from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from app.application.app_context import AppContext, rescan_discovered_printers
from app.domain.states import Role, role_can

# How often to silently re-check the host print system for newly connected
# printers. A manual "Rescan Now" click bypasses this interval entirely.
AUTO_RESCAN_INTERVAL_MS = 15_000


class PrinterViewWidget(QWidget):
    def __init__(self, context: AppContext, user_role: Role, parent=None):
        super().__init__(parent)
        self.context = context
        self.user_role = user_role
        self.cards: dict[str, dict[str, QLabel]] = {}

        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        header.addWidget(QLabel("<b>Printers</b>"))
        header.addStretch()
        self.rescan_button = QPushButton("Rescan for Printers")
        self.rescan_button.setToolTip(
            "Re-check the host print system for newly connected USB or network printers."
        )
        self.rescan_button.clicked.connect(self._rescan_now)
        header.addWidget(self.rescan_button)
        layout.addLayout(header)

        self.grid_box = QGroupBox("Detected & Configured Printers")
        layout.addWidget(self.grid_box)
        self._build_grid()

        if role_can(user_role, "test_printer"):
            test_button = QPushButton("Open Printer Test")
            test_button.clicked.connect(self._open_test_dialog)
            layout.addWidget(test_button)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        layout.addStretch()

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()

        self.rescan_timer = QTimer(self)
        self.rescan_timer.setInterval(AUTO_RESCAN_INTERVAL_MS)
        self.rescan_timer.timeout.connect(lambda: self._rescan_now(silent=True))
        self.rescan_timer.start()

    def _build_grid(self) -> None:
        """(Re)build the printer grid from the current printer manager state
        plus any detected-but-not-configured printers. Safe to call repeatedly
        after a rescan -- old widgets are discarded and recreated."""
        old_layout = self.grid_box.layout()
        if old_layout is not None:
            while old_layout.count():
                item = old_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
            QWidget().setLayout(old_layout)  # detach so a fresh layout can be set

        grid = QGridLayout(self.grid_box)
        self.cards = {}

        row = 0
        for name in self.context.printer_manager.names():
            cfg = self.context.printer_manager.config_for(name)
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
            row += 1

        configured_names = set(self.context.printer_manager.names())
        for printer in self.context.discovered_printers or []:
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
            row += 1

        if row == 0:
            grid.addWidget(QLabel("No printers detected yet. Connect a printer and click Rescan."), 0, 0)

        self.refresh()

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

    def _rescan_now(self, silent: bool = False) -> None:
        if not silent:
            self.rescan_button.setEnabled(False)
            self.rescan_button.setText("Rescanning...")
        try:
            newly_added = rescan_discovered_printers(self.context)
        except Exception as exc:  # noqa: BLE001 - never let a rescan crash the UI
            if not silent:
                self.status_label.setText(f"Rescan failed: {exc}")
            return
        finally:
            if not silent:
                self.rescan_button.setEnabled(True)
                self.rescan_button.setText("Rescan for Printers")

        if newly_added:
            self._build_grid()
            self.status_label.setText(f"Found and connected new printer(s): {', '.join(newly_added)}")
        elif not silent:
            self.status_label.setText("No new printers found.")

    def _open_test_dialog(self) -> None:
        from app.ui.dialogs.printer_test_dialog import PrinterTestDialog
        dialog = PrinterTestDialog(self.context.printer_manager, self.context.printer_monitor.printer_service, self)
        dialog.exec()
