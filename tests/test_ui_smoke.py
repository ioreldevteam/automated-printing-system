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


def test_printer_card_action_buttons_enable_when_job_active(db, qt_app):
    """Regression test: _refresh_printer_cards() used to look up each
    printer card's Pause/Resume/Stop buttons via
    `card["buttons"].parent().findChildren(QPushButton)`, which always
    returned an empty list (the buttons are QObject children of the card
    widget, not of the nested QHBoxLayout), so the buttons stayed disabled
    forever no matter the job state."""
    config = _test_config()
    with session_scope() as session:
        AuthService(session).ensure_default_admin()

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

    from app.ui.production_view import ProductionViewWidget
    view = ProductionViewWidget(app_context, current_user)

    printer_name = next(iter(view._printer_cards))
    card = view._printer_cards[printer_name]
    assert all(not btn.isEnabled() for btn in card["action_buttons"].values())

    # Simulate a running job with this printer selected in an active box.
    view.active_job_id = 999
    view._box_cards["FAKE"] = {"selected": True, "printer": type(
        "FakeCombo", (), {"currentData": staticmethod(lambda: printer_name)}
    )()}
    view._refresh_printer_cards()

    assert all(btn.isEnabled() for btn in card["action_buttons"].values())

    app_context.printer_monitor.stop()
    app_context.production_controller.shutdown()


def test_production_view_start_and_cancel_buttons_hidden_until_job_created(db, qt_app):
    config = _test_config()
    with session_scope() as session:
        AuthService(session).ensure_default_admin()
        ProductRepository(session).create(product_code="PROD-B", product_name="Test Product B")

    app_context = build_app_context(config)
    with session_scope() as session:
        PrinterService(app_context.printer_manager).sync_configured_printers(session)
    app_context.printer_manager.connect_all()

    with session_scope() as session:
        user = AuthService(session).users.get_by_username("admin")
        from app.database.models import User
        current_user = User(id=user.id, username=user.username, role=user.role, password_hash="x", active=True)

    from app.ui.production_view import ProductionViewWidget
    view = ProductionViewWidget(app_context, current_user)

    # Initially before job creation, both buttons and container are hidden
    assert view.actions_widget.isHidden()
    assert view.start_button.isHidden()
    assert view.cancel_button.isHidden()

    # Create job
    view.product_combo.setCurrentIndex(view.product_combo.findData("PROD-B"))
    view.quantity_spin.setValue(10)
    view._create_job()

    # Now that job is created, buttons and container are visible
    assert not view.actions_widget.isHidden()
    assert not view.start_button.isHidden()
    assert not view.cancel_button.isHidden()

    # Reset to new job form
    view._show_new_job_form()
    assert view.actions_widget.isHidden()
    assert view.start_button.isHidden()
    assert view.cancel_button.isHidden()

    app_context.printer_monitor.stop()
    app_context.production_controller.shutdown()


def test_unit_box_label_preview_in_production_view(db, qt_app):
    from PySide6.QtWidgets import QLabel, QPushButton
    config = _test_config()
    with session_scope() as session:
        AuthService(session).ensure_default_admin()
        ProductRepository(session).create(product_code="101-1001", product_name="1 Gang 1 Way Switch Indicator")

    app_context = build_app_context(config)
    with session_scope() as session:
        PrinterService(app_context.printer_manager).sync_configured_printers(session)
    app_context.printer_manager.connect_all()

    with session_scope() as session:
        user = AuthService(session).users.get_by_username("admin")
        from app.database.models import User
        current_user = User(id=user.id, username=user.username, role=user.role, password_hash="x", active=True)

    from app.ui.production_view import ProductionViewWidget
    view = ProductionViewWidget(app_context, current_user)

    view.product_combo.setCurrentIndex(view.product_combo.findData("101-1001"))
    view.quantity_spin.setValue(10)
    view._create_job()

    assert "UNIT" in view._box_cards
    unit_card = view._box_cards["UNIT"]["container"]

    # Check for preview title label
    labels = unit_card.findChildren(QLabel)
    preview_titles = [l.text() for l in labels if "Unit Box Label Preview" in l.text()]
    assert len(preview_titles) == 1

    # Check that an image preview label with pixmap exists
    pixmap_labels = [l for l in labels if l.pixmap() is not None and not l.pixmap().isNull()]
    assert len(pixmap_labels) >= 1
    assert pixmap_labels[0].pixmap().width() > 0

    # Check that Enlarge Label button exists
    buttons = unit_card.findChildren(QPushButton)
    enlarge_buttons = [b for b in buttons if "Enlarge Label" in b.text()]
    assert len(enlarge_buttons) == 1

    app_context.printer_monitor.stop()
    app_context.production_controller.shutdown()

