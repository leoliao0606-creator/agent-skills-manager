"""Apply the bundled light QSS stylesheet to the application."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

_STYLE_PATH = Path(__file__).parent / "resources" / "style.qss"


def load_stylesheet() -> str:
    try:
        return _STYLE_PATH.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - missing resource should not be fatal
        return ""


def apply_theme(app: QApplication) -> None:
    qss = load_stylesheet()
    if qss:
        app.setStyleSheet(qss)
