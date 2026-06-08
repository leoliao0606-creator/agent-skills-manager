"""Logs page: the shared command-output pane (fallback / debug surface)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QFileDialog, QHBoxLayout, QMessageBox, QPushButton

from ..widgets import LogView
from .base import Page


class LogsPage(Page):
    def __init__(self, main, log_view: LogView) -> None:
        super().__init__(main)
        self.add_header("Logs", "Output from every Apply / restore command runs here.")
        self.log_view = log_view
        self.layout_v.addWidget(self.log_view, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        clear = QPushButton("Clear")
        clear.clicked.connect(self.log_view.clear)
        copy = QPushButton("Copy")
        copy.clicked.connect(self.log_view.copy_all)
        save = QPushButton("Save…")
        save.clicked.connect(self._save)
        autoscroll = QCheckBox("Autoscroll")
        autoscroll.setChecked(True)
        autoscroll.toggled.connect(self.log_view.set_autoscroll)
        actions.addWidget(clear)
        actions.addWidget(copy)
        actions.addWidget(save)
        actions.addStretch(1)
        actions.addWidget(autoscroll)
        self.layout_v.addLayout(actions)

    def _save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save log", "agent-skills.log", "Log files (*.log *.txt)")
        if not path:
            return
        try:
            Path(path).write_text(self.log_view.toPlainText(), encoding="utf-8")
        except OSError as exc:  # pragma: no cover - surfaced to the user
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.main.set_status(f"Saved log to {path}")
