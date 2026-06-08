import argparse
import sys
import unittest
from unittest.mock import patch

from agent_skills_manager import cli


class GuiTests(unittest.TestCase):
    def test_gui_without_pyside6_exits_with_install_hint(self):
        # Force the optional Qt import to fail regardless of whether PySide6 is
        # actually installed: block PySide6 in sys.modules and drop any cached
        # qtgui submodules so the import statement re-executes.
        removed = {
            name: sys.modules.pop(name)
            for name in list(sys.modules)
            if name.startswith("agent_skills_manager.qtgui")
        }
        try:
            with patch.dict(sys.modules, {"PySide6": None, "PySide6.QtWidgets": None}):
                with self.assertRaises(SystemExit) as ctx:
                    cli.cmd_gui(argparse.Namespace())
        finally:
            sys.modules.update(removed)

        message = str(ctx.exception)
        self.assertIn("PySide6", message)
        self.assertIn("pip install 'agent-skills-manager[qt]'", message)


class GuiActionCommandTests(unittest.TestCase):
    def test_readonly_actions_have_no_sync_flags(self):
        for action in ("scan", "status", "validate"):
            cmd = cli.gui_action_command(action, dry_run=True, mirror=True, python="py")
            self.assertEqual(cmd, ["py", "-m", "agent_skills_manager.cli", action])

    def test_diff_previews_push_direction(self):
        cmd = cli.gui_action_command("diff", dry_run=True, mirror=True, python="py")
        self.assertEqual(cmd, ["py", "-m", "agent_skills_manager.cli", "diff", "--direction", "push"])

    def test_push_includes_dry_run_mirror_and_message(self):
        cmd = cli.gui_action_command("push", dry_run=True, mirror=True, message="hello", python="py")
        self.assertEqual(
            cmd,
            ["py", "-m", "agent_skills_manager.cli", "push", "--dry-run", "--mirror", "--yes", "-m", "hello"],
        )

    def test_pull_plain_run_has_no_flags(self):
        cmd = cli.gui_action_command("pull", dry_run=False, mirror=False, python="py")
        self.assertEqual(cmd, ["py", "-m", "agent_skills_manager.cli", "pull"])


if __name__ == "__main__":
    unittest.main()
