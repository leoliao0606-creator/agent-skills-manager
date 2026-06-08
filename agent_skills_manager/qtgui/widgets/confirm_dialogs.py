"""Confirmation dialogs for destructive operations (doc §15)."""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget


def confirm(parent: QWidget | None, title: str, text: str) -> bool:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    box.setDefaultButton(QMessageBox.No)
    return box.exec() == QMessageBox.Yes


def confirm_mirror(parent: QWidget | None, direction: str) -> bool:
    where = "the repository copy" if direction == "push" else "your local skill directories"
    return confirm(
        parent,
        f"Mirror {direction.capitalize()}",
        f"Mirror {direction.capitalize()} may delete files from {where}.\n\n"
        "This will make the destination match the source exactly.\n"
        "Deleted files cannot be recovered unless they exist in git history or backups.\n\n"
        "Continue?",
    )


def confirm_force(parent: QWidget | None) -> bool:
    return confirm(
        parent,
        "Force overwrite",
        "Force will overwrite files that were flagged as conflicts.\n\n"
        "Conflicting changes in the destination will be lost.\n\n"
        "Continue?",
    )
