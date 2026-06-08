"""Application entry point for the Qt GUI."""
from __future__ import annotations

import argparse
import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .theme import apply_theme

# Preferred UI fonts, best first. Qt picks the first that is installed; the final
# generic family guarantees a sane fallback on a bare Linux box.
_UI_FONTS = ["SF Pro Text", ".AppleSystemUIFont", "Inter", "Segoe UI", "Noto Sans", "sans-serif"]


def _apply_font(app: QApplication) -> None:
    font = QFont(_UI_FONTS)
    font.setPointSize(10)
    app.setFont(font)


def run(args: argparse.Namespace) -> None:
    del args  # the GUI takes no arguments today

    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication(sys.argv)

    # Fusion renders QSS consistently across platforms; the native macOS/Windows
    # styles override paddings and colours we set in the stylesheet.
    app.setStyle("Fusion")
    _apply_font(app)
    apply_theme(app)

    # Track the OS light/dark switch live (Qt 6.5+ emits this signal).
    try:
        app.styleHints().colorSchemeChanged.connect(lambda _scheme: apply_theme(app))
    except Exception:  # pragma: no cover - older Qt without the signal
        pass

    window = MainWindow()
    window.resize(1180, 760)
    window.show()

    if owns_app:
        raise SystemExit(app.exec())
