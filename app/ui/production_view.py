"""Production job creation and control (Section 49/95). The operator
workflow is intentionally short: select product, enter quantity, confirm,
start, monitor.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
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

        layout = QVBoxLayout(self)

        self.dashboard = DashboardWidget(context, self)
        layout.addWidget(self.dashboard)

        form_box = QGroupBox("New Production Job")
        form = QFormLayout(form_box)
        self.product_combo = QComboBox()
        self._reload_products()
        self.quantity_spin = QSpinBox()
        self.quantity_spin.setRange(1, 1_000_000)
        self.quantity_spin.setValue(3000)
        form.addRow("Product", self.product_combo)
        form.addRow("Quantity", self.quantity_spin)

        self.printer_list = QListWidget()
        self.printer_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        for name in context.printer_manager.names():
            printer = context.printer_manager.config_for(name)
            self.printer_list.addItem(f"{name} ({printer.type})")
            self.printer_list.item(self.printer_list.count() - 1).setData(Qt.ItemDataRole.UserRole, name)
        for printer in context.discovered_printers or []:
            if printer.name in context.printer_manager.names():
                continue
            item = QListWidgetItem(f"{printer.name} (detected via {printer.source})")
            item.setData(Qt.ItemDataRole.UserRole, printer.name)
            item.setToolTip(f"{printer.uri or 'No device URI'}; configure an adapter before assigning")
            self.printer_list.addItem(item)
        form.addRow("Printers", self.printer_list)
        form.addRow(QLabel("Select a printer to override its stage; the other stage uses its configured default."))

        self.create_button = QPushButton("Create Job")
        self.create_button.clicked.connect(self._create_job)
        self.create_button.setEnabled(role_can(Role(current_user.role), "create_job"))
        form.addRow(self.create_button)
        layout.addWidget(form_box)

        self.status_label = QLabel("No active job.")
        layout.addWidget(self.status_label)

        controls = QHBoxLayout()
        self.start_button = QPushButton("START")
        self.pause_button = QPushButton("PAUSE")
        self.resume_button = QPushButton("RESUME")
        self.stop_button = QPushButton("STOP")
        for button in (self.start_button, self.pause_button, self.resume_button, self.stop_button):
            button.setEnabled(False)
        self.start_button.clicked.connect(self._start_job)
        self.pause_button.clicked.connect(self._pause_job)
        self.resume_button.clicked.connect(self._resume_job)
        self.stop_button.clicked.connect(self._stop_job)
        controls.addWidget(self.start_button)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.resume_button)
        controls.addWidget(self.stop_button)
        layout.addLayout(controls)
        layout.addStretch()

    def _reload_products(self) -> None:
        self.product_combo.clear()
        with session_scope() as session:
            for product in ProductRepository(session).list_active():
                self.product_combo.addItem(f"{product.product_code} - {product.product_name}", product.product_code)

    def _create_job(self) -> None:
        product_code = self.product_combo.currentData()
        if not product_code:
            QMessageBox.warning(self, "No product", "Add a product in Settings before creating a job.")
            return
        quantity = self.quantity_spin.value()
        selected_printers = [item.data(Qt.ItemDataRole.UserRole) for item in self.printer_list.selectedItems()]
        if not selected_printers:
            QMessageBox.warning(self, "No printer", "Select at least one printer for this job.")
            return
        selected_by_type = {
            self.context.printer_manager.config_for(name).type: name
            for name in selected_printers
        }
        anser = selected_by_type.get("ANSER")
        label_printer = selected_by_type.get("ZEBRA") or selected_by_type.get("CUPS")
        if anser is None:
            anser = next(
                (name for name in self.context.printer_manager.names()
                 if self.context.printer_manager.config_for(name).type == "ANSER"),
                None,
            )
        if label_printer is None:
            label_printer = next(
                (name for name in self.context.printer_manager.names()
                 if self.context.printer_manager.config_for(name).type in ("ZEBRA", "CUPS")),
                None,
            )
        if anser is None or label_printer is None:
            QMessageBox.warning(self, "Incomplete printer selection",
                                "Configure an ANSER printer and a Zebra or Epson/CUPS label printer first.")
            return
        try:
            with session_scope() as session:
                job_service = JobService(session)
                job = job_service.create_job(product_code, quantity, self.current_user.id)
                printers = PrinterRepository(session)
                zebra = label_printer
                if anser:
                    job.anser_printer_id = printers.get_by_name(anser).id
                if zebra:
                    job.zebra_printer_id = printers.get_by_name(zebra).id
                product = ProductRepository(session).get_by_code(product_code)
                SerialService(session, self.context.config.api).allocate_for_job(job, product)
                job_service.mark_serials_allocated(job, self.current_user.id)
                job_service.mark_ready(job, self.current_user.id)
                self.active_job_id = job.id
                job_number = job.job_number
        except ProductionError as exc:
            QMessageBox.critical(self, "Cannot create job", str(exc))
            return

        self.status_label.setText(f"Job {job_number} ready.")
        self.start_button.setEnabled(role_can(Role(self.current_user.role), "start_job"))
        self.job_started.emit(self.active_job_id)
        self.dashboard.set_active_job(self.active_job_id)

    def _start_job(self) -> None:
        if self.active_job_id is None:
            return
        with session_scope() as session:
            job = JobRepository(session).get(self.active_job_id)
            JobService(session).start_job(job, self.current_user.id)
        self.context.production_controller.start_job(self.active_job_id)
        self.status_label.setText("Production running.")
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(role_can(Role(self.current_user.role), "pause_job"))
        self.stop_button.setEnabled(role_can(Role(self.current_user.role), "cancel_job"))

    def _pause_job(self) -> None:
        if self.active_job_id is None:
            return
        self.context.production_controller.pause_job(self.active_job_id, self.current_user.id)
        self.status_label.setText("Production paused.")
        self.pause_button.setEnabled(False)
        self.resume_button.setEnabled(role_can(Role(self.current_user.role), "resume_job"))

    def _resume_job(self) -> None:
        if self.active_job_id is None:
            return
        self.context.production_controller.resume_job(self.active_job_id, self.current_user.id)
        self.status_label.setText("Production running.")
        self.resume_button.setEnabled(False)
        self.pause_button.setEnabled(role_can(Role(self.current_user.role), "pause_job"))

    def _stop_job(self) -> None:
        if self.active_job_id is None:
            return
        self.context.production_controller.stop_job(self.active_job_id, self.current_user.id)
        self.status_label.setText("Production stopped.")
        for button in (self.pause_button, self.resume_button, self.stop_button):
            button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.active_job_id = None
