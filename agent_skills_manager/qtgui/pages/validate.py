"""Validate page: structure / metadata / duplicate / secret findings."""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableView,
)

from .. import services
from ..models import ValidationTableModel
from .base import Page


class ValidatePage(Page):
    def __init__(self, main) -> None:
        super().__init__(main)
        self.add_header("Validate", "Check skill structure, metadata, duplicate names, and possible secrets.")

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.location = QComboBox()
        self.location.addItems(["local", "repo"])
        self.target = QComboBox()
        self.target.addItem("All targets", None)
        run = QPushButton("Validate")
        run.setObjectName("primary")
        run.clicked.connect(self._validate)
        controls.addWidget(QLabel("Location"))
        controls.addWidget(self.location)
        controls.addWidget(QLabel("Target"))
        controls.addWidget(self.target)
        controls.addWidget(run)
        controls.addStretch(1)
        self.show_errors = QCheckBox("Errors")
        self.show_warnings = QCheckBox("Warnings")
        self.show_secrets = QCheckBox("Secrets")
        for box in (self.show_errors, self.show_warnings, self.show_secrets):
            box.setChecked(True)
            box.toggled.connect(self._apply_filter)
            controls.addWidget(box)
        self.layout_v.addLayout(controls)

        self.model = ValidationTableModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.doubleClicked.connect(lambda _=None: self._open_file())
        self.layout_v.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.summary = QLabel("Run validation to see findings.")
        self.summary.setProperty("muted", True)
        actions.addWidget(self.summary)
        actions.addStretch(1)
        open_btn = QPushButton("Open file")
        open_btn.clicked.connect(self._open_file)
        copy_btn = QPushButton("Copy path")
        copy_btn.clicked.connect(self._copy_path)
        actions.addWidget(open_btn)
        actions.addWidget(copy_btn)
        self.layout_v.addLayout(actions)

    def refresh(self) -> None:
        # Keep the target dropdown in sync with the configured targets.
        self.main.run_callable(services.load_target_statuses, self._fill_targets, description="Loading targets")

    def _fill_targets(self, targets) -> None:
        current = self.target.currentData()
        self.target.blockSignals(True)
        self.target.clear()
        self.target.addItem("All targets", None)
        for target in targets:
            self.target.addItem(target.name, target.name)
        index = self.target.findData(current)
        self.target.setCurrentIndex(index if index >= 0 else 0)
        self.target.blockSignals(False)

    def _validate(self) -> None:
        location = self.location.currentText()
        target = self.target.currentData()
        self.main.run_callable(
            lambda: services.run_validation(location, target),
            self._apply_findings,
            description="Validating",
        )

    def _apply_findings(self, findings: List[services.ValidationFinding]) -> None:
        self.model.set_findings(findings)
        self._apply_filter()
        errors = sum(1 for f in findings if f.severity == "error")
        secrets = sum(1 for f in findings if f.kind == "secret")
        warnings = sum(1 for f in findings if f.severity == "warning" and f.kind != "secret")
        self.summary.setText(f"{errors} errors · {warnings} warnings · {secrets} possible secrets")

    def _apply_filter(self) -> None:
        self.model.set_filter(self.show_errors.isChecked(), self.show_warnings.isChecked(), self.show_secrets.isChecked())

    def _selected(self) -> Optional[services.ValidationFinding]:
        indexes = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        return self.model.finding_at(indexes[0].row()) if indexes else None

    def _open_file(self) -> None:
        finding = self._selected()
        if finding and finding.path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(finding.path))

    def _copy_path(self) -> None:
        finding = self._selected()
        if finding and finding.path:
            QApplication.clipboard().setText(finding.path)
            self.main.set_status(f"Copied: {finding.path}")
