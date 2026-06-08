"""Shared page scaffolding: a base Page class and small card/header helpers."""
from __future__ import annotations

from typing import Optional

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..widgets import StatusBadge


def add_card_shadow(widget: QWidget) -> None:
    """Give a card a soft, diffuse drop shadow so it floats like a macOS panel."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(24)
    shadow.setColor(QColor(0, 0, 0, 38))
    shadow.setOffset(0, 2)
    widget.setGraphicsEffect(shadow)


class Page(QWidget):
    """Base class for nav pages. Subclasses build their UI and may override refresh()."""

    def __init__(self, main: "QWidget") -> None:
        super().__init__()
        self.main = main
        self.layout_v = QVBoxLayout(self)
        self.layout_v.setContentsMargins(24, 20, 24, 20)
        self.layout_v.setSpacing(14)

    def add_header(self, title: str, subtitle: str = "") -> None:
        label = QLabel(title)
        label.setObjectName("pageTitle")
        self.layout_v.addWidget(label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("pageSubtitle")
            sub.setWordWrap(True)
            self.layout_v.addWidget(sub)

    def refresh(self) -> None:  # pragma: no cover - overridden where needed
        """Called when the page becomes visible. No-op by default."""


class Card(QFrame):
    """A small dashboard card with a title, big value, optional detail + badge."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setProperty("card", True)
        add_card_shadow(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        title_label = QLabel(title.upper())
        title_label.setObjectName("cardTitle")
        layout.addWidget(title_label)

        self.value_label = QLabel("—")
        self.value_label.setObjectName("cardValue")
        self.value_label.setWordWrap(True)
        layout.addWidget(self.value_label)

        self.detail_label = QLabel("")
        self.detail_label.setProperty("muted", True)
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)

        self.badge = StatusBadge("", "muted")
        layout.addWidget(self.badge)
        layout.addStretch(1)

    def set_value(self, value: str, detail: str = "", level: str = "muted", badge_text: Optional[str] = None) -> None:
        self.value_label.setText(value)
        self.detail_label.setText(detail)
        self.detail_label.setVisible(bool(detail))
        if badge_text is None:
            self.badge.setVisible(False)
        else:
            self.badge.setVisible(True)
            self.badge.set_status(level, badge_text)
