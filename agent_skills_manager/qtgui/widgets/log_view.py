"""A read-only monospace log pane fed by command workers."""
from __future__ import annotations

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QPlainTextEdit


class LogView(QPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("logView")
        self.setReadOnly(True)
        self.setMaximumBlockCount(10000)
        self._autoscroll = True

    def set_autoscroll(self, enabled: bool) -> None:
        self._autoscroll = enabled

    def append_text(self, text: str) -> None:
        # insertPlainText preserves a streamed subprocess's own newlines.
        self.moveCursor(QTextCursor.End)
        self.insertPlainText(text)
        if self._autoscroll:
            self.moveCursor(QTextCursor.End)
            self.ensureCursorVisible()

    def append_line(self, text: str) -> None:
        self.append_text(text if text.endswith("\n") else text + "\n")

    def copy_all(self) -> None:
        QApplication.clipboard().setText(self.toPlainText())
