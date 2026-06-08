"""Overview dashboard: config / repo / targets status + quick actions."""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton

from .. import services
from ..workers import cli_command
from .base import Card, Page


class OverviewPage(Page):
    def __init__(self, main) -> None:
        super().__init__(main)
        self.add_header("Overview", "A snapshot of your configuration, repository, and skill targets.")

        cards = QHBoxLayout()
        cards.setSpacing(14)
        self.config_card = Card("Config")
        self.repo_card = Card("Repository")
        self.targets_card = Card("Targets")
        for card in (self.config_card, self.repo_card, self.targets_card):
            cards.addWidget(card, 1)
        self.layout_v.addLayout(cards)

        self.details = QLabel("")
        self.details.setProperty("muted", True)
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(self.details.textInteractionFlags())
        self.layout_v.addWidget(self.details)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        preview_push = QPushButton("Preview Push")
        preview_push.setObjectName("primary")
        preview_push.clicked.connect(lambda: self.main.navigate("Sync"))
        preview_pull = QPushButton("Preview Pull")
        preview_pull.clicked.connect(lambda: self.main.navigate("Sync"))
        doctor = QPushButton("Run Doctor")
        doctor.clicked.connect(self._run_doctor)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        for button in (preview_push, preview_pull, doctor):
            actions.addWidget(button)
        actions.addStretch(1)
        actions.addWidget(refresh)
        self.layout_v.addLayout(actions)
        self.layout_v.addStretch(1)

    def refresh(self) -> None:
        self.main.run_callable(services.load_overview_status, self._apply, description="Loading overview")

    def _run_doctor(self) -> None:
        self.main.navigate("Logs")
        self.main.run_command(cli_command("doctor", "--no-ascii", "--color", "never"), description="doctor")

    def _apply(self, status: services.OverviewStatus) -> None:
        # Config card
        if status.config_exists:
            self.config_card.set_value("Saved", status.config_path, "ok", "ready")
        else:
            self.config_card.set_value("Not created", "Using implicit defaults — run setup before real syncs.", "warn", "defaults")

        # Repo card
        if not status.git_available:
            self.repo_card.set_value(status.repo_dir, "git is not installed or not in PATH", "error", "no git")
        elif not status.repo_initialized:
            self.repo_card.set_value(status.repo_dir, "Repository is not initialized yet.", "warn", "no repo")
        elif status.repo_dirty:
            self.repo_card.set_value(status.repo_dir, f"Branch {status.repo_branch or '?'} · uncommitted changes", "warn", "dirty")
        else:
            self.repo_card.set_value(status.repo_dir, f"Branch {status.repo_branch or '?'} · clean", "ok", "clean")

        # Targets card
        level = "ok" if status.enabled_target_count else "warn"
        self.targets_card.set_value(
            f"{status.enabled_target_count}/{status.target_count} enabled",
            f"local skills: {status.local_skill_count} · repo skills: {status.repo_skill_count}",
            level,
            "active" if status.enabled_target_count else "none on",
        )

        remote = status.repo_remote.splitlines()[0] if status.repo_remote else "(no remote configured)"
        self.details.setText(f"Config: {status.config_path}\nRemote: {remote}")
