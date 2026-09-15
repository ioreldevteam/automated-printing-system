"""Combined job monitoring and production history view."""
from __future__ import annotations

from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from app.application.app_context import AppContext
from app.ui.history_view import HistoryViewWidget
from app.ui.jobs_view import JobsViewWidget


class JobsHistoryViewWidget(QWidget):
    def __init__(self, context: AppContext, parent=None):
        super().__init__(parent)
        self.jobs_view = JobsViewWidget(context, self)
        self.history_view = HistoryViewWidget(context, self)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.addWidget(self.jobs_view)
        layout.addWidget(self.history_view)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)

        outer_layout = QVBoxLayout(self)
        outer_layout.addWidget(scroll)

    def refresh(self) -> None:
        self.jobs_view.refresh()
        self.history_view.refresh()