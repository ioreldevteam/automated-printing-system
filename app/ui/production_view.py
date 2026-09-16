"""Production job creation and control. The home screen opens with a
job-first workflow: create the job, review the available printer cards, then
show the generated box-by-box production sections for the active job.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
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
from app.database.repositories import JobRepository, PrinterRepository, ProductRepository, UnitRepository
from app.domain.exceptions import ProductionError
from app.domain.states import Role, role_can
from app.templates.label_designer import render_label_qimage
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

        self.actions_widget = QWidget()
        start_row = QHBoxLayout(self.actions_widget)
        start_row.setContentsMargins(0, 0, 0, 0)
        self.cancel_button = QPushButton("CANCEL")
        self.cancel_button.setEnabled(False)
        self.cancel_button.setStyleSheet("background-color: #b91c1c; color: white;")
        self.cancel_button.clicked.connect(self._cancel_job)
        start_row.addWidget(self.cancel_button)

        self.start_button = QPushButton("START")
        self.start_button.setEnabled(False)
        self.start_button.clicked.connect(self._start_job)
        start_row.addWidget(self.start_button)
        self.cancel_button.hide()
        self.start_button.hide()
        self.actions_widget.hide()
        layout.addWidget(self.actions_widget)

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

    def _available_printer_names(self) -> list[str]:
        names = list(self.context.printer_manager.names())
        for printer in self.context.discovered_printers or []:
            if printer.name not in names:
                names.append(printer.name)
        return names

    def _label_printer_names(self) -> list[str]:
        """Printers that can take a label/box print job -- i.e. every known
        printer except the ANSER serializer, which speaks a different
        (FIFO push) protocol and is never a valid target for the per-box
        printer picker."""
        names = self._available_printer_names()
        return [
            name for name in names
            if not (name in self.context.printer_manager.names()
                    and self.context.printer_manager.config_for(name).type == "ANSER")
        ]

    def _default_printers(self) -> tuple[str | None, str | None]:
        names = self._available_printer_names()
        anser = next(
            (name for name in names
             if name in self.context.printer_manager.names() and self.context.printer_manager.config_for(name).type == "ANSER"),
            None,
        )
        label = next(
            (name for name in names
             if name in self.context.printer_manager.names()
             and self.context.printer_manager.config_for(name).type in ("ZEBRA", "CUPS", "WINDOWS")),
            None,
        )
        return anser, label

    def _build_printer_cards(self) -> None:
        for name in list(self._printer_cards):
            widget = self._printer_cards[name]["widget"]
            self.printer_grid.removeWidget(widget)
            widget.deleteLater()
        self._printer_cards.clear()

        printer_names = self._available_printer_names()
        for index, name in enumerate(printer_names):
            row, col = divmod(index, 4)
            card = QWidget()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 8, 8, 8)

            title = QLabel(f"{name}")
            title.setStyleSheet("font-weight: bold;")
            status_label = QLabel("Status: UNKNOWN")
            info_label = QLabel("Model: UNKNOWN")
            if name in self.context.printer_manager.names():
                cfg = self.context.printer_manager.config_for(name)
                info_label.setText(f"Model: {cfg.model or 'unknown'}")
            else:
                detected = next((p for p in (self.context.discovered_printers or []) if p.name == name), None)
                if detected is not None:
                    info_label.setText(f"Source: {detected.source} | {detected.uri or 'USB'}")
            fault_label = QLabel("Fault: NONE")
            card_layout.addWidget(title)
            card_layout.addWidget(status_label)
            card_layout.addWidget(info_label)
            card_layout.addWidget(fault_label)

            buttons = QHBoxLayout()
            action_buttons: dict[str, QPushButton] = {}
            for action in ("Pause", "Resume", "Stop"):
                button = QPushButton(action)
                button.setEnabled(False)
                button.clicked.connect(lambda _checked=False, action=action, printer=name: self._printer_action(printer, action))
                buttons.addWidget(button)
                action_buttons[action] = button
            card_layout.addLayout(buttons)
            card.setEnabled(False)

            self._printer_cards[name] = {
                "widget": card,
                "status": status_label,
                "info": info_label,
                "fault": fault_label,
                "buttons": buttons,
                "action_buttons": action_buttons,
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
            # Enable the buttons directly instead of trying to re-discover
            # them via the layout: `buttons.parent()` is the QHBoxLayout
            # itself (Qt reparents a nested layout to its parent layout when
            # you addLayout() it), and the QPushButtons added to it via
            # addWidget() are never reparented onto that layout object --
            # they become children of the card widget instead. So
            # `card["buttons"].parent().findChildren(QPushButton)` always
            # returned an empty list and these buttons stayed disabled
            # forever, no matter what state the job was in.
            for button in card["action_buttons"].values():
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
            self.cancel_button.setEnabled(False)
            self.cancel_button.hide()
            self.start_button.hide()
            self.actions_widget.hide()
            self.active_job_id = None
            self.sections_box.hide()
            self.form_box.show()
            self.new_job_button.hide()
            self._refresh_printer_cards()

    def _get_label_specs(self, product_code: str, product_name: str, job_number: str, serial_number: str) -> dict:
        item_c = product_code or "101-1001"
        specs = {
            "item_code": item_c,
            "product_name": product_name or "1 Gang 1 Way Switch Indicator",
            "batch_code": f"BATCH-{job_number}" if job_number else "BATCH-001",
            "serial_number": serial_number or f"SN{item_c.replace('-', '')}-0001",
            "retail_barcode": "8901234567890",
            "mrp_value": "450.00",
            "rated_specs": "10 AX / 250 V~",
            "sls_code": "141",
        }
        mock_file = Path(__file__).resolve().parents[2] / "mock_api" / "product_data.json"
        if mock_file.exists():
            try:
                with open(mock_file, "r", encoding="utf-8") as f:
                    catalog = json.load(f)
                for item in catalog:
                    if item.get("item_code") == item_c:
                        if item.get("retail_barcode"):
                            specs["retail_barcode"] = str(item["retail_barcode"])
                        if item.get("mrp_value"):
                            specs["mrp_value"] = str(item["mrp_value"])
                        break
            except Exception:
                pass
        return specs

    def _show_full_label_dialog(self, specs: dict) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Unit Box Label - {specs.get('item_code', '')}")
        d_layout = QVBoxLayout(dialog)

        img = render_label_qimage(specs, width=600, height=240)
        lbl = QLabel()
        lbl.setPixmap(QPixmap.fromImage(img))
        lbl.setStyleSheet("border: 2px solid #333; background: white;")
        d_layout.addWidget(lbl)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(dialog.reject)
        d_layout.addWidget(btn_box)
        dialog.exec()

    def _create_section_cards(self, job_number: str, product_name: str, quantity: int,
                              product_code: str = "", first_serial: str = "", last_serial: str = "") -> None:
        for value in list(self._box_cards.values()):
            value["container"].deleteLater()
        self._box_cards.clear()

        while self.sections_layout.count():
            item = self.sections_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())

        clean_code = (product_code or "101-1001").replace("-", "")
        start_sn = first_serial or f"SN{clean_code}-0001"
        end_sn = last_serial or f"SN{clean_code}-{quantity:04d}"

        section_grid = QGridLayout()
        section_order = ["UNIT", "B", "M"]
        for index, label in enumerate(section_order):
            card = QWidget()
            card_layout = QVBoxLayout(card)
            header = QHBoxLayout()
            header_label = QLabel(f"{label} Box")
            header_label.setStyleSheet("font-weight: bold; font-size: 13px;")
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
            serial_start = start_sn if label == "UNIT" else f"B-BOX-{clean_code}-001" if label == "B" else f"M-BOX-{clean_code}-001"
            serial_end = end_sn if label == "UNIT" else f"B-BOX-{clean_code}-{max(1, quantity // 10):03d}" if label == "B" else f"M-BOX-{clean_code}-{max(1, quantity // 100):03d}"
            details.addRow("Start Serial", QLabel(self._mask_serial(serial_start)))
            details.addRow("End Serial", QLabel(self._mask_serial(serial_end)))
            details.addRow("POS Code", QLabel(f"POS-{index + 1:02d}"))
            details.addRow("Box Code", QLabel(f"BOX-{label}-{index + 1:02d}"))
            details.addRow("Item Description", QLabel(product_name))
            details.addRow("Batch Code", QLabel(f"BATCH-{job_number}"))

            if label == "UNIT":
                unit_preview_container = QWidget()
                unit_preview_layout = QVBoxLayout(unit_preview_container)
                unit_preview_layout.setContentsMargins(4, 4, 4, 4)

                preview_title = QLabel("<b>Unit Box Label Preview</b>")
                preview_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
                unit_preview_layout.addWidget(preview_title)

                label_specs = self._get_label_specs(product_code, product_name, job_number, start_sn)
                unit_img = render_label_qimage(label_specs, width=600, height=240)

                unit_img_label = QLabel()
                unit_img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                unit_pixmap = QPixmap.fromImage(unit_img).scaled(
                    230, 92, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
                unit_img_label.setPixmap(unit_pixmap)
                unit_img_label.setStyleSheet(
                    "border: 1px solid #0284c7; background-color: #ffffff; border-radius: 4px; padding: 2px;"
                )
                unit_img_label.setCursor(Qt.CursorShape.PointingHandCursor)
                unit_img_label.setToolTip("Click to enlarge Unit Box label")
                unit_img_label.mousePressEvent = lambda event, s=label_specs: self._show_full_label_dialog(s)
                unit_preview_layout.addWidget(unit_img_label)

                enlarge_btn = QPushButton("🔍 Enlarge Label")
                enlarge_btn.setStyleSheet("font-size: 11px; padding: 2px 6px;")
                enlarge_btn.clicked.connect(lambda _=False, s=label_specs: self._show_full_label_dialog(s))
                unit_preview_layout.addWidget(enlarge_btn)

                preview = QHBoxLayout()
                preview.addLayout(details)
                preview.addWidget(unit_preview_container)
                card_layout.addLayout(preview)
            else:
                right_panel = QWidget()
                right_layout = QVBoxLayout(right_panel)
                right_layout.addWidget(QLabel(f"<b>{label}-Box Label</b>"))
                right_layout.addWidget(QLabel(f"{product_name}\nBATCH-{job_number}"))
                preview = QHBoxLayout()
                preview.addLayout(details)
                preview.addWidget(right_panel)
                card_layout.addLayout(preview)

            printer_combo = QComboBox()
            printer_combo.addItem("Default printer", None)
            for printer_name in self._label_printer_names():
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
                units = UnitRepository(session).list_for_job(job.id)
                first_serial = units[0].serial_number if units else ""
                last_serial = units[-1].serial_number if units else ""
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
        self._create_section_cards(
            job_number,
            product_name,
            quantity,
            product_code=product_code,
            first_serial=first_serial,
            last_serial=last_serial,
        )
        self.status_label.setText(f"Job {job_number} ready.")
        self.actions_widget.show()
        self.start_button.show()
        self.cancel_button.show()
        self.start_button.setEnabled(role_can(Role(self.current_user.role), "start_job"))
        self.cancel_button.setEnabled(role_can(Role(self.current_user.role), "cancel_job"))
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

        # The queue only runs a single Zebra/label worker per job, so every
        # active box has to agree on one physical printer -- otherwise we'd
        # have to silently pick one and the operator's choice for the other
        # boxes would be ignored.
        distinct_printers = set(selected_printers)
        if len(distinct_printers) > 1:
            self.status_label.setText(
                "Select the same printer for every active box before starting "
                "(a job currently prints to one label printer at a time)."
            )
            self.status_label.show()
            return

        chosen_printer_name = next(iter(distinct_printers))

        with session_scope() as session:
            job = JobRepository(session).get(self.active_job_id)
            chosen_printer = PrinterRepository(session).get_by_name(chosen_printer_name)
            if chosen_printer is None:
                self.status_label.setText(
                    f"Printer '{chosen_printer_name}' isn't registered yet -- rescan printers and try again."
                )
                self.status_label.show()
                return
            # This is the actual fix: apply the operator's chosen printer to
            # the job so the queue worker targets it. Previously the
            # selection made here was only used to enable/highlight printer
            # cards and was never written back to the job, so the job kept
            # printing to whatever default printer was assigned at
            # Create-Job time (e.g. a simulated printer), no matter what was
            # picked here.
            job.zebra_printer_id = chosen_printer.id
            JobService(session).start_job(job, self.current_user.id)
        self.context.production_controller.start_job(self.active_job_id)
        self.status_label.setText(f"Production running on {chosen_printer_name}.")
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.cancel_button.hide()
        self.start_button.hide()
        self.actions_widget.hide()
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
        self.preview_box.hide()
        self.active_job_id = None
        self.status_label.setText("No active job.")
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.cancel_button.hide()
        self.start_button.hide()
        self.actions_widget.hide()

    def _cancel_job(self) -> None:
        if self.active_job_id is None:
            return
        if not role_can(Role(self.current_user.role), "cancel_job"):
            QMessageBox.warning(self, "Not allowed", "Your role cannot cancel jobs.")
            return
        confirm = QMessageBox.question(
            self, "Cancel job",
            "Cancel this job before it prints? It will be recorded as CANCELLED in job history.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        job_id = self.active_job_id
        try:
            with session_scope() as session:
                job = JobRepository(session).get(job_id)
                if job is None:
                    return
                JobService(session).cancel_job(job, self.current_user.id)
                job_number = job.job_number
        except ProductionError as exc:
            QMessageBox.critical(self, "Cannot cancel job", str(exc))
            return

        self.status_label.setText(f"Job {job_number} cancelled.")
        self.active_job_id = None
        self.sections_box.hide()
        self.preview_box.hide()
        self.form_box.show()
        self.new_job_button.hide()
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.cancel_button.hide()
        self.start_button.hide()
        self.actions_widget.hide()
        self.dashboard.set_active_job(None)
        self._refresh_printer_cards()

    def _stop_job(self) -> None:
        if self.active_job_id is None:
            return
        self.context.production_controller.stop_job(self.active_job_id, self.current_user.id)
        self.status_label.setText("Production stopped.")
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.cancel_button.hide()
        self.start_button.hide()
        self.actions_widget.hide()
        self.active_job_id = None
        self.sections_box.hide()
        self.preview_box.hide()
        self.form_box.show()
        self.new_job_button.hide()
        self._refresh_printer_cards()
