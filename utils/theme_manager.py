from __future__ import annotations
"""
Theme Manager for AI Master TTS Controller
Provides high-contrast, professional styling for both macOS Dark Mode and Light Mode.
Guarantees consistent text and background visibility across QComboBox, QLineEdit, QListWidget, and buttons.
"""

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt


def get_dark_stylesheet() -> str:
    """High-contrast dark mode stylesheet for macOS/Windows."""
    return """
        * {
            font-size: 13px;
            font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
        }
        QWidget {
            background-color: #212529;
            color: #f8f9fa;
        }
        QMainWindow {
            background-color: #1a1d20;
        }

        /* ── QComboBox (고대비 다크 스타일: 흰 글씨 + 차콜 배경 + 명확한 테두리) ── */
        QComboBox {
            background-color: #2c3238;
            color: #ffffff;
            border: 1px solid #495057;
            border-radius: 5px;
            padding: 5px 10px;
            min-height: 24px;
        }
        QComboBox:hover {
            border: 1px solid #3b82f6;
            background-color: #343a40;
        }
        QComboBox:focus {
            border: 1.5px solid #60a5fa;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 25px;
            border-left: 1px solid #495057;
        }
        QComboBox QAbstractItemView {
            background-color: #2c3238;
            color: #ffffff;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
            border: 1px solid #495057;
            padding: 4px;
        }

        /* ── QLineEdit & QTextEdit ── */
        QLineEdit, QTextEdit, QPlainTextEdit {
            background-color: #2c3238;
            color: #ffffff;
            border: 1px solid #495057;
            border-radius: 4px;
            padding: 5px;
        }
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
            border: 1.5px solid #60a5fa;
            background-color: #343a40;
        }

        /* ── QListWidget & QTableWidget ── */
        QListWidget, QTableWidget {
            background-color: #212529;
            color: #ffffff;
            border: 1px solid #495057;
            border-radius: 4px;
        }
        QListWidget::item:selected, QTableWidget::item:selected {
            background-color: #2563eb;
            color: #ffffff;
        }

        /* ── QPushButton (기본 버튼) ── */
        QPushButton {
            background-color: #343a40;
            color: #ffffff;
            border: 1px solid #495057;
            border-radius: 5px;
            padding: 6px 12px;
        }
        QPushButton:hover {
            background-color: #495057;
        }
        QPushButton:pressed {
            background-color: #212529;
        }

        /* ── QTabBar ── */
        QTabBar::tab {
            background-color: #2c3238;
            color: #adb5bd;
            padding: 8px 18px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            margin-right: 2px;
        }
        QTabBar::tab:selected {
            background-color: #2563eb;
            color: #ffffff;
            font-weight: bold;
        }
        QTabWidget::pane {
            border: 1px solid #495057;
            background-color: #212529;
        }

        /* ── QGroupBox ── */
        QGroupBox {
            border: 1px solid #495057;
            border-radius: 6px;
            margin-top: 1.2ex;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 5px;
            color: #93c5fd;
            font-weight: bold;
        }

        /* ── QProgressBar ── */
        QProgressBar {
            background-color: #2c3238;
            border: 1px solid #495057;
            border-radius: 4px;
            text-align: center;
            color: #ffffff;
        }
        QProgressBar::chunk {
            background-color: #2563eb;
            border-radius: 3px;
        }

        /* ── QSlider ── */
        QSlider::groove:horizontal {
            height: 6px;
            background: #495057;
            border-radius: 3px;
        }
        QSlider::sub-page:horizontal {
            background: #2563eb;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #ffffff;
            border: 1px solid #2563eb;
            width: 16px;
            margin-top: -5px;
            margin-bottom: -5px;
            border-radius: 8px;
        }

        /* ── QToolTip (선명하고 큰 고대비 말풍선 도움말) ── */
        QToolTip {
            background-color: #0f172a;
            color: #f8fafc;
            border: 1.5px solid #38bdf8;
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 13px;
            font-weight: bold;
        }
    """


def get_light_stylesheet() -> str:
    """Crisp light mode stylesheet with high readability."""
    return """
        * {
            font-size: 13px;
            font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
        }
        QWidget {
            background-color: #f8fafc;
            color: #0f172a;
        }
        QMainWindow {
            background-color: #f1f5f9;
        }

        /* ── QComboBox (고대비 라이트 스타일: 짙은 텍스트 + 순백 배경 + 명확한 테두리) ── */
        QComboBox {
            background-color: #ffffff;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            border-radius: 5px;
            padding: 5px 10px;
            min-height: 24px;
        }
        QComboBox:hover {
            border: 1px solid #2563eb;
            background-color: #f8fafc;
        }
        QComboBox:focus {
            border: 1.5px solid #2563eb;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 25px;
            border-left: 1px solid #cbd5e1;
        }
        QComboBox QAbstractItemView {
            background-color: #ffffff;
            color: #0f172a;
            selection-background-color: #2563eb;
            selection-color: #ffffff;
            border: 1px solid #cbd5e1;
            padding: 4px;
        }

        /* ── QLineEdit & QTextEdit ── */
        QLineEdit, QTextEdit, QPlainTextEdit {
            background-color: #ffffff;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            border-radius: 4px;
            padding: 5px;
        }
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
            border: 1.5px solid #2563eb;
        }

        /* ── QListWidget & QTableWidget ── */
        QListWidget, QTableWidget {
            background-color: #ffffff;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            border-radius: 4px;
        }
        QListWidget::item:selected, QTableWidget::item:selected {
            background-color: #2563eb;
            color: #ffffff;
        }

        /* ── QPushButton (기본 버튼) ── */
        QPushButton {
            background-color: #ffffff;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            border-radius: 5px;
            padding: 6px 12px;
        }
        QPushButton:hover {
            background-color: #f1f5f9;
            border-color: #94a3b8;
        }
        QPushButton:pressed {
            background-color: #e2e8f0;
        }

        /* ── QTabBar ── */
        QTabBar::tab {
            background-color: #e2e8f0;
            color: #475569;
            padding: 8px 18px;
            border-top-left-radius: 6px;
            border-top-right-radius: 6px;
            margin-right: 2px;
        }
        QTabBar::tab:selected {
            background-color: #2563eb;
            color: #ffffff;
            font-weight: bold;
        }
        QTabWidget::pane {
            border: 1px solid #cbd5e1;
            background-color: #ffffff;
        }

        /* ── QGroupBox ── */
        QGroupBox {
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            margin-top: 1.2ex;
            padding-top: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 5px;
            color: #1e40af;
            font-weight: bold;
        }

        /* ── QProgressBar ── */
        QProgressBar {
            background-color: #e2e8f0;
            border: 1px solid #cbd5e1;
            border-radius: 4px;
            text-align: center;
            color: #0f172a;
        }
        QProgressBar::chunk {
            background-color: #2563eb;
            border-radius: 3px;
        }

        /* ── QSlider ── */
        QSlider::groove:horizontal {
            height: 6px;
            background: #cbd5e1;
            border-radius: 3px;
        }
        QSlider::sub-page:horizontal {
            background: #2563eb;
            border-radius: 3px;
        }
        QSlider::handle:horizontal {
            background: #ffffff;
            border: 1px solid #2563eb;
            width: 16px;
            margin-top: -5px;
            margin-bottom: -5px;
            border-radius: 8px;
        }

        /* ── QToolTip (선명하고 큰 고대비 말풍선 도움말) ── */
        QToolTip {
            background-color: #ffffff;
            color: #0f172a;
            border: 1.5px solid #0284c7;
            border-radius: 6px;
            padding: 8px 12px;
            font-size: 13px;
            font-weight: bold;
        }
    """


def apply_app_theme(app: QApplication) -> None:
    """Applies Fusion style and responsive high-contrast theme depending on OS dark/light mode."""
    try:
        app.setStyle("Fusion")
    except Exception as e:
        print(f"[ThemeManager] setStyle error: {e}")

    try:
        hints = app.styleHints()
        is_dark = (hints.colorScheme() == Qt.ColorScheme.Dark)
    except Exception:
        is_dark = False

    sheet = get_dark_stylesheet() if is_dark else get_light_stylesheet()
    app.setStyleSheet(sheet)


def setup_theme_listener(app: QApplication) -> None:
    """Listens for OS-level theme change events (e.g. sunset dark mode) and dynamically updates styles."""
    apply_app_theme(app)
    try:
        hints = app.styleHints()
        hints.colorSchemeChanged.connect(lambda scheme: apply_app_theme(app))
    except Exception as e:
        print(f"[ThemeManager] colorSchemeChanged listener warning: {e}")
