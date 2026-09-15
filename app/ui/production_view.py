"""Production job creation and control. The home screen opens with a
job-first workflow: create the job, review the available printer cards, then
show the generated box-by-box production sections for the active job.
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.application.app_context import AppContext
from app.application.job_service import JobService
from app.application.serial_service import SerialService
from app.database.database import session_scope
from app.database.models import User
from app.database.repositories import JobRepository, PrinterRepository, ProductRepository
from app.domain.exceptions import ProductionError
from app.domain.states import Role, role_can
from app.ui.dashboard import DashboardWidget


class ProductionViewWidget(QWidget):
    job_started = Signal(int)  # job_id

    def __init__(self, context: AppContext, current_user: User, parent=None):
        super().__init__(parent)
        self.context = context
        self.current_user = current_user
        self.active_job_id: int | None = None
        self._box_cards: dict[str, dict[str, Any]] = {}
        self._printer_cards: dict[str, dict[str, Any]] = {}

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        top_row.addStretch()
        self.new_job_button = QPushButton("New Job")
        self.new_job_button.setVisible(False)
        self.new_job_button.clicked.connect(self._show_new_job_form)
        top_row.addWidget(self.new_job_button)
        layout.addLayout(top_row)

        self.dashboard = DashboardWidget(context, self)
        self.dashboard.hide()

        self.form_box = QGroupBox("New Production Job")
        form = QFormLayout(self.form_box)
        self.product_combo = QComboBox()
        self._reload_products()
        self.quantity_spin = QSpinBox()
        self.quantity_spin.setRange(1, 1_000_000)
        self.quantity_spin.setValue(3000)
        form.addRow("Item", self.product_combo)
        form.addRow("Quantity", self.quantity_spin)

        self.create_button = QPushButton("Create Job")
        self.create_button.clicked.connect(self._create_job)
        self.create_button.setEnabled(role_can(Role(current_user.role), "create_job"))
        form.addRow(self.create_button)
        layout.addWidget(self.form_box)

        self.preview_box = QGroupBox("Job Preview")
        self.preview_layout = QFormLayout(self.preview_box)
        self.preview_job = QLabel("-")
        self.preview_product = QLabel("-")
        self.preview_count = QLabel("-")
        self.preview_layout.addRow("Job ID", self.preview_job)
        self.preview_layout.addRow("Product", self.preview_product)
        self.preview_layout.addRow("Count", self.preview_count)
        self.preview_box.hide()
        layout.addWidget(self.preview_box)

        self.sections_box = QGroupBox("Production Sections")
        self.sections_layout = QVBoxLayout(self.sections_box)
        self.sections_box.hide()
        layout.addWidget(self.sections_box)

        self.start_button = QPushButton("START")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self._start_job)
        layout.addWidget(self.start_button)

        self.printer_box = QGroupBox("Printer Section")
        self.printer_grid = QGridLayout(self.printer_box)
        self._build_printer_cards()
        layout.addWidget(self.printer_box)

        self.status_label = QLabel("No active job.")
        self.status_label.hide()
        layout.addWidget(self.status_label)
        layout.addStretch()

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._refresh_printer_cards)
        self.timer.start()

    def _reload_products(self) -> None:
        self.product_combo.clear()
        with session_scope() as session:
            for product in ProductRepository(session).list_active():
                self.product_combo.addItem(f"{product.product_code} - {product.product_name}", product.product_code)

    def _mask_serial(self, raw: str) -> str:
        text = (raw or "").strip()
        if len(text) <= 6:
            return text
        return f"{text[:3]}***{text[-3:]}"

    def _default_printers(self) -> tuple[str | None, str | None]:
        anser = next(
            (name for name in self.context.printer_manager.names()
             if self.context.printer_manager.config_for(name).type == "ANSER"),
            None,
        )
        label = next(
            (name for name in self.context.printer_manager.names()
             if self.context.printer_manager.config_for(name).type in ("ZEBRA", "CUPS")),
            None,
        )
        return anser, label

    def _build_printer_cards(self) -> None:
        for name in list(self._printer_cards):
            widget = self._printer_cards[name]["widget"]
            self.printer_grid.removeWidget(widget)
            widget.deleteLater()
        self._printer_cards.clear()

        printer_names = list(self.context.printer_manager.names())
        for index, name in enumerate(printer_names):
            row, col = divmod(index, 4)
            card = QWidget()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 8, 8, 8)

            title = QLabel(f"{name}")
            title.setStyleSheet("font-weight: bold;")
            status_label = QLabel("Status: UNKNOWN")
            info_label = QLabel("Model: UNKNOWN")
            fault_label = QLabel("Fault: NONE")
            card_layout.addWidget(title)
            card_layout.addWidget(status_label)
            card_layout.addWidget(info_label)
            card_layout.addWidget(fault_label)

            buttons = QHBoxLayout()
            for action in ("Pause", "Resume", "Stop"):
                button = QPushButton(action)
                button.setEnabled(False)
                button.clicked.connect(lambda _checked=False, action=action, printer=name: self._printer_action(printer, action))
                buttons.addWidget(button)
            card_layout.addLayout(buttons)
            card.setEnabled(False)

            self._printer_cards[name] = {
                "widget": card,
                "status": status_label,
                "info": info_label,
                "fault": fault_label,
                "buttons": buttons,
            }
            self.printer_grid.addWidget(card, row, col)

    def _refresh_printer_cards(self) -> None:
        selected_printers = set()
        for box in self._box_cards.values():
            if not box["selected"]:
                continue
            printer = box["printer"].currentData()
            if printer:
                selected_printers.add(printer)

        for name, card in self._printer_cards.items():
            status = self.context.printer_monitor.printer_service.last_known_status(name)
            if status is None:
                card["status"].setText("Status: UNKNOWN")
                card["fault"].setText("Fault: NONE")
            else:
                card["status"].setText(f"Status: {status.value}")
                card["fault"].setText(f"Fault: {status.value if status.value in ('ERROR', 'OFFLINE', 'PAUSED') else 'NONE'}")

            active = self.active_job_id is not None and name in selected_printers
            card["widget"].setEnabled(active)
            for button in card["buttons"].parent().findChildren(QPushButton):
                button.setEnabled(active)

    def _printer_action(self, printer_name: str, action: str) -> None:
        if self.active_job_id is None:
            return
        if action == "Pause":
            self.context.production_controller.pause_job(self.active_job_id, self.current_user.id)
            self.status_label.setText(f"Printer {printer_name} paused.")
        elif action == "Resume":
            self.context.production_controller.resume_job(self.active_job_id, self.current_user.id)
            self.status_label.setText(f"Printer {printer_name} resumed.")
        elif action == "Stop":
            self.context.production_controller.stop_job(self.active_job_id, self.current_user.id)
            self.status_label.setText(f"Printer {printer_name} stopped.")
            self.start_button.setEnabled(False)
            self.active_job_id = None
            self.sections_box.hide()
            self.form_box.show()
            self.new_job_button.hide()
            self._refresh_printer_cards()

    def _create_section_cards(self, job_number: str, product_name: str, quantity: int) -> None:
        for value in list(self._box_cards.values()):
            value["container"].deleteLater()
        self._box_cards.clear()

        while self.sections_layout.count():
            item = self.sections_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())

        section_grid = QGridLayout()
        section_order = ["UNIT", "B", "M"]
        for index, label in enumerate(section_order):
            card = QWidget()
            card_layout = QVBoxLayout(card)
            header = QHBoxLayout()
            header_label = QLabel(f"{label} Box")
            header_label.setStyleSheet("font-weight: bold;")
            select_toggle = QPushButton("Selected")
            select_toggle.setCheckable(True)
            select_toggle.setChecked(True)
            select_toggle.setStyleSheet("background-color: #2e7d32; color: white;")
            select_toggle.clicked.connect(lambda checked, name=label: self._toggle_box_selection(name, checked))
            header.addWidget(header_label)
            header.addStretch()
            header.addWidget(select_toggle)
            card_layout.addLayout(header)

            details = QFormLayout()
            serial_start = f"{job_number[:3]}{index + 1:03d}***{quantity:05d}"
            serial_end = f"{job_number[:3]}{index + 1 + 5:03d}***{quantity:05d}"
            details.addRow("Start Serial", QLabel(self._mask_serial(serial_start)))
            details.addRow("End Serial", QLabel(self._mask_serial(serial_end)))
            details.addRow("POS Code", QLabel(f"POS-{index + 1:02d}"))
            details.addRow("Box Code", QLabel(f"BOX-{label}-{index + 1:02d}"))
            details.addRow("Item Description", QLabel(product_name))
            details.addRow("Batch Code", QLabel(f"BATCH-{job_number}"))

            right_panel = QWidget()
            right_layout = QVBoxLayout(right_panel)
            right_layout.addWidget(QLabel("Label"))
            right_layout.addWidget(QLabel(f"{product_name}\n{job_number}"))
            preview = QHBoxLayout()
            preview.addLayout(details)
            preview.addWidget(right_panel)
            card_layout.addLayout(preview)

            printer_combo = QComboBox()
            printer_combo.addItem("Default printer", None)
            for printer_name in self.context.printer_manager.names():
                printer_combo.addItem(printer_name, printer_name)
            card_layout.addWidget(printer_combo)

            self._box_cards[label] = {
                "container": card,
                "toggle": select_toggle,
                "printer": printer_combo,
                "selected": True,
            }
            section_grid.addWidget(card, 0, index)

        self.sections_layout.addLayout(section_grid)
        self.sections_box.show()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())

    def _toggle_box_selection(self, name: str, checked: bool) -> None:
        if name in self._box_cards:
            self._box_cards[name]["selected"] = checked
            toggle = self._box_cards[name]["toggle"]
            toggle.setText("Selected" if checked else "Unselected")
            toggle.setStyleSheet("background-color: #2e7d32; color: white;" if checked else "background-color: #b91c1c; color: white;")

    def _create_job(self) -> None:
        product_code = self.product_combo.currentData()
        if not product_code:
            QMessageBox.warning(self, "No product", "Add a product in Settings before creating a job.")
            return
        quantity = self.quantity_spin.value()

        anser_name, label_name = self._default_printers()
        if anser_name is None or label_name is None:
            QMessageBox.warning(self, "Incomplete printer setup",
                                "Configure an ANSER printer and a Zebra or Epson/CUPS label printer first.")
            return

        try:
            with session_scope() as session:
                job_service = JobService(session)
                job = job_service.create_job(product_code, quantity, self.current_user.id)
                printers = PrinterRepository(session)
                if anser_name:
                    job.anser_printer_id = printers.get_by_name(anser_name).id
                if label_name:
                    job.zebra_printer_id = printers.get_by_name(label_name).id
                product = ProductRepository(session).get_by_code(product_code)
                SerialService(session, self.context.config.api).allocate_for_job(job, product)
                job_service.mark_serials_allocated(job, self.current_user.id)
                job_service.mark_ready(job, self.current_user.id)
                self.active_job_id = job.id
                job_number = job.job_number
        except ProductionError as exc:
            QMessageBox.critical(self, "Cannot create job", str(exc))
            return

        product_name = self.product_combo.currentText().split(" - ", 1)[-1]
        self.form_box.hide()
        self.preview_job.setText(job_number)
        self.preview_product.setText(product_name)
        self.preview_count.setText(str(quantity))
        self.preview_box.show()
        self.new_job_button.show()
        self._create_section_cards(job_number, product_name, quantity)
        self.status_label.setText(f"Job {job_number} ready.")
        self.start_button.setEnabled(role_can(Role(self.current_user.role), "start_job"))
        self.job_started.emit(self.active_job_id)
        self.dashboard.set_active_job(self.active_job_id)
        self._refresh_printer_cards()

    def _start_job(self) -> None:
        if self.active_job_id is None:
            return
        selected_printers = []
        for box in self._box_cards.values():
            if not box["selected"]:
                continue
            printer_name = box["printer"].currentData()
            if printer_name:
                selected_printers.append(printer_name)

        if not selected_printers:
            self.status_label.setText("Select at least one printer in the production section before starting.")
            self.status_label.show()
            return

        with session_scope() as session:
            job = JobRepository(session).get(self.active_job_id)
            JobService(session).start_job(job, self.current_user.id)
        self.context.production_controller.start_job(self.active_job_id)
        self.status_label.setText("Production running.")
        self.start_button.setEnabled(False)
        self._refresh_printer_cards()

    def _pause_job(self) -> None:
        if self.active_job_id is None:
            return
        self.context.production_controller.pause_job(self.active_job_id, self.current_user.id)
        self.status_label.setText("Production paused.")

    def _resume_job(self) -> None:
        if self.active_job_id is None:
            return
        self.context.production_controller.resume_job(self.active_job_id, self.current_user.id)
        self.status_label.setText("Production running.")

    def _show_new_job_form(self) -> None:
        self.new_job_button.hide()
        self.form_box.show()
        self.sections_box.hide()
        self.active_job_id = None
        self.status_label.setText("No active job.")
        self.start_button.setEnabled(False)

    def _stop_job(self) -> None:
        if self.active_job_id is None:
            return
        self.context.production_controller.stop_job(self.active_job_id, self.current_user.id)
        self.status_label.setText("Production stopped.")
        self.start_button.setEnabled(False)
        self.active_job_id = None
        self.sections_box.hide()
        self.form_box.show()
        self.new_job_button.hide()
        self._refresh_printer_cards()
