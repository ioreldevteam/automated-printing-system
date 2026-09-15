"""Settings (Section 63): product catalog management and a read-only view of
the configured printers/retry policy. Printer connection details themselves
come from config.yaml (Section 63) -- editing that file is an admin/ops task,
not exposed here, to avoid a UI path that silently diverges from the file the
operations team actually deploys.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.application.app_context import AppContext
from app.database.database import session_scope
from app.database.models import User
from app.database.repositories import ProductRepository
from app.domain.exceptions import ProductionError
from app.domain.states import Role, role_can


class SettingsViewWidget(QWidget):
    def __init__(self, context: AppContext, current_user: User, parent=None):
        super().__init__(parent)
        self.context = context
        self.current_user = current_user

        layout = QVBoxLayout(self)

        products_box = QGroupBox("Products")
        products_layout = QVBoxLayout(products_box)
        self.products_table = QTableWidget(0, 2)
        self.products_table.setHorizontalHeaderLabels(["Code", "Name"])
        self.products_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        products_layout.addWidget(self.products_table)

        if role_can(Role(current_user.role), "manage_products"):
            form = QFormLayout()
            self.code_edit = QLineEdit()
            self.name_edit = QLineEdit()
            form.addRow("Product Code", self.code_edit)
            form.addRow("Product Name", self.name_edit)
            add_button = QPushButton("Add Product")
            add_button.clicked.connect(self._add_product)
            form.addRow(add_button)
            products_layout.addLayout(form)
        layout.addWidget(products_box)

        printers_box = QGroupBox("Configured Printers (from config.yaml)")
        printers_layout = QVBoxLayout(printers_box)
        for cfg in context.config.printers:
            mode = "SIMULATED" if cfg.simulate else "LIVE"
            printers_layout.addWidget(
                QLabel(f"{cfg.name}: {cfg.type} {cfg.model} @ {cfg.address}:{cfg.port} [{mode}]")
            )
        layout.addWidget(printers_box)

        retry_box = QGroupBox("Retry Policy")
        retry_layout = QVBoxLayout(retry_box)
        printing_cfg = context.config.printing
        retry_layout.addWidget(QLabel(f"Max retries: {printing_cfg.max_retries}"))
        retry_layout.addWidget(QLabel(f"Retryable: {', '.join(printing_cfg.retryable_errors)}"))
        retry_layout.addWidget(QLabel(f"Manual recovery: {', '.join(printing_cfg.manual_recovery_errors)}"))
        layout.addWidget(retry_box)

        layout.addStretch()
        self._reload_products()

    def _reload_products(self) -> None:
        with session_scope() as session:
            products = ProductRepository(session).list_active()
            self.products_table.setRowCount(len(products))
            for row, product in enumerate(products):
                self.products_table.setItem(row, 0, QTableWidgetItem(product.product_code))
                self.products_table.setItem(row, 1, QTableWidgetItem(product.product_name))

    def _add_product(self) -> None:
        code = self.code_edit.text().strip()
        name = self.name_edit.text().strip()
        if not code or not name:
            QMessageBox.warning(self, "Missing fields", "Both product code and name are required.")
            return
        try:
            with session_scope() as session:
                ProductRepository(session).create(product_code=code, product_name=name)
        except ProductionError as exc:
            QMessageBox.critical(self, "Cannot add product", str(exc))
            return
        self.code_edit.clear()
        self.name_edit.clear()
        self._reload_products()
