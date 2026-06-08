"""A small coloured pill label used for green/amber/red status."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel


class StatusBadge(QLabel):
    """A rounded status pill. ``level`` is one of ok / warn / error / muted."""

    def __init__(self, text: str = "", level: str = "muted") -> None:
        super().__init__(text)
        self.setProperty("badge", True)
        self.set_status(level, text)

    def set_status(self, level: str, text: str | None = None) -> None:
        if text is not None:
            self.setText(text)
        self.setProperty("level", level)
        # A dynamic-property change needs an explicit re-polish to restyle.
        style = self.style()
        style.unpolish(self)
        style.polish(self)
