"""Operator login (Section 51/64)."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from app.database.database import session_scope
from app.database.models import User
from app.domain.exceptions import AuthenticationError


class LoginDialog(QDialog):
    def __init__(self, bcrypt_rounds: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Production Print System - Login")
        self.setMinimumWidth(320)
        self.bcrypt_rounds = bcrypt_rounds
        self.authenticated_user: User | None = None

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Username", self.username_edit)
        form.addRow("Password", self.password_edit)
        layout.addLayout(form)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: red;")
        layout.addWidget(self.error_label)

        login_button = QPushButton("Login")
        login_button.clicked.connect(self._attempt_login)
        layout.addWidget(login_button)
        self.password_edit.returnPressed.connect(self._attempt_login)

    def _attempt_login(self) -> None:
        from app.application.auth_service import AuthService

        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        try:
            with session_scope() as session:
                auth = AuthService(session, self.bcrypt_rounds)
                self.authenticated_user = auth.login(username, password)
            self.accept()
        except AuthenticationError as exc:
            self.error_label.setText(str(exc))
