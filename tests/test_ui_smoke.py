"""Headless UI smoke test: builds the full application context and the main
window against the offscreen Qt platform plugin, and exercises each tab's
refresh path once. This is not a substitute for testing against a real
display, but it catches import errors, constructor bugs, and blocking I/O
calls made from the UI thread during construction.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from app.application.app_context import build_app_context
from app.application.auth_service import AuthService
from app.application.job_service import JobService
from app.application.printer_service import PrinterService
from app.application.serial_service import SerialService
from app.config.loader import AnserModbusConfig, ApiConfig, AppConfig, PrinterConfig
from app.database.database import session_scope
from app.database.repositories import ProductRepository
from app.domain.states import Role


@pytest.fixture()
def qt_app():
    PySide6 = pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from app.ui.theme import apply_light_theme
    apply_light_theme(app)
    yield app


def _test_config() -> AppConfig:
    return AppConfig(
        printers=[
            PrinterConfig(name="ANSER-01", type="ANSER", address="127.0.0.1", port=502, simulate=True,
                          anser_modbus=AnserModbusConfig()),
            PrinterConfig(name="ZEBRA-01", type="ZEBRA", address="127.0.0.1", port=9100, simulate=True),
        ],
    )


def test_main_window_builds_and_refreshes(db, qt_app):
    config = _test_config()
    with session_scope() as session:
        AuthService(session).ensure_default_admin()
        product = ProductRepository(session).create(product_code="PROD-A", product_name="Smoke Test Product")
        product_id = product.id

    app_context = build_app_context(config)
    with session_scope() as session:
        PrinterService(app_context.printer_manager).sync_configured_printers(session)
    app_context.printer_manager.connect_all()

    with session_scope() as session:
        user = AuthService(session).users.get_by_username("admin")
        user_id = user.id
        role = user.role
        username = user.username

    from app.database.models import User
    current_user = User(id=user_id, username=username, role=role, password_hash="x", active=True)

    from app.ui.main_window import MainWindow
    window = MainWindow(app_context, current_user)

    window.dashboard.refresh()
    window.printer_view.refresh()
    window.jobs_view.refresh()
    window.history_view.refresh()

    with session_scope() as session:
        job = JobService(session).create_job("PROD-A", 5, created_by=user_id)
        product = ProductRepository(session).get(product_id)
        SerialService(session, ApiConfig(mode="local")).allocate_for_job(job, product)
        job_id = job.id

    window.dashboard.set_active_job(job_id)
    window.dashboard.refresh()

    window.context.printer_monitor.stop()
    window.context.production_controller.shutdown()
    window.close()
