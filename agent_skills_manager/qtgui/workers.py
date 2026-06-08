"""Background task workers.

Long-running work (git subprocesses, file hashing for previews/validation) must
never run on the Qt main thread or the window freezes. Two worker objects cover
both cases; both are moved onto a ``QThread`` by :class:`MainWindow`.
"""
from __future__ import annotations

import subprocess
import sys
from typing import Callable, List, Sequence

from PySide6.QtCore import QObject, Signal, Slot


class CommandWorker(QObject):
    """Run a CLI subcommand as a subprocess, streaming stdout line by line."""

    output = Signal(str)
    error = Signal(str)
    finished = Signal(int)

    def __init__(self, argv: Sequence[str]) -> None:
        super().__init__()
        self.argv = list(argv)

    @Slot()
    def run(self) -> None:
        try:
            proc = subprocess.Popen(
                self.argv,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                self.output.emit(line)
            proc.wait()
            self.finished.emit(proc.returncode)
        except Exception as exc:  # pragma: no cover - surfaced into the log pane
            self.error.emit(str(exc))
            self.finished.emit(1)


class CallableWorker(QObject):
    """Run a read-only service call off the main thread and emit its result."""

    result = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self.fn = fn

    @Slot()
    def run(self) -> None:
        try:
            value = self.fn()
            self.result.emit(value)
        except Exception as exc:  # pragma: no cover - surfaced into the UI
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


def cli_command(*args: str) -> List[str]:
    """Build the argv for an out-of-process CLI invocation (CLI-identical apply)."""
    return [sys.executable, "-m", "agent_skills_manager.cli", *args]
