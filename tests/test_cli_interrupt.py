import argparse
import contextlib
import io
import unittest
from unittest.mock import patch

from agent_skills_manager import cli


class CtrlCHandlingTests(unittest.TestCase):
    def test_main_handles_keyboard_interrupt_without_traceback(self):
        stderr = io.StringIO()
        with patch.object(cli, "cmd_scan", side_effect=KeyboardInterrupt):
            with contextlib.redirect_stderr(stderr):
                exit_code = cli.main(["scan"])

        self.assertEqual(exit_code, 130)
        self.assertIn("Cancelled", stderr.getvalue())

    def test_main_handles_eof_without_traceback(self):
        stderr = io.StringIO()
        with patch.object(cli, "cmd_scan", side_effect=EOFError):
            with contextlib.redirect_stderr(stderr):
                exit_code = cli.main(["scan"])

        self.assertEqual(exit_code, 130)
        self.assertIn("No input received", stderr.getvalue())

    def test_setup_explains_local_repo_checkout_path_before_prompting(self):
        stdout = io.StringIO()
        with patch.object(cli, "git_available", return_value=True):
            with patch.object(cli, "load_config", return_value=cli.Config("~/agent-skills-library")):
                def interrupt_after_prompt(prompt):
                    print(prompt, end="")
                    raise KeyboardInterrupt

                with patch("builtins.input", side_effect=interrupt_after_prompt):
                    with contextlib.redirect_stdout(stdout):
                        with self.assertRaises(KeyboardInterrupt):
                            cli.cmd_setup(argparse.Namespace())

        output = stdout.getvalue()
        self.assertIn("Local repo checkout path", output)
        self.assertIn("local Git checkout directory", output)
        self.assertIn("not your home directory", output)
        self.assertIn("~/agent-skills-library", output)
        self.assertIn("Local repo checkout path [~/agent-skills-library]", output)

    def test_default_repo_dir_is_home_relative_not_machine_specific(self):
        self.assertEqual(cli.detect_default_repo(), "~/agent-skills-library")

    def test_setup_repo_path_prompt_uses_generic_default_even_when_config_has_custom_path(self):
        stdout = io.StringIO()
        inputs = iter(["", "", "main", "none"])
        saved = []
        cfg = cli.Config(
            "~/Projects/custom-agent-skills",
            remote_url="git@github.com:owner/custom-agent-skills.git",
            default_branch="test",
            targets=[],
        )

        def answer(prompt):
            print(prompt, end="")
            value = next(inputs)
            print(value)
            return value

        def save_and_stop(config):
            saved.append(config)
            raise KeyboardInterrupt

        with patch.object(cli, "git_available", return_value=True):
            with patch.object(cli, "load_config", return_value=cfg):
                with patch.object(cli, "candidate_targets", return_value=[]):
                    with patch.object(cli, "save_config", side_effect=save_and_stop):
                        with patch("builtins.input", side_effect=answer):
                            with contextlib.redirect_stdout(stdout):
                                with self.assertRaises(KeyboardInterrupt):
                                    cli.cmd_setup(argparse.Namespace())

        output = stdout.getvalue()
        self.assertIn("Local repo checkout path [~/agent-skills-library]", output)
        self.assertIn("Git remote URL (SSH or HTTPS; empty is OK for local-only):", output)
        self.assertNotIn("Git remote URL (SSH or HTTPS; empty is OK for local-only) [", output)
        self.assertIn("Default branch [main]", output)
        self.assertNotIn("custom-agent-skills", output)
        self.assertNotIn("Default branch [test]", output)
        self.assertEqual(saved[0].repo_dir, "~/agent-skills-library")
        self.assertEqual(saved[0].remote_url, "")
        self.assertEqual(saved[0].default_branch, "main")

    def test_setup_remote_url_prompt_has_no_default_and_enter_clears_value(self):
        stdout = io.StringIO()
        inputs = iter(["~/agent-skills-library", "", "main", "none"])
        saved = []
        cfg = cli.Config(
            "~/agent-skills-library",
            remote_url="git@github.com:owner/existing.git",
            targets=[],
        )

        def answer(prompt):
            print(prompt, end="")
            value = next(inputs)
            if isinstance(value, BaseException):
                raise value
            print(value)
            return value

        def save_and_stop(config):
            saved.append(config)
            raise KeyboardInterrupt

        with patch.object(cli, "git_available", return_value=True):
            with patch.object(cli, "load_config", return_value=cfg):
                with patch.object(cli, "candidate_targets", return_value=[]):
                    with patch.object(cli, "save_config", side_effect=save_and_stop):
                        with patch("builtins.input", side_effect=answer):
                            with contextlib.redirect_stdout(stdout):
                                with self.assertRaises(KeyboardInterrupt):
                                    cli.cmd_setup(argparse.Namespace())

        output = stdout.getvalue()
        self.assertIn("Git remote URL (SSH or HTTPS; empty is OK for local-only):", output)
        self.assertNotIn("Git remote URL (SSH or HTTPS; empty is OK for local-only) [", output)
        self.assertEqual(saved[0].remote_url, "")


if __name__ == "__main__":
    unittest.main()
