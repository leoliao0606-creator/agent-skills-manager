"""Compare page: preview and compare two targets' skills, then copy A<->B.

Modelled on the Diff page's three-column layout. Each side picks a target and a
local/repo location independently, so the same target's local-vs-repo can also be
compared. The copy action runs through the ``copy-skill`` CLI verb so it shares
the exact code path, confirmation, and backup behaviour as the command line.
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ... import gui
from .. import services
from ..models import SkillComparisonTableModel
from ..services import SkillComparisonRow, TargetComparison
from ..widgets import confirm
from .base import Page


class ComparePage(Page):
    def __init__(self, main) -> None:
        super().__init__(main)
        self.add_header("Compare", "Preview and compare two targets' skills, then copy a skill from one to the other.")
        self._comparison: Optional[TargetComparison] = None

        # --- selectors row ---
        selectors = QHBoxLayout()
        selectors.setSpacing(8)
        self.target_a = QComboBox()
        self.loc_a = self._location_combo()
        self.target_b = QComboBox()
        self.loc_b = self._location_combo()
        compare_btn = QPushButton("Compare")
        compare_btn.clicked.connect(self.refresh)
        selectors.addWidget(QLabel("A"))
        selectors.addWidget(self.target_a, 1)
        selectors.addWidget(self.loc_a)
        selectors.addSpacing(12)
        selectors.addWidget(QLabel("B"))
        selectors.addWidget(self.target_b, 1)
        selectors.addWidget(self.loc_b)
        selectors.addStretch(1)
        selectors.addWidget(compare_btn)
        self.layout_v.addLayout(selectors)

        columns = QHBoxLayout()
        columns.setSpacing(14)

        # --- left: comparison table ---
        self.model = SkillComparisonTableModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.selectionModel().currentRowChanged.connect(self._show_detail)
        columns.addWidget(self.table, 1)

        # --- right: detail + copy actions ---
        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(self._heading("Skill detail"))
        self.detail_a = QLabel("—")
        self.detail_b = QLabel("—")
        for label in (self.detail_a, self.detail_b):
            label.setWordWrap(True)
            label.setProperty("muted", True)
            right.addWidget(label)
        right.addWidget(self._heading("SKILL.md diff"))
        self.diff_view = QPlainTextEdit()
        self.diff_view.setReadOnly(True)
        self.diff_view.setObjectName("diffView")
        right.addWidget(self.diff_view, 1)

        buttons = QHBoxLayout()
        self.copy_a_to_b = QPushButton("Copy A → B")
        self.copy_b_to_a = QPushButton("Copy B → A")
        self.copy_a_to_b.clicked.connect(lambda: self._copy("a"))
        self.copy_b_to_a.clicked.connect(lambda: self._copy("b"))
        buttons.addWidget(self.copy_a_to_b)
        buttons.addWidget(self.copy_b_to_a)
        right.addLayout(buttons)

        right_w = QWidget()
        right_w.setLayout(right)
        right_w.setFixedWidth(360)
        columns.addWidget(right_w)

        self.layout_v.addLayout(columns, 1)

        self.main.busyChanged.connect(lambda _busy=False: self._update_buttons())
        self._update_buttons()

    @staticmethod
    def _location_combo() -> QComboBox:
        combo = QComboBox()
        combo.addItems(["local", "repo"])
        return combo

    @staticmethod
    def _heading(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("cardTitle")
        return label

    def refresh(self) -> None:
        self._populate_targets()
        a = self.target_a.currentText()
        b = self.target_b.currentText()
        if not a or not b:
            self.model.set_rows([])
            return
        la = self.loc_a.currentText()
        lb = self.loc_b.currentText()
        self.main.run_callable(
            lambda: services.compare_targets(a, la, b, lb),
            self._apply_comparison,
            description="Comparing",
        )

    def _populate_targets(self) -> None:
        names = [t.name for t in services.load_target_statuses()]
        for combo in (self.target_a, self.target_b):
            if [combo.itemText(i) for i in range(combo.count())] == names:
                continue
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(names)
            if current in names:
                combo.setCurrentText(current)
            combo.blockSignals(False)

    def _apply_comparison(self, comparison: TargetComparison) -> None:
        self._comparison = comparison
        self.model.set_rows(comparison.rows)
        self._show_detail(None, None)

    def _current_row(self) -> Optional[SkillComparisonRow]:
        index = self.table.selectionModel().currentIndex()
        return self.model.row_at(index.row()) if index.isValid() else None

    def _show_detail(self, _current, _previous) -> None:
        row = self._current_row()
        if row is None:
            self.detail_a.setText("—")
            self.detail_b.setText("")
            self.diff_view.setPlainText("")
            self._update_buttons()
            return
        self.detail_a.setText(self._side_text("A", row.a))
        self.detail_b.setText(self._side_text("B", row.b))
        if row.a and row.b:
            self.diff_view.setPlainText(
                services.skill_unified_diff(row.a.skill_file, row.b.skill_file, "A", "B")
                or "(no SKILL.md differences)"
            )
        else:
            self.diff_view.setPlainText("")
        self._update_buttons()

    @staticmethod
    def _side_text(prefix: str, summary) -> str:
        if summary is None:
            return f"{prefix}: (missing)"
        version = summary.version or "-"
        description = summary.description or ""
        return f"{prefix} [{summary.location}]: {summary.name}  v{version}\n{description}"

    def _update_buttons(self) -> None:
        row = self._current_row()
        busy = getattr(self.main, "busy", False)
        self.copy_a_to_b.setEnabled(bool(row and row.a) and not busy)
        self.copy_b_to_a.setEnabled(bool(row and row.b) and not busy)

    def _copy(self, source_side: str) -> None:
        row = self._current_row()
        if row is None:
            return
        src = row.a if source_side == "a" else row.b
        dst_target = self.target_b.currentText() if source_side == "a" else self.target_a.currentText()
        dst_location = self.loc_b.currentText() if source_side == "a" else self.loc_a.currentText()
        if src is None or not dst_target:
            return
        if not confirm(
            self,
            "Copy skill",
            f"Copy '{src.name}' from {src.target} [{src.location}] "
            f"to {dst_target} [{dst_location}]?\n\n"
            "An existing skill at the destination is backed up first.",
        ):
            return
        argv = gui.gui_copy_skill_command(
            f"{src.target}:{src.name}",
            dst_target,
            from_location=src.location,
            to_location=dst_location,
        )
        self.main.run_command(argv, description="Copy skill", on_finished=lambda _code: self.refresh())
