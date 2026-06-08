import unittest
from unittest.mock import patch

from agent_skills_manager import cli


class FakeReadline:
    def __init__(self):
        self.completer = "original"
        self.bindings = []

    def get_completer(self):
        return self.completer

    def set_completer(self, completer):
        self.completer = completer

    def parse_and_bind(self, binding):
        self.bindings.append(binding)


class PathCompletionTests(unittest.TestCase):
    def test_read_path_answer_enables_tab_completion_and_restores_previous_completer(self):
        fake_readline = FakeReadline()
        prompts = []

        def answer(prompt):
            prompts.append(prompt)
            self.assertTrue(callable(fake_readline.completer))
            return "~/Projects/skills"

        with patch.object(cli.tui, "readline", fake_readline):
            with patch("builtins.input", side_effect=answer):
                result = cli.read_path_answer("Local repo checkout path", "~/agent-skills-library")

        self.assertEqual(result, "~/Projects/skills")
        self.assertEqual(prompts, ["Local repo checkout path [~/agent-skills-library]: "])
        self.assertIn("tab: complete", fake_readline.bindings)
        self.assertEqual(fake_readline.completer, "original")

    def test_read_path_answer_falls_back_to_plain_input_without_readline(self):
        with patch.object(cli.tui, "readline", None):
            with patch("builtins.input", return_value=""):
                result = cli.read_path_answer("Local repo checkout path", "~/agent-skills-library")

        self.assertEqual(result, "~/agent-skills-library")


if __name__ == "__main__":
    unittest.main()
