"""Operator authentication (Section 64/51). Passwords are always bcrypt
hashed; plain-text passwords are never stored or logged.
"""
from __future__ import annotations

import bcrypt
from sqlalchemy.orm import Session

from app.database.models import User
from app.database.repositories import AuditLogRepository, UserRepository
from app.domain.exceptions import AuthenticationError
from app.domain.states import Role


class AuthService:
    def __init__(self, session: Session, bcrypt_rounds: int = 12):
        self.session = session
        self.users = UserRepository(session)
        self.audit = AuditLogRepository(session)
        self.bcrypt_rounds = bcrypt_rounds

    def create_user(self, username: str, password: str, role: Role) -> User:
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(self.bcrypt_rounds)).decode("ascii")
        return self.users.create(username=username, password_hash=password_hash, role=role.value)

    def login(self, username: str, password: str) -> User:
        user = self.users.get_by_username(username)
        if user is None or not user.active:
            raise AuthenticationError("Invalid username or password")
        if not bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
            raise AuthenticationError("Invalid username or password")
        self.users.touch_login(user)
        self.audit.record(user.id, "LOGIN", entity_type="user", entity_id=username)
        return user

    def logout(self, user: User) -> None:
        self.audit.record(user.id, "LOGOUT", entity_type="user", entity_id=user.username)

    DEFAULT_ADMIN_USERNAME = "admin"
    DEFAULT_ADMIN_PASSWORD = "admin"

    def ensure_default_admin(self) -> None:
        """Seeds one ADMIN account on first run so the application is usable
        out of the box. The operator must change this password immediately --
        surfaced as a startup warning, not silently assumed safe."""
        if self.users.get_by_username(self.DEFAULT_ADMIN_USERNAME) is None:
            self.create_user(self.DEFAULT_ADMIN_USERNAME, self.DEFAULT_ADMIN_PASSWORD, Role.ADMIN)

    def is_using_default_password(self, user: User) -> bool:
        if user.username != self.DEFAULT_ADMIN_USERNAME:
            return False
        return bcrypt.checkpw(self.DEFAULT_ADMIN_PASSWORD.encode("utf-8"), user.password_hash.encode("ascii"))
