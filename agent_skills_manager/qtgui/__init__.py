"""Optional PySide6 desktop frontend for agent-skills-manager.

The CLI remains the primary, dependency-free interface. This package is only
imported when the user runs ``agent-skills gui`` and PySide6 is installed.

Only :mod:`services` (and its dataclasses) is guaranteed to be importable
without PySide6 — every other module in this package imports Qt.
"""
