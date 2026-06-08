import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_skills_manager import cli


def scan_args(**overrides):
    values = {
        "all": False,
        "only": None,
        "format": "text",
        "examples": True,
        "limit": 5,
        "color": "auto",
        "ascii_art": True,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class ScanStatusTests(unittest.TestCase):
    def test_scan_defaults_to_configured_targets_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            existing_local = tmp_path / "local"
            not_configured_local = tmp_path / "not-configured-local"
            existing_repo = tmp_path / "repo" / "claude-skills"
            existing_local.mkdir(parents=True)
            not_configured_local.mkdir(parents=True)
            existing_repo.mkdir(parents=True)
            missing_local = tmp_path / "missing-local"

            cfg = cli.Config(
                repo_dir=str(tmp_path / "repo"),
                targets=[
                    cli.SkillTarget("claude", str(existing_local), "claude-skills", True),
                    cli.SkillTarget("codex", str(missing_local), "codex-skills", False),
                    cli.SkillTarget("gemini", str(not_configured_local), "gemini-skills", False),
                ],
            )
            stdout = io.StringIO()

            with patch.object(cli.config, "load_config", return_value=cfg):
                with contextlib.redirect_stdout(stdout):
                    cli.cmd_scan(scan_args())

        output = stdout.getvalue()
        self.assertIn("[claude] configured", output)
        self.assertNotIn("[codex]", output)
        self.assertNotIn("[gemini]", output)

    def test_scan_all_reports_missing_directories_as_not_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            existing_local = tmp_path / "local"
            existing_repo = tmp_path / "repo" / "claude-skills"
            existing_local.mkdir(parents=True)
            existing_repo.mkdir(parents=True)
            missing_local = tmp_path / "missing-local"

            cfg = cli.Config(
                repo_dir=str(tmp_path / "repo"),
                targets=[
                    cli.SkillTarget("claude", str(existing_local), "claude-skills", True),
                    cli.SkillTarget("codex", str(missing_local), "codex-skills", False),
                ],
            )
            stdout = io.StringIO()

            with patch.object(cli.config, "load_config", return_value=cfg):
                with contextlib.redirect_stdout(stdout):
                    cli.cmd_scan(scan_args(all=True))

        output = stdout.getvalue()
        self.assertIn("[claude] configured", output)
        self.assertIn("[codex] not exist", output)
        self.assertNotIn("[codex] not configured", output)
        codex_section = output.split("[codex] not exist", 1)[1]
        self.assertNotIn("local:", codex_section)
        self.assertNotIn("repo:", codex_section)

    def test_scan_all_reports_existing_disabled_target_as_not_configured(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local = tmp_path / "local"
            local.mkdir()
            cfg = cli.Config(
                repo_dir=str(tmp_path / "repo"),
                targets=[cli.SkillTarget("gemini", str(local), "gemini-skills", False)],
            )
            stdout = io.StringIO()

            with patch.object(cli.config, "load_config", return_value=cfg):
                with contextlib.redirect_stdout(stdout):
                    cli.cmd_scan(scan_args(all=True))

        output = stdout.getvalue()
        self.assertIn("[gemini] not configured", output)
        self.assertIn("local:", output)
        self.assertNotIn("repo:", output)

    def test_scan_only_missing_shows_missing_targets_without_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            existing_local = tmp_path / "local"
            existing_local.mkdir()
            cfg = cli.Config(
                repo_dir=str(tmp_path / "repo"),
                targets=[
                    cli.SkillTarget("claude", str(existing_local), "claude-skills", True),
                    cli.SkillTarget("codex", str(tmp_path / "missing-local"), "codex-skills", False),
                ],
            )
            stdout = io.StringIO()

            with patch.object(cli.config, "load_config", return_value=cfg):
                with contextlib.redirect_stdout(stdout):
                    cli.cmd_scan(scan_args(only="missing"))

        output = stdout.getvalue()
        self.assertNotIn("[claude]", output)
        self.assertIn("[codex] not exist", output)

    def test_scan_names_format_outputs_names_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local = tmp_path / "local"
            local.mkdir()
            cfg = cli.Config(
                repo_dir=str(tmp_path / "repo"),
                targets=[cli.SkillTarget("claude", str(local), "claude-skills", True)],
            )
            stdout = io.StringIO()

            with patch.object(cli.config, "load_config", return_value=cfg):
                with contextlib.redirect_stdout(stdout):
                    cli.cmd_scan(scan_args(format="names"))

        self.assertEqual(stdout.getvalue(), "claude\n")

    def test_scan_json_format_is_machine_readable_and_filtered(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local = tmp_path / "local"
            local.mkdir()
            cfg = cli.Config(
                repo_dir=str(tmp_path / "repo"),
                targets=[cli.SkillTarget("claude", str(local), "claude-skills", True)],
            )
            stdout = io.StringIO()

            with patch.object(cli.config, "load_config", return_value=cfg):
                with contextlib.redirect_stdout(stdout):
                    cli.cmd_scan(scan_args(format="json"))

        data = json.loads(stdout.getvalue())
        self.assertEqual(data["repo"], str((tmp_path / "repo").resolve()))
        self.assertEqual(data["targets"][0]["name"], "claude")
        self.assertTrue(data["targets"][0]["configured"])
        self.assertEqual(data["targets"][0]["status"], "configured")

    def test_scan_no_examples_and_limit_control_skill_examples(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local = tmp_path / "local"
            for name in ["one", "two", "three"]:
                skill_dir = local / name
                skill_dir.mkdir(parents=True)
                (skill_dir / "SKILL.md").write_text("# skill\n", encoding="utf-8")
            cfg = cli.Config(
                repo_dir=str(tmp_path / "repo"),
                targets=[cli.SkillTarget("claude", str(local), "claude-skills", True)],
            )
            limited = io.StringIO()
            no_examples = io.StringIO()

            with patch.object(cli.config, "load_config", return_value=cfg):
                with contextlib.redirect_stdout(limited):
                    cli.cmd_scan(scan_args(limit=1))
                with contextlib.redirect_stdout(no_examples):
                    cli.cmd_scan(scan_args(examples=False))

        self.assertIn("    - one", limited.getvalue())
        self.assertNotIn("    - two", limited.getvalue())
        self.assertIn("    ...", limited.getvalue())
        self.assertNotIn("    - one", no_examples.getvalue())
    def test_scan_text_output_can_force_color_and_ascii_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local = tmp_path / "local"
            local.mkdir()
            cfg = cli.Config(
                repo_dir=str(tmp_path / "repo"),
                targets=[cli.SkillTarget("claude", str(local), "claude-skills", True)],
            )
            stdout = io.StringIO()

            with patch.object(cli.config, "load_config", return_value=cfg):
                with contextlib.redirect_stdout(stdout):
                    cli.cmd_scan(scan_args(color="always"))

        output = stdout.getvalue()
        self.assertIn("+-------------------+", output)
        self.assertIn("| Agent Skills Scan |", output)
        self.assertIn("\x1b[", output)
        self.assertIn("configured", output)

    def test_scan_text_output_can_disable_ascii_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local = tmp_path / "local"
            local.mkdir()
            cfg = cli.Config(
                repo_dir=str(tmp_path / "repo"),
                targets=[cli.SkillTarget("claude", str(local), "claude-skills", True)],
            )
            stdout = io.StringIO()

            with patch.object(cli.config, "load_config", return_value=cfg):
                with contextlib.redirect_stdout(stdout):
                    cli.cmd_scan(scan_args(ascii_art=False))

        output = stdout.getvalue()
        self.assertNotIn("Agent Skills Scan", output)
        self.assertIn("Config:", output)


if __name__ == "__main__":
    unittest.main()
