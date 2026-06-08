import types
import unittest
from unittest.mock import patch

from agent_skills_manager import cli


class GuiTests(unittest.TestCase):
    def test_gui_without_display_exits_cleanly_without_traceback(self):
        class DisplayError(RuntimeError):
            pass

        fake_tk = types.SimpleNamespace()
        fake_tk.TclError = DisplayError
        fake_tk.filedialog = types.SimpleNamespace()
        fake_tk.messagebox = types.SimpleNamespace()

        def fail_tk():
            raise DisplayError("no display name and no $DISPLAY environment variable")

        fake_tk.Tk = fail_tk

        with patch.dict("sys.modules", {"tkinter": fake_tk}):
            with self.assertRaises(SystemExit) as ctx:
                cli.cmd_gui(object())

        self.assertIn("GUI is not available", str(ctx.exception))
        self.assertIn("no display", str(ctx.exception))


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
