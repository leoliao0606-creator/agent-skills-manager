"""Backups page: list backups and restore them (dry-run first)."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from .. import services
from ..services import BackupEntry
from ..widgets import confirm
from ..workers import cli_command
from .base import Page


class BackupsPage(Page):
    def __init__(self, main) -> None:
        super().__init__(main)
        self.add_header("Backups", "Local skill directories backed up before pulls. Always restore with a dry-run first.")
        self._entries: List[BackupEntry] = []
        self._dryrun_ok_path: Optional[str] = None

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Date", "Target", "Size", "Path"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.layout_v.addWidget(self.table, 1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        open_folder = QPushButton("Open folder")
        open_folder.clicked.connect(self._open_folder)
        self.btn_dry = QPushButton("Restore (dry-run)")
        self.btn_dry.clicked.connect(self._restore_dry)
        self.btn_restore = QPushButton("Restore…")
        self.btn_restore.setObjectName("danger")
        self.btn_restore.clicked.connect(self._restore)
        actions.addWidget(refresh)
        actions.addWidget(open_folder)
        actions.addStretch(1)
        actions.addWidget(self.btn_dry)
        actions.addWidget(self.btn_restore)
        self.layout_v.addLayout(actions)

        self.hint = QLabel("Select a backup, run a dry-run, then restore.")
        self.hint.setProperty("muted", True)
        self.layout_v.addWidget(self.hint)
        self._update_buttons()

    def refresh(self) -> None:
        self.main.run_callable(services.list_backups, self._apply, description="Loading backups")

    def _apply(self, entries: List[BackupEntry]) -> None:
        self._entries = entries
        self._dryrun_ok_path = None
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            for col, value in enumerate((entry.date, entry.target, entry.size_human, entry.path)):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, entry.path)
                self.table.setItem(row, col, item)
        self._update_buttons()

    def _selected(self) -> Optional[BackupEntry]:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        index = rows[0].row()
        return self._entries[index] if 0 <= index < len(self._entries) else None

    def _on_selection_changed(self) -> None:
        # Changing selection invalidates the preview-first guard.
        entry = self._selected()
        if entry is None or entry.path != self._dryrun_ok_path:
            self._dryrun_ok_path = None
        self._update_buttons()

    def _update_buttons(self) -> None:
        entry = self._selected()
        self.btn_dry.setEnabled(entry is not None)
        self.btn_restore.setEnabled(entry is not None and entry.path == self._dryrun_ok_path)

    def _open_folder(self) -> None:
        entry = self._selected()
        target = Path(entry.path).parent if entry else None
        if target is None and self._entries:
            target = Path(self._entries[0].path).parent.parent
        if target:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _restore_dry(self) -> None:
        entry = self._selected()
        if entry is None:
            return
        argv = cli_command("restore-backup", entry.path, "--target", entry.target, "--dry-run")
        path = entry.path
        self.main.navigate("Logs")
        self.main.run_command(
            argv,
            description=f"restore {entry.target} (dry run)",
            on_finished=lambda code: self._after_dry(code, path),
        )

    def _after_dry(self, code: int, path: str) -> None:
        if code == 0:
            self._dryrun_ok_path = path
            self.hint.setText("Dry-run complete. The Restore… button is now enabled for this backup.")
        self._update_buttons()

    def _restore(self) -> None:
        entry = self._selected()
        if entry is None or entry.path != self._dryrun_ok_path:
            return
        if not confirm(
            self, "Restore backup",
            f"Restore '{entry.target}' from\n{entry.path}\n\n"
            "This mirrors the backup into your local skill directory and may delete "
            "local files that are not in the backup.\n\nContinue?",
        ):
            return
        argv = cli_command("restore-backup", entry.path, "--target", entry.target, "--yes")
        self.main.navigate("Logs")
        self.main.run_command(argv, description=f"restore {entry.target}", on_finished=lambda _code: self.refresh())
