"""Targets page: edit the configured skill targets and save them."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QTableView,
)

from .. import services
from ..models import TargetTableModel
from ..services import TargetStatus
from .base import Page


class TargetsPage(Page):
    def __init__(self, main) -> None:
        super().__init__(main)
        self.add_header(
            "Targets",
            "Map local skill directories to subdirectories in your repo. "
            "Removing a target here only changes config — it never deletes any files.",
        )

        self.model = TargetTableModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(32)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.layout_v.addWidget(self.table, 1)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        add = QPushButton("Add target…")
        add.clicked.connect(self._add_target)
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self._remove_selected)
        browse = QPushButton("Browse local…")
        browse.clicked.connect(self._browse_local)
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        reset = QPushButton("Reset")
        reset.clicked.connect(self.refresh)
        for button in (add, remove, browse):
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        toolbar.addWidget(reset)
        toolbar.addWidget(save)
        self.layout_v.addLayout(toolbar)

    def refresh(self) -> None:
        self.main.run_callable(services.load_target_statuses, self.model.set_rows, description="Loading targets")

    def _selected_row(self) -> int:
        indexes = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        return indexes[0].row() if indexes else -1

    def _add_target(self) -> None:
        name, ok = QInputDialog.getText(self, "Add target", "Target name (e.g. my-agent):")
        name = name.strip()
        if not ok or not name:
            return
        self.model.add_row(TargetStatus(
            name=name,
            enabled=True,
            local_dir=f"~/.{name}/skills",
            repo_dir=f"{name}-skills",
            local_dir_expanded="",
            repo_dir_expanded="",
            local_skills=0,
            repo_skills=0,
            status="new",
        ))

    def _remove_selected(self) -> None:
        row = self._selected_row()
        if row < 0:
            return
        target = self.model.row_at(row)
        if target and QMessageBox.question(
            self, "Remove target",
            f"Remove target '{target.name}' from config?\n\nThis does not delete any files on disk.",
        ) != QMessageBox.Yes:
            return
        self.model.remove_row(row)

    def _browse_local(self) -> None:
        row = self._selected_row()
        target = self.model.row_at(row) if row >= 0 else None
        if target is None:
            QMessageBox.information(self, "Browse", "Select a target row first.")
            return
        path = QFileDialog.getExistingDirectory(self, "Choose local skills directory", target.local_dir)
        if path:
            self.model.setData(self.model.index(row, 2), path)

    def _save(self) -> None:
        try:
            path = services.save_targets(self.model.to_targets())
        except Exception as exc:  # pragma: no cover - surfaced to the user
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.main.set_status(f"Saved targets to {path}")
        self.refresh()
