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


if __name__ == "__main__":
    unittest.main()
