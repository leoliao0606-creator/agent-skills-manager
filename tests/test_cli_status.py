import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_skills_manager import cli


def status_args(**overrides):
    values = {
        "all": False,
        "only": None,
        "format": "text",
        "examples": True,
        "limit": 5,
        "no_git": False,
        "no_scan": False,
        "color": "auto",
        "ascii_art": True,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class StatusTests(unittest.TestCase):
    def test_status_defaults_to_configured_targets_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            enabled_local = tmp_path / "enabled-local"
            not_configured_local = tmp_path / "not-configured-local"
            repo = tmp_path / "repo"
            enabled_local.mkdir(parents=True)
            not_configured_local.mkdir(parents=True)
            repo.mkdir(parents=True)
            cfg = cli.Config(
                repo_dir=str(repo),
                targets=[
                    cli.SkillTarget("claude", str(enabled_local), "claude-skills", True),
                    cli.SkillTarget("gemini", str(not_configured_local), "gemini-skills", False),
                ],
            )
            stdout = io.StringIO()

            with patch.object(cli, "load_config", return_value=cfg):
                with contextlib.redirect_stdout(stdout):
                    cli.cmd_status(status_args())

        output = stdout.getvalue()
        self.assertIn("[claude] configured", output)
        self.assertNotIn("[gemini]", output)

    def test_status_no_scan_prints_only_git_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local = tmp_path / "local"
            repo = tmp_path / "repo"
            local.mkdir()
            repo.mkdir()
            cfg = cli.Config(
                repo_dir=str(repo),
                targets=[cli.SkillTarget("claude", str(local), "claude-skills", True)],
            )
            stdout = io.StringIO()

            with patch.object(cli, "load_config", return_value=cfg):
                with contextlib.redirect_stdout(stdout):
                    cli.cmd_status(status_args(no_scan=True))

        output = stdout.getvalue()
        self.assertIn("Repo is not initialized yet.", output)
        self.assertNotIn("[claude]", output)

    def test_status_no_git_prints_only_scan_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local = tmp_path / "local"
            local.mkdir()
            cfg = cli.Config(
                repo_dir=str(tmp_path / "repo"),
                targets=[cli.SkillTarget("claude", str(local), "claude-skills", True)],
            )
            stdout = io.StringIO()

            with patch.object(cli, "load_config", return_value=cfg):
                with contextlib.redirect_stdout(stdout):
                    cli.cmd_status(status_args(no_git=True))

        output = stdout.getvalue()
        self.assertNotIn("Repo is not initialized yet.", output)
        self.assertIn("[claude] configured", output)

    def test_status_json_includes_git_and_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local = tmp_path / "local"
            repo = tmp_path / "repo"
            local.mkdir()
            repo.mkdir()
            cfg = cli.Config(
                repo_dir=str(repo),
                targets=[cli.SkillTarget("claude", str(local), "claude-skills", True)],
            )
            stdout = io.StringIO()

            with patch.object(cli, "load_config", return_value=cfg):
                with contextlib.redirect_stdout(stdout):
                    cli.cmd_status(status_args(format="json"))

        data = json.loads(stdout.getvalue())
        self.assertEqual(data["repo"], str(repo.resolve()))
        self.assertIn("git", data)
        self.assertEqual(data["targets"][0]["name"], "claude")


if __name__ == "__main__":
    unittest.main()
