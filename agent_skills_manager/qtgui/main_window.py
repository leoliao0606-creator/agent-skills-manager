"""The main window: left nav + stacked pages, status bar, and task plumbing.

All long-running work goes through :meth:`run_command` (subprocess, CLI-identical)
or :meth:`run_callable` (read-only service calls). Both run on a ``QThread`` and
toggle a busy state that destructive buttons listen to via ``busyChanged``.
"""
from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .pages.backups import BackupsPage
from .pages.compare import ComparePage
from .pages.diff import DiffPage
from .pages.logs import LogsPage
from .pages.overview import OverviewPage
from .pages.settings import SettingsPage
from .pages.sync import SyncPage
from .pages.targets import TargetsPage
from .pages.validate import ValidatePage
from .widgets import LogView
from .workers import CallableWorker, CommandWorker


class MainWindow(QMainWindow):
    busyChanged = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Agent Skills Manager")

        self.busy = False
        self._threads: List[Tuple[QThread, object]] = []
        self.log_view = LogView()

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_header())

        body = QWidget()
        layout = QHBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(200)
        self.stack = QStackedWidget()

        self._pages: List[Tuple[str, QWidget]] = [
            ("Overview", OverviewPage(self)),
            ("Targets", TargetsPage(self)),
            ("Sync", SyncPage(self)),
            ("Diff", DiffPage(self)),
            ("Compare", ComparePage(self)),
            ("Validate", ValidatePage(self)),
            ("Backups", BackupsPage(self)),
            ("Settings", SettingsPage(self)),
            ("Logs", LogsPage(self, self.log_view)),
        ]
        self._index = {label: i for i, (label, _) in enumerate(self._pages)}
        for label, page in self._pages:
            self.nav.addItem(QListWidgetItem(label))
            self.stack.addWidget(page)

        layout.addWidget(self.nav)
        layout.addWidget(self.stack, 1)
        outer.addWidget(body, 1)
        self.setCentralWidget(root)

        self.nav.currentRowChanged.connect(self._on_nav_changed)
        self.statusBar().showMessage("Ready")
        self.nav.setCurrentRow(0)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("titleBar")
        header.setFixedHeight(48)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(18, 0, 18, 0)
        title = QLabel("Agent Skills Manager")
        title.setObjectName("appTitle")
        self.busy_label = QLabel("")
        self.busy_label.setProperty("muted", True)
        layout.addWidget(title)
        layout.addStretch(1)
        layout.addWidget(self.busy_label)
        return header

    # --- navigation ---
    def _on_nav_changed(self, index: int) -> None:
        if index < 0:
            return
        self.stack.setCurrentIndex(index)
        page = self.stack.widget(index)
        if hasattr(page, "refresh"):
            page.refresh()

    def navigate(self, label: str) -> None:
        if label in self._index:
            self.nav.setCurrentRow(self._index[label])

    def closeEvent(self, event) -> None:
        # Join any running worker threads so we never destroy a live QThread.
        for thread, _worker in list(self._threads):
            thread.quit()
            thread.wait(3000)
        super().closeEvent(event)

    def set_status(self, text: str) -> None:
        self.statusBar().showMessage(text)

    # --- task plumbing ---
    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.busy_label.setText("● working…" if busy else "")
        self.busyChanged.emit(busy)

    def _spawn(self, worker) -> QThread:
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        entry = (thread, worker)
        self._threads.append(entry)

        def _cleanup() -> None:
            worker.deleteLater()
            thread.deleteLater()
            try:
                self._threads.remove(entry)
            except ValueError:
                pass

        thread.finished.connect(_cleanup)
        return thread

    def run_command(self, argv: Sequence[str], description: str = "", on_finished: Optional[Callable[[int], None]] = None) -> None:
        if self.busy:
            self.set_status("Busy — wait for the current task to finish.")
            return
        worker = CommandWorker(argv)
        thread = self._spawn(worker)
        self._set_busy(True)
        self.log_view.append_line(f"$ {' '.join(argv)}")
        worker.output.connect(self.log_view.append_text)
        worker.error.connect(lambda message: self.log_view.append_line(f"[error] {message}"))

        def _done(code: int) -> None:
            self._set_busy(False)
            self.set_status(f"{description or 'Command'} finished (exit {code})")
            if on_finished is not None:
                on_finished(code)

        worker.finished.connect(_done)
        worker.finished.connect(thread.quit)
        self.set_status(f"Running: {description or 'command'}…")
        thread.start()

    def run_callable(self, fn: Callable[[], object], on_result: Callable[[object], None], on_error: Optional[Callable[[str], None]] = None, description: str = "") -> None:
        if self.busy:
            self.set_status("Busy — wait for the current task to finish.")
            return
        worker = CallableWorker(fn)
        thread = self._spawn(worker)
        self._set_busy(True)
        if description:
            self.set_status(f"{description}…")
        worker.result.connect(on_result)

        def _err(message: str) -> None:
            self.log_view.append_line(f"[error] {message}")
            self.set_status(f"Error: {message}")
            if on_error is not None:
                on_error(message)

        def _finished() -> None:
            self._set_busy(False)

        worker.error.connect(_err)
        worker.finished.connect(_finished)
        worker.finished.connect(thread.quit)
        thread.start()
