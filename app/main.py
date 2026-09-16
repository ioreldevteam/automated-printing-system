"""Application entry point (Section 53: startup recovery runs before the
operator reaches the dashboard).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication, QMessageBox

from app.application.app_context import build_app_context
from app.application.auth_service import AuthService
from app.application.printer_service import PrinterService
from app.application.recovery_service import RecoveryService
from app.config.loader import load_config
from app.database.database import init_db, session_scope
from app.logging.logger import configure_logging
from app.ui.dialogs.login_dialog import LoginDialog
from app.ui.dialogs.recovery_dialog import RecoveryDialog
from app.ui.main_window import MainWindow
from app.ui.theme import apply_light_theme


def run_startup_recovery(app_context, parent_widget) -> None:
    with session_scope() as session:
        summaries = RecoveryService(session, app_context.printer_manager).scan_on_startup()

    for summary in summaries:
        dialog = RecoveryDialog(summary, app_context.printer_monitor.printer_service,
                                 app_context.production_controller.resolve_zebra_printer_name(summary.job_id),
                                 parent_widget)
        dialog.exec()
        if dialog.decision == "resume":
            app_context.production_controller.resume_job(summary.job_id, None)
        elif dialog.decision == "cancel":
            app_context.production_controller.stop_job(summary.job_id, None)


def main() -> int:
    qt_app = QApplication(sys.argv)
    apply_light_theme(qt_app)

    config = load_config()
    configure_logging(config.logging)
    init_db(config.database.path)

    with session_scope() as session:
        AuthService(session, config.security.bcrypt_rounds).ensure_default_admin()

    app_context = build_app_context(config)
    with session_scope() as session:
        PrinterService(app_context.printer_manager).sync_configured_printers(session)
    app_context.printer_manager.connect_all()
    app_context.printer_monitor.start()

    login_dialog = LoginDialog(config.security.bcrypt_rounds)
    if login_dialog.exec() != LoginDialog.DialogCode.Accepted or login_dialog.authenticated_user is None:
        return 0
    current_user = login_dialog.authenticated_user
    app_context.current_user = current_user


    main_window = MainWindow(app_context, current_user)
    run_startup_recovery(app_context, main_window)
    main_window.show()

    with session_scope() as session:
        auth_service = AuthService(session, config.security.bcrypt_rounds)
        user_record = auth_service.users.get_by_username(current_user.username)
        using_default_password = user_record is not None and auth_service.is_using_default_password(user_record)
    if using_default_password:
        QMessageBox.warning(
            main_window, "Change default password",
            "The default admin account still uses the initial password. \n"
            "Change it before deploying to production.\n\n"
            "Default credentials: admin / admin",
        )

    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
