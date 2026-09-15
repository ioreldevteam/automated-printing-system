"""Standalone printer test mode (Section 75), usable without a production job.

Also exposes fault injection when the selected printer is a
SimulationPrinter (Section 76/77) -- there is no real hardware fault switch
to flip in a demo/dev environment, so this is the supported way to see the
pause -> RecoveryDialog -> resume flow (Section 36/50) without physical
printers.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from app.application.printer_service import PrinterService
from app.printers.printer_manager import PrinterManager
from app.printers.simulation import SimulationPrinter

FAILURE_MODES = ["media_out", "offline", "timeout", "busy", "unknown_result"]


class PrinterTestDialog(QDialog):
    def __init__(self, printer_manager: PrinterManager, printer_service: PrinterService, parent=None):
        super().__init__(parent)
        self.printer_manager = printer_manager
        self.printer_service = printer_service
        self.setWindowTitle("Printer Test")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        for name in printer_manager.names():
            self.list_widget.addItem(QListWidgetItem(name))
        layout.addWidget(self.list_widget)

        self.result_label = QLabel("")
        layout.addWidget(self.result_label)

        buttons = QHBoxLayout()
        connect_button = QPushButton("Test Connection")
        connect_button.clicked.connect(self._test_connection)
        status_button = QPushButton("Read Status")
        status_button.clicked.connect(self._read_status)
        print_button = QPushButton("Test Print")
        print_button.clicked.connect(self._test_print)
        buttons.addWidget(connect_button)
        buttons.addWidget(status_button)
        buttons.addWidget(print_button)
        layout.addLayout(buttons)

        fault_row = QHBoxLayout()
        self.fault_combo = QComboBox()
        self.fault_combo.addItems(FAILURE_MODES)
        inject_button = QPushButton("Simulate Fault on Next Print")
        inject_button.clicked.connect(self._inject_fault)
        clear_button = QPushButton("Clear Simulated Faults")
        clear_button.clicked.connect(self._clear_faults)
        fault_row.addWidget(self.fault_combo)
        fault_row.addWidget(inject_button)
        fault_row.addWidget(clear_button)
        layout.addLayout(fault_row)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

    def _selected_name(self) -> str | None:
        item = self.list_widget.currentItem()
        return item.text() if item else None

    def _test_connection(self) -> None:
        name = self._selected_name()
        if not name:
            return
        try:
            self.printer_manager.get(name).connect()
            self.result_label.setText(f"{name}: Connected")
        except Exception as exc:  # noqa: BLE001
            self.result_label.setText(f"{name}: Connection failed ({exc})")

    def _read_status(self) -> None:
        name = self._selected_name()
        if not name:
            return
        info = self.printer_manager.get(name).get_status()
        self.result_label.setText(f"{name}: {info.status.value} (connected={info.connected}) {info.detail}")

    def _test_print(self) -> None:
        name = self._selected_name()
        if not name:
            return
        ok = self.printer_service.test_printer(name)
        self.result_label.setText(f"{name}: Test print {'succeeded' if ok else 'failed'}")

    def _inject_fault(self) -> None:
        name = self._selected_name()
        if not name:
            return
        printer = self.printer_manager.get(name)
        if not isinstance(printer, SimulationPrinter):
            self.result_label.setText(f"{name}: not a simulated printer, cannot inject a fault")
            return
        mode = self.fault_combo.currentText()
        printer.inject_failure(mode)
        self.result_label.setText(
            f"{name}: will fail with '{mode}' on its next print during a running job."
        )

    def _clear_faults(self) -> None:
        name = self._selected_name()
        if not name:
            return
        printer = self.printer_manager.get(name)
        if isinstance(printer, SimulationPrinter):
            printer.clear_failures()
            self.result_label.setText(f"{name}: simulated faults cleared")
