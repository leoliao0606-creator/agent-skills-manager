"""Application entry point for the Qt GUI."""
from __future__ import annotations

import argparse
import sys

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .theme import apply_theme


def run(args: argparse.Namespace) -> None:
    del args  # the GUI takes no arguments today

    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication(sys.argv)

    apply_theme(app)

    window = MainWindow()
    window.resize(1180, 760)
    window.show()

    if owns_app:
        raise SystemExit(app.exec())
