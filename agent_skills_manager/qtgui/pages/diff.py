"""Diff page: per-target file changes with a detail panel (file-level, v1)."""
from __future__ import annotations

from typing import Dict, List, Tuple

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .. import services
from ..models import FileChangeTableModel
from ..services import FileChange, SyncPreview, TargetPlanSummary
from .base import Page


class DiffPage(Page):
    def __init__(self, main) -> None:
        super().__init__(main)
        self.add_header("Diff", "Compare local and repo trees per target. File-level changes only.")
        self._summaries: Dict[str, TargetPlanSummary] = {}

        columns = QHBoxLayout()
        columns.setSpacing(14)

        # Left: controls + target list
        left = QVBoxLayout()
        controls = QHBoxLayout()
        self.direction = QComboBox()
        self.direction.addItems(["push", "pull"])
        self.direction.currentTextChanged.connect(lambda _=None: self.refresh())
        self.mirror = QCheckBox("Mirror")
        self.mirror.toggled.connect(lambda _=False: self.refresh())
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        controls.addWidget(QLabel("Direction"))
        controls.addWidget(self.direction)
        controls.addWidget(self.mirror)
        controls.addStretch(1)
        controls.addWidget(refresh)
        left.addLayout(controls)
        self.target_list = QListWidget()
        self.target_list.currentTextChanged.connect(self._show_target)
        left.addWidget(self.target_list, 1)
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setFixedWidth(280)
        columns.addWidget(left_w)

        # Middle: changes table
        self.model = FileChangeTableModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setColumnHidden(1, True)  # single target shown at a time
        self.table.selectionModel().currentRowChanged.connect(self._show_detail)
        columns.addWidget(self.table, 1)

        # Right: file detail
        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(self._heading("File detail"))
        self.detail_status = QLabel("—")
        self.detail_path = QLabel("")
        self.detail_source = QLabel("")
        self.detail_dest = QLabel("")
        for label in (self.detail_status, self.detail_path, self.detail_source, self.detail_dest):
            label.setWordWrap(True)
            label.setProperty("muted", True)
            right.addWidget(label)
        right.addStretch(1)
        right_w = QWidget()
        right_w.setLayout(right)
        right_w.setFixedWidth(320)
        columns.addWidget(right_w)

        self.layout_v.addLayout(columns, 1)

    @staticmethod
    def _heading(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("cardTitle")
        return label

    def refresh(self) -> None:
        direction = self.direction.currentText()
        mirror = self.mirror.isChecked()
        self.main.run_callable(
            lambda: services.build_sync_preview(direction, mirror),
            self._apply_preview,
            description=f"Diffing {direction}",
        )

    def _apply_preview(self, preview: SyncPreview) -> None:
        self._summaries = {t.target: t for t in preview.targets}
        self.target_list.blockSignals(True)
        self.target_list.clear()
        for target in preview.targets:
            self.target_list.addItem(f"{target.target}  ({target.change_count})")
        self.target_list.blockSignals(False)
        if preview.targets:
            self.target_list.setCurrentRow(0)
            self._show_target(self.target_list.item(0).text())
        else:
            self.model.set_rows([])

    def _show_target(self, label: str) -> None:
        name = label.split("  (")[0] if label else ""
        summary = self._summaries.get(name)
        rows: List[Tuple[str, FileChange]] = []
        if summary:
            rows = [(summary.target, change) for change in summary.files]
        self.model.set_rows(rows)

    def _show_detail(self, current, _previous) -> None:
        item = self.model.change_at(current.row()) if current and current.isValid() else None
        if item is None:
            self.detail_status.setText("—")
            for label in (self.detail_path, self.detail_source, self.detail_dest):
                label.setText("")
            return
        _target, change = item
        self.detail_status.setText(f"Status: {change.status}")
        self.detail_path.setText(f"Path: {change.path}")
        self.detail_source.setText(f"Source: {change.source}")
        self.detail_dest.setText(f"Destination: {change.destination}")
