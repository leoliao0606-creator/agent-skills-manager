"""Entry shim for the optional Qt desktop GUI.

The CLI is the primary, dependency-free interface. ``agent-skills gui`` opens an
optional PySide6 frontend (:mod:`agent_skills_manager.qtgui`); if PySide6 is not
installed we exit with a friendly install hint instead of a traceback.

``gui_action_command`` is a pure argv builder kept here (not in the Qt package)
so it stays importable without the ``[qt]`` extra and unit-testable without a
display.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

# Read-only actions never touch files; sync actions accept dry-run/mirror flags.
GUI_SYNC_ACTIONS = ("pull", "push")
GUI_READONLY_ACTIONS = ("scan", "status", "diff", "validate")


def gui_action_command(
    action: str,
    *,
    dry_run: bool = False,
    mirror: bool = False,
    message: str = "Sync local agent skills",
    python: Optional[str] = None,
) -> List[str]:
    """Build the ``python -m agent_skills_manager.cli ...`` argv for a GUI action.

    Kept as a pure function so the flag assembly is unit-testable without a
    display. ``dry_run``/``mirror`` only apply to the sync actions; ``diff``
    always previews and ``scan``/``status``/``validate`` are read-only.
    """
    python = python or sys.executable
    cmd = [python, "-m", "agent_skills_manager.cli", action]
    if action == "diff":
        cmd += ["--direction", "push"]
    if action in GUI_SYNC_ACTIONS:
        if dry_run:
            cmd.append("--dry-run")
        if mirror:
            cmd += ["--mirror", "--yes"]
    if action == "push":
        cmd += ["-m", message]
    return cmd


def gui_copy_skill_command(
    spec: str,
    to_target: str,
    *,
    from_location: str = "local",
    to_location: str = "local",
    dry_run: bool = False,
    mirror: bool = False,
    force: bool = False,
    python: Optional[str] = None,
) -> List[str]:
    """Build the ``copy-skill`` argv for the GUI's "Copy →" action.

    Kept as a pure function (alongside :func:`gui_action_command`) so the GUI
    write path goes through the exact CLI verb and its confirmation/backup, and
    so the flag assembly stays unit-testable without a display. ``--yes`` is set
    because the GUI gathers its own confirmation before invoking the command.
    """
    python = python or sys.executable
    cmd = [
        python, "-m", "agent_skills_manager.cli", "copy-skill", spec,
        "--to-target", to_target,
        "--from-location", from_location,
        "--to-location", to_location,
        "--yes",
    ]
    if dry_run:
        cmd.append("--dry-run")
    if mirror:
        cmd.append("--mirror")
    if force:
        cmd.append("--force")
    return cmd


def cmd_gui(args: argparse.Namespace) -> None:
    try:
        from .qtgui.app import run
    except ImportError as exc:
        raise SystemExit(
            "Qt GUI requires PySide6.\n\n"
            "Install it with:\n"
            "  python -m pip install 'agent-skills-manager[qt]'\n\n"
            "CLI alternatives:\n"
            "  agent-skills setup\n"
            "  agent-skills scan\n"
            "  agent-skills status\n"
            "  agent-skills push --dry-run"
        ) from exc

    run(args)
