"""Qt table models for the targets, validation, and file-change tables."""
from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from ..config import SkillTarget
from . import theme
from .services import FileChange, SkillComparisonRow, TargetStatus, ValidationFinding

_RED = QColor("#ef4444")
_AMBER = QColor("#9a6700")
_MUTED = QColor("#6e7781")

# Comparison statuses map to distinct semantic colours from the active palette so
# they track the OS light/dark switch the same way the rest of the GUI does.
_COMPARE_TOKENS = {
    "only_a": "ACCENT",     # only in A   -> blue
    "only_b": "WARN_FG",    # only in B   -> amber
    "same": "OK_FG",        # identical   -> green
    "different": "ERROR_FG",  # differs   -> red
}


def status_color(status: str) -> Optional[QColor]:
    """Return the palette colour for a comparison status (live light/dark aware)."""
    token = _COMPARE_TOKENS.get(status)
    if not token:
        return None
    app = QApplication.instance()
    palette = theme.DARK if (app is not None and theme.is_dark(app)) else theme.LIGHT
    return QColor(palette[token])


class TargetTableModel(QAbstractTableModel):
    """Editable table of skill targets (the Targets page)."""

    HEADERS = ["", "Name", "Local dir", "Repo subdir", "Local", "Repo", "Status"]

    def __init__(self, rows: Optional[List[TargetStatus]] = None) -> None:
        super().__init__()
        self._rows: List[TargetStatus] = list(rows or [])

    # --- required overrides ---
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        col = index.column()
        if col == 0:
            return base | Qt.ItemIsUserCheckable
        if col in (1, 2, 3):
            return base | Qt.ItemIsEditable
        return base

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        if col == 0 and role == Qt.CheckStateRole:
            return Qt.Checked if row.enabled else Qt.Unchecked
        if role in (Qt.DisplayRole, Qt.EditRole):
            if col == 1:
                return row.name
            if col == 2:
                return row.local_dir
            if col == 3:
                return row.repo_dir
            if col == 4:
                return str(row.local_skills)
            if col == 5:
                return str(row.repo_skills)
            if col == 6:
                return row.status
        if role == Qt.ForegroundRole and col == 6 and row.status == "not exist":
            return _AMBER
        if role == Qt.TextAlignmentRole and col in (4, 5):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole) -> bool:
        if not index.isValid():
            return False
        row = self._rows[index.row()]
        col = index.column()
        if col == 0 and role == Qt.CheckStateRole:
            row.enabled = Qt.CheckState(value) == Qt.Checked
            self.dataChanged.emit(index, index, [Qt.CheckStateRole])
            return True
        if role == Qt.EditRole:
            text = str(value)
            if col == 1:
                row.name = text
            elif col == 2:
                row.local_dir = text
            elif col == 3:
                row.repo_dir = text
            else:
                return False
            self.dataChanged.emit(index, index, [Qt.EditRole, Qt.DisplayRole])
            return True
        return False

    # --- helpers ---
    def set_rows(self, rows: List[TargetStatus]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def add_row(self, row: TargetStatus) -> None:
        position = len(self._rows)
        self.beginInsertRows(QModelIndex(), position, position)
        self._rows.append(row)
        self.endInsertRows()

    def remove_row(self, position: int) -> None:
        if 0 <= position < len(self._rows):
            self.beginRemoveRows(QModelIndex(), position, position)
            del self._rows[position]
            self.endRemoveRows()

    def row_at(self, position: int) -> Optional[TargetStatus]:
        if 0 <= position < len(self._rows):
            return self._rows[position]
        return None

    def to_targets(self) -> List[SkillTarget]:
        return [SkillTarget(r.name, r.local_dir, r.repo_dir, r.enabled) for r in self._rows]


class ValidationTableModel(QAbstractTableModel):
    """Read-only, filterable table of validation findings (the Validate page)."""

    HEADERS = ["Severity", "Target", "Skill", "File", "Message"]

    def __init__(self) -> None:
        super().__init__()
        self._all: List[ValidationFinding] = []
        self._rows: List[ValidationFinding] = []
        self._show_errors = True
        self._show_warnings = True
        self._show_secrets = True

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        finding = self._rows[index.row()]
        col = index.column()
        if role in (Qt.DisplayRole, Qt.EditRole):
            return [finding.severity, finding.target, finding.skill, finding.path, finding.message][col]
        if role == Qt.ForegroundRole and col == 0:
            return _RED if finding.severity == "error" else _AMBER
        return None

    def set_findings(self, findings: List[ValidationFinding]) -> None:
        self._all = list(findings)
        self._apply_filter()

    def set_filter(self, show_errors: bool, show_warnings: bool, show_secrets: bool) -> None:
        self._show_errors = show_errors
        self._show_warnings = show_warnings
        self._show_secrets = show_secrets
        self._apply_filter()

    def _apply_filter(self) -> None:
        self.beginResetModel()
        rows: List[ValidationFinding] = []
        for f in self._all:
            if f.kind == "secret":
                if self._show_secrets:
                    rows.append(f)
                continue
            if f.severity == "error" and self._show_errors:
                rows.append(f)
            elif f.severity == "warning" and self._show_warnings:
                rows.append(f)
        self._rows = rows
        self.endResetModel()

    def finding_at(self, position: int) -> Optional[ValidationFinding]:
        if 0 <= position < len(self._rows):
            return self._rows[position]
        return None


class FileChangeTableModel(QAbstractTableModel):
    """Read-only table of file changes (Sync preview and Diff)."""

    HEADERS = ["Status", "Target", "Path"]

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[Tuple[str, FileChange]] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        target, change = self._rows[index.row()]
        col = index.column()
        if role in (Qt.DisplayRole, Qt.EditRole):
            return [change.status, target, change.path][col]
        if role == Qt.ForegroundRole and col == 0:
            if change.status in ("deleted", "conflict"):
                return _RED
            if change.status == "modified":
                return _AMBER
        return None

    def set_rows(self, rows: List[Tuple[str, FileChange]]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def change_at(self, position: int) -> Optional[Tuple[str, FileChange]]:
        if 0 <= position < len(self._rows):
            return self._rows[position]
        return None


class SkillComparisonTableModel(QAbstractTableModel):
    """Read-only, colour-coded table comparing two targets' skills (Compare page)."""

    HEADERS = ["Status", "Skill", "A version", "B version"]
    _LABELS = {"only_a": "only A", "only_b": "only B", "same": "same", "different": "differs"}

    def __init__(self) -> None:
        super().__init__()
        self._rows: List[SkillComparisonRow] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        if role in (Qt.DisplayRole, Qt.EditRole):
            a_version = row.a.version if row.a else ""
            b_version = row.b.version if row.b else ""
            return [self._LABELS.get(row.status, row.status), row.name, a_version, b_version][col]
        if role == Qt.ForegroundRole and col == 0:
            return status_color(row.status)
        return None

    def set_rows(self, rows: List[SkillComparisonRow]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def row_at(self, position: int) -> Optional[SkillComparisonRow]:
        if 0 <= position < len(self._rows):
            return self._rows[position]
        return None
