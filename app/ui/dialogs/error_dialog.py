"""Operator-friendly error presentation (Section 86-87). Operators should
never see raw socket/TCP errors -- only what happened and what to check.
Technical detail stays available for maintenance/admin roles.
"""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QTextEdit, QVBoxLayout

FRIENDLY_MESSAGES: dict[str, tuple[str, list[str]]] = {
    "PRINTER_001": ("Printer is not responding.", ["Printer power", "Network connection", "Printer status"]),
    "PRINTER_002": ("Printer is out of label media.", ["Load new media", "Close the media cover"]),
    "PRINTER_003": ("Printer is out of ribbon.", ["Load a new ribbon"]),
    "PRINTER_004": ("Printer head is open.", ["Close the print head"]),
    "PRINT_001": ("The printer did not respond in time.", ["Printer power", "Network connection"]),
    "PRINT_002": ("The print result could not be confirmed.", ["Check the last physical unit before resuming"]),
    "VERIFY_001": ("Scanned serial does not match the expected serial.", ["Stop and inspect the product"]),
    "VERIFY_002": ("This serial number has already been used.", ["Contact a supervisor"]),
    "SYSTEM_001": ("A database error occurred.", ["Do not continue without confirming data integrity"]),
    "API_001": ("The production server did not respond in time.", ["Check network connection"]),
    "API_003": ("The production server is unavailable.", ["Production continues from the local buffer"]),
}


class ErrorDialog(QDialog):
    def __init__(self, error_code: str, technical_detail: str = "", show_technical: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Production Paused")
        self.setMinimumWidth(420)

        friendly, checks = FRIENDLY_MESSAGES.get(error_code, ("An unexpected error occurred.", []))
        layout = QVBoxLayout(self)

        message = QLabel(friendly)
        message.setWordWrap(True)
        message.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(message)

        if checks:
            check_label = QLabel("Check:\n" + "\n".join(f"  {i + 1}. {c}" for i, c in enumerate(checks)))
            check_label.setWordWrap(True)
            layout.addWidget(check_label)

        layout.addWidget(QLabel("Production has been paused safely."))

        if show_technical and technical_detail:
            detail_box = QTextEdit()
            detail_box.setReadOnly(True)
            detail_box.setPlainText(f"[{error_code}] {technical_detail}")
            detail_box.setMaximumHeight(100)
            layout.addWidget(detail_box)

        close_button = QPushButton("OK")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)
