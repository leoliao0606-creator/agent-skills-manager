"""Sync page: read-only previews, then gated, confirmed Apply via the CLI."""
from __future__ import annotations

from typing import Dict, List, Tuple

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
)

from .. import services
from ..models import FileChangeTableModel
from ..services import FileChange, SyncPreview
from ..widgets import confirm_force, confirm_mirror
from .base import Page


class SyncPage(Page):
    def __init__(self, main) -> None:
        super().__init__(main)
        self.add_header(
            "Sync",
            "Preview is always safe and read-only. Apply runs the same command as the CLI; "
            "dry-run is on by default.",
        )
        self._fresh: Dict[str, SyncPreview] = {}

        # Preview buttons
        preview_row = QHBoxLayout()
        preview_row.setSpacing(8)
        self.btn_preview_push = QPushButton("Preview Push")
        self.btn_preview_push.setObjectName("primary")
        self.btn_preview_push.clicked.connect(lambda: self._preview("push"))
        self.btn_preview_pull = QPushButton("Preview Pull")
        self.btn_preview_pull.clicked.connect(lambda: self._preview("pull"))
        preview_row.addWidget(self.btn_preview_push)
        preview_row.addWidget(self.btn_preview_pull)
        preview_row.addStretch(1)
        self.layout_v.addLayout(preview_row)

        # Summary + file table
        self.summary = QLabel("Run a preview to see pending changes.")
        self.summary.setTextFormat(self.summary.textFormat())
        self.layout_v.addWidget(self.summary)

        self.model = FileChangeTableModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.layout_v.addWidget(self.table, 1)

        # Advanced options
        options = QGroupBox("Apply options")
        form = QFormLayout(options)
        self.opt_dry_run = QCheckBox("Dry run (preview only — no files written)")
        self.opt_dry_run.setChecked(True)
        self.opt_mirror = QCheckBox("Mirror (delete destination files missing from source)")
        self.opt_force = QCheckBox("Force (overwrite conflicting files)")
        self.opt_strict = QCheckBox("Strict (fail on missing source directories)")
        self.opt_no_pull = QCheckBox("Skip git pull")
        self.opt_no_backup = QCheckBox("Skip backup before pull")
        self.opt_message = QLineEdit("Sync local agent skills")
        self.opt_mirror.toggled.connect(self._on_mirror_toggled)
        self.opt_force.toggled.connect(lambda _=False: self._update_apply_enabled())
        form.addRow(self.opt_dry_run)
        form.addRow(self.opt_mirror)
        form.addRow(self.opt_force)
        form.addRow(self.opt_strict)
        form.addRow(self.opt_no_pull)
        form.addRow(self.opt_no_backup)
        form.addRow(QLabel("Commit message"), self.opt_message)
        self.layout_v.addWidget(options)

        # Apply buttons
        apply_row = QHBoxLayout()
        apply_row.setSpacing(8)
        self.btn_apply_push = QPushButton("Apply Push: Local → Repo")
        self.btn_apply_push.clicked.connect(lambda: self._apply("push"))
        self.btn_apply_pull = QPushButton("Apply Pull: Repo → Local")
        self.btn_apply_pull.clicked.connect(lambda: self._apply("pull"))
        self.btn_apply_sync = QPushButton("Apply Two-way: Pull → Push")
        self.btn_apply_sync.clicked.connect(lambda: self._apply("sync"))
        for button in (self.btn_apply_push, self.btn_apply_pull, self.btn_apply_sync):
            apply_row.addWidget(button)
        apply_row.addStretch(1)
        self.layout_v.addLayout(apply_row)

        self.main.busyChanged.connect(self._on_busy_changed)
        self._update_apply_enabled()

    # --- preview ---
    def _preview(self, direction: str) -> None:
        mirror = self.opt_mirror.isChecked()
        self.main.run_callable(
            lambda: services.build_sync_preview(direction, mirror),
            self._apply_preview,
            description=f"Previewing {direction}",
        )

    def _apply_preview(self, preview: SyncPreview) -> None:
        self._fresh[preview.direction] = preview
        rows: List[Tuple[str, FileChange]] = []
        for target in preview.targets:
            for change in target.files:
                rows.append((target.target, change))
        self.model.set_rows(rows)
        self._set_summary(preview)
        self._update_apply_enabled()

    def _set_summary(self, preview: SyncPreview) -> None:
        deleted = preview.total_deleted
        conflict = preview.total_conflict
        red = "color:#ef4444;font-weight:600;"
        parts = [
            f"<b>{preview.direction.capitalize()}</b>",
            f"Added {preview.total_added}",
            f"Modified {preview.total_modified}",
            f"<span style='{red}'>Deleted {deleted}</span>" if deleted else "Deleted 0",
            f"<span style='{red}'>Conflicts {conflict}</span>" if conflict else "Conflicts 0",
        ]
        text = " &nbsp;·&nbsp; ".join(parts)
        if conflict and not self.opt_force.isChecked():
            text += " &nbsp;—&nbsp; resolve conflicts or enable Force to apply."
        self.summary.setText(text)

    def _on_mirror_toggled(self, _checked: bool) -> None:
        # A mirror change invalidates any preview because the plan differs.
        self._fresh.clear()
        self.model.set_rows([])
        self.summary.setText("Mirror changed — run a preview again.")
        self._update_apply_enabled()

    # --- apply ---
    def _can_apply(self, direction: str) -> bool:
        if direction == "sync":
            previews = [self._fresh.get("push"), self._fresh.get("pull")]
            fresh = [p for p in previews if p is not None]
            if not fresh:
                return False
            return self.opt_force.isChecked() or not any(p.has_conflict for p in fresh)
        preview = self._fresh.get(direction)
        if preview is None:
            return False
        return self.opt_force.isChecked() or not preview.has_conflict

    def _update_apply_enabled(self) -> None:
        busy = getattr(self.main, "busy", False)
        self.btn_apply_push.setEnabled(self._can_apply("push") and not busy)
        self.btn_apply_pull.setEnabled(self._can_apply("pull") and not busy)
        self.btn_apply_sync.setEnabled(self._can_apply("sync") and not busy)

    def _build_argv(self, direction: str) -> List[str]:
        from ..workers import cli_command
        args: List[str] = [direction]
        if self.opt_dry_run.isChecked():
            args.append("--dry-run")
        if self.opt_mirror.isChecked():
            args += ["--mirror", "--yes"]
        if self.opt_force.isChecked():
            args.append("--force")
        if self.opt_strict.isChecked():
            args.append("--strict")
        if self.opt_no_pull.isChecked():
            args.append("--no-pull")
        if direction in ("pull", "sync") and self.opt_no_backup.isChecked():
            args.append("--no-backup")
        if direction in ("push", "sync"):
            args += ["-m", self.opt_message.text().strip() or "Sync local agent skills"]
        return cli_command(*args)

    def _apply(self, direction: str) -> None:
        dry_run = self.opt_dry_run.isChecked()
        if self.opt_force.isChecked() and not confirm_force(self):
            return
        confirm_direction = "push" if direction == "sync" else direction
        if self.opt_mirror.isChecked() and not dry_run and not confirm_mirror(self, confirm_direction):
            return
        argv = self._build_argv(direction)
        self.main.navigate("Logs")
        self.main.run_command(argv, description=f"{direction}{' (dry run)' if dry_run else ''}", on_finished=self._after_apply)

    def _after_apply(self, _code: int) -> None:
        # State on disk may have changed; force a fresh preview before any re-apply.
        if not self.opt_dry_run.isChecked():
            self._fresh.clear()
            self.model.set_rows([])
            self.summary.setText("Applied. Run a preview to see the new state.")
        self._update_apply_enabled()

    def _on_busy_changed(self, busy: bool) -> None:
        self.btn_preview_push.setEnabled(not busy)
        self.btn_preview_pull.setEnabled(not busy)
        self._update_apply_enabled()
