"""Forces a consistent light theme regardless of the OS theme setting. Qt's
default styling can otherwise pick up Windows dark mode and render some
widgets with poor contrast; Fusion + an explicit light QPalette sidesteps
that rather than depending on the platform theme.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

BACKGROUND = QColor(245, 246, 248)
BASE = QColor(255, 255, 255)
TEXT = QColor(30, 30, 30)
DISABLED_TEXT = QColor(150, 150, 150)
ACCENT = QColor(0, 102, 204)
BUTTON = QColor(240, 240, 240)


def apply_light_theme(app: QApplication) -> None:
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, BACKGROUND)
    palette.setColor(QPalette.ColorRole.WindowText, TEXT)
    palette.setColor(QPalette.ColorRole.Base, BASE)
    palette.setColor(QPalette.ColorRole.AlternateBase, BACKGROUND)
    palette.setColor(QPalette.ColorRole.ToolTipBase, BASE)
    palette.setColor(QPalette.ColorRole.ToolTipText, TEXT)
    palette.setColor(QPalette.ColorRole.Text, TEXT)
    palette.setColor(QPalette.ColorRole.Button, BUTTON)
    palette.setColor(QPalette.ColorRole.ButtonText, TEXT)
    palette.setColor(QPalette.ColorRole.BrightText, QColor("red"))
    palette.setColor(QPalette.ColorRole.Link, ACCENT)
    palette.setColor(QPalette.ColorRole.Highlight, ACCENT)
    palette.setColor(QPalette.ColorRole.HighlightedText, BASE)

    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, DISABLED_TEXT)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, DISABLED_TEXT)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, DISABLED_TEXT)

    app.setPalette(palette)

    app.setStyleSheet(
        """
        QMainWindow, QDialog { background-color: #f5f6f8; }
        QGroupBox {
            font-weight: bold;
            border: 1px solid #d0d3d8;
            border-radius: 4px;
            margin-top: 10px;
            padding-top: 10px;
            background-color: #ffffff;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 4px;
            color: #1e1e1e;
        }
        QTabWidget::pane { border: 1px solid #d0d3d8; background-color: #ffffff; }
        QTabBar::tab {
            background: #e9eaed;
            padding: 6px 14px;
            border: 1px solid #d0d3d8;
            border-bottom: none;
        }
        QTabBar::tab:selected { background: #ffffff; font-weight: bold; }
        QPushButton {
            background-color: #ffffff;
            border: 1px solid #b8bcc4;
            border-radius: 4px;
            padding: 5px 12px;
        }
        QPushButton:hover { background-color: #eef3fb; }
        QPushButton:pressed { background-color: #dde8f7; }
        QPushButton:disabled { color: #9a9a9a; background-color: #f2f2f2; }
        QLineEdit, QSpinBox, QComboBox, QTextEdit {
            background-color: #ffffff;
            border: 1px solid #c3c6cc;
            border-radius: 3px;
            padding: 3px;
        }
        QTableWidget {
            background-color: #ffffff;
            gridline-color: #e0e2e6;
            selection-background-color: #cfe2fb;
            selection-color: #1e1e1e;
        }
        QHeaderView::section {
            background-color: #eceef1;
            padding: 4px;
            border: 1px solid #d0d3d8;
        }
        QProgressBar {
            border: 1px solid #c3c6cc;
            border-radius: 4px;
            text-align: center;
            background-color: #ffffff;
        }
        QProgressBar::chunk { background-color: #0066cc; }
        """
    )
