"""Headless smoke test: build the window and every page without showing it.

Skipped entirely when PySide6 is not installed (the default, dependency-free
test environment). Runs under the offscreen Qt platform plugin.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QElapsedTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from agent_skills_manager.qtgui.main_window import MainWindow  # noqa: E402

EXPECTED_PAGES = ["Overview", "Targets", "Sync", "Diff", "Validate", "Backups", "Settings", "Logs"]


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


def _drain(application, window, timeout_ms=8000):
    """Let the construction-time Overview refresh thread finish and clean up."""
    timer = QElapsedTimer()
    timer.start()
    while window.busy and timer.elapsed() < timeout_ms:
        application.processEvents()
    application.processEvents()


def test_main_window_builds_all_pages(app):
    window = MainWindow()
    try:
        assert window.stack.count() == len(EXPECTED_PAGES)
        labels = [window.nav.item(i).text() for i in range(window.nav.count())]
        assert labels == EXPECTED_PAGES
        _drain(app, window)
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()


def test_pages_construct_individually(app):
    # Each page is constructed inside MainWindow; verify the concrete types so a
    # broken page import/layout fails here rather than only at runtime.
    from agent_skills_manager.qtgui.pages.backups import BackupsPage
    from agent_skills_manager.qtgui.pages.diff import DiffPage
    from agent_skills_manager.qtgui.pages.logs import LogsPage
    from agent_skills_manager.qtgui.pages.overview import OverviewPage
    from agent_skills_manager.qtgui.pages.settings import SettingsPage
    from agent_skills_manager.qtgui.pages.sync import SyncPage
    from agent_skills_manager.qtgui.pages.targets import TargetsPage
    from agent_skills_manager.qtgui.pages.validate import ValidatePage

    window = MainWindow()
    try:
        types = {type(page) for _label, page in window._pages}
        assert types == {
            OverviewPage, TargetsPage, SyncPage, DiffPage,
            ValidatePage, BackupsPage, SettingsPage, LogsPage,
        }
        _drain(app, window)
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
