"""Build and apply the macOS-flavoured stylesheet.

``resources/style.qss`` is a template full of ``@@TOKEN@@`` placeholders. We pick
a light or dark palette from the system colour scheme, substitute the tokens, and
hand the result to ``QApplication.setStyleSheet``. Re-running ``apply_theme`` when
the OS flips light/dark keeps the window in sync.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

_RESOURCES = Path(__file__).parent / "resources"
_STYLE_PATH = _RESOURCES / "style.qss"
_CHECK_ICON = (_RESOURCES / "check.svg").as_posix()

# macOS "Aqua" light palette.
LIGHT: Dict[str, str] = {
    "BG": "#f2f2f7",
    "TITLEBAR_BG": "#ececf0",
    "SIDEBAR_BG": "#e8e8ec",
    "CARD_BG": "#ffffff",
    "CARD_BORDER": "#e2e2e7",
    "TEXT": "#1d1d1f",
    "MUTED": "#86868b",
    "SEPARATOR": "#d8d8dd",
    "ACCENT": "#007aff",
    "ACCENT_HOVER": "#0a6fe0",
    "ACCENT_PRESSED": "#0a5fc0",
    "ACCENT_DISABLED": "#a6cdff",
    "ON_ACCENT": "#ffffff",
    "NAV_HOVER": "#dcdce1",
    "DANGER": "#ff3b30",
    "DANGER_DISABLED": "#f3b6b3",
    "BTN_BG": "#ffffff",
    "BTN_HOVER": "#f3f3f5",
    "BTN_PRESSED": "#e7e7eb",
    "BTN_BORDER": "#cfcfd6",
    "INPUT_BG": "#ffffff",
    "INPUT_BORDER": "#cfcfd6",
    "SELECTION_BG": "#d6e4ff",
    "TABLE_HEADER_BG": "#f5f5f7",
    "OK_BG": "#e3f7ec", "OK_FG": "#1a7f4b",
    "WARN_BG": "#fdf0dd", "WARN_FG": "#9a6700",
    "ERROR_BG": "#fde7e6", "ERROR_FG": "#c0392f",
    "MUTED_BG": "#ececf0",
    "LOG_BG": "#1e1e1e",
    "LOG_TEXT": "#e6e6e6",
    "SCROLLBAR": "#c4c4cc",
    "SCROLLBAR_HOVER": "#aeaeb6",
    "CHECK_ICON": _CHECK_ICON,
}

# macOS dark palette.
DARK: Dict[str, str] = {
    "BG": "#1e1e1e",
    "TITLEBAR_BG": "#2a2a2c",
    "SIDEBAR_BG": "#252527",
    "CARD_BG": "#2c2c2e",
    "CARD_BORDER": "#3a3a3c",
    "TEXT": "#f5f5f7",
    "MUTED": "#98989d",
    "SEPARATOR": "#3a3a3c",
    "ACCENT": "#0a84ff",
    "ACCENT_HOVER": "#3b9bff",
    "ACCENT_PRESSED": "#0a6fe0",
    "ACCENT_DISABLED": "#1d4e80",
    "ON_ACCENT": "#ffffff",
    "NAV_HOVER": "#323234",
    "DANGER": "#ff453a",
    "DANGER_DISABLED": "#7a3330",
    "BTN_BG": "#3a3a3c",
    "BTN_HOVER": "#434345",
    "BTN_PRESSED": "#4d4d4f",
    "BTN_BORDER": "#48484a",
    "INPUT_BG": "#1c1c1e",
    "INPUT_BORDER": "#48484a",
    "SELECTION_BG": "#0a4a8f",
    "TABLE_HEADER_BG": "#323234",
    "OK_BG": "#16361f", "OK_FG": "#41d27e",
    "WARN_BG": "#3a2e16", "WARN_FG": "#e0a23a",
    "ERROR_BG": "#3a1f1d", "ERROR_FG": "#ff6961",
    "MUTED_BG": "#3a3a3c",
    "LOG_BG": "#161617",
    "LOG_TEXT": "#e6e6e6",
    "SCROLLBAR": "#4d4d4f",
    "SCROLLBAR_HOVER": "#5e5e60",
    "CHECK_ICON": _CHECK_ICON,
}


def _load_template() -> str:
    try:
        return _STYLE_PATH.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - missing resource should not be fatal
        return ""


def is_dark(app: QApplication) -> bool:
    """True when the OS is using a dark colour scheme.

    ``QStyleHints.colorScheme()`` exists from Qt 6.5; older builds fall back to
    light, which is a safe default.
    """
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:  # pragma: no cover - very old Qt
        return False


def build_stylesheet(dark: bool) -> str:
    palette = DARK if dark else LIGHT
    qss = _load_template()
    for token, value in palette.items():
        qss = qss.replace(f"@@{token}@@", value)
    return qss


def apply_theme(app: QApplication) -> None:
    qss = build_stylesheet(is_dark(app))
    if qss:
        app.setStyleSheet(qss)
