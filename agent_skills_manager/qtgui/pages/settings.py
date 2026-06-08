"""Settings page: edit scalar config + excludes, switch profiles."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
)

from .. import services
from ..services import ConfigSettings
from ..widgets import PathPicker
from .base import Page


class SettingsPage(Page):
    def __init__(self, main) -> None:
        super().__init__(main)
        self.add_header("Settings", "Repository, remote, and sync settings. Targets are edited on the Targets page.")

        form = QFormLayout()
        self.profile = QComboBox()
        self.profile.currentTextChanged.connect(self._on_profile_changed)
        self.repo_dir = PathPicker(placeholder="~/agent-skills-library")
        self.remote_url = QLineEdit()
        self.default_branch = QLineEdit()
        self.backups_dir = PathPicker()
        self.excludes = QPlainTextEdit()
        self.excludes.setPlaceholderText("One ignore pattern per line")
        self.excludes.setFixedHeight(140)
        form.addRow("Profile", self.profile)
        form.addRow("Local repo path", self.repo_dir)
        form.addRow("Remote URL", self.remote_url)
        form.addRow("Default branch", self.default_branch)
        form.addRow("Backups directory", self.backups_dir)
        form.addRow("Excludes", self.excludes)
        self.layout_v.addLayout(form)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        reload_btn = QPushButton("Reload")
        reload_btn.clicked.connect(self.refresh)
        open_cfg = QPushButton("Open config file")
        open_cfg.clicked.connect(self._open_config)
        export = QPushButton("Export summary…")
        export.clicked.connect(self._export)
        actions.addWidget(save)
        actions.addWidget(reload_btn)
        actions.addStretch(1)
        actions.addWidget(open_cfg)
        actions.addWidget(export)
        self.layout_v.addLayout(actions)
        self.layout_v.addStretch(1)

        self._config_path = ""
        self._fill_profiles()

    def _fill_profiles(self) -> None:
        self.profile.blockSignals(True)
        self.profile.clear()
        self.profile.addItems(services.list_profiles())
        active = services.active_profile()
        index = self.profile.findText(active)
        self.profile.setCurrentIndex(index if index >= 0 else 0)
        self.profile.blockSignals(False)

    def refresh(self) -> None:
        self._fill_profiles()
        settings = services.load_config_settings()
        self._apply(settings)

    def _apply(self, settings: ConfigSettings) -> None:
        self._config_path = settings.config_path
        self.repo_dir.setText(settings.repo_dir)
        self.remote_url.setText(settings.remote_url)
        self.default_branch.setText(settings.default_branch)
        self.backups_dir.setText(settings.backups_dir)
        self.excludes.setPlainText("\n".join(settings.excludes))

    def _collect(self) -> ConfigSettings:
        excludes = [line.strip() for line in self.excludes.toPlainText().splitlines() if line.strip()]
        return ConfigSettings(
            repo_dir=self.repo_dir.text().strip(),
            remote_url=self.remote_url.text().strip(),
            default_branch=self.default_branch.text().strip() or "main",
            backups_dir=self.backups_dir.text().strip(),
            excludes=excludes,
            config_path=self._config_path,
            config_exists=True,
        )

    def _save(self) -> None:
        try:
            path = services.save_config_settings(self._collect())
        except Exception as exc:  # pragma: no cover - surfaced to the user
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        self.main.set_status(f"Saved settings to {path}")

    def _on_profile_changed(self, name: str) -> None:
        if not name:
            return
        services.set_active_profile(name)
        self._apply(services.load_config_settings())
        self.main.set_status(f"Active profile: {name} (switch pages to refresh their data)")

    def _open_config(self) -> None:
        path = Path(self._config_path)
        target = path if path.exists() else path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export summary", "agent-skills-summary.txt", "Text files (*.txt)")
        if not path:
            return
        try:
            Path(path).write_text(services.export_summary(), encoding="utf-8")
        except OSError as exc:  # pragma: no cover - surfaced to the user
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        self.main.set_status(f"Exported summary to {path}")
