import argparse
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_skills_manager import cli


def write_skill(root: Path, dirname: str, name: str) -> None:
    skill = root / dirname
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: demo skill\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def validate_args(**overrides):
    values = {"location": "local", "target": None, "format": "text"}
    values.update(overrides)
    return argparse.Namespace(**values)


class ValidateDuplicateTests(unittest.TestCase):
    def test_same_name_across_targets_is_not_a_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            claude_local = root / "claude"
            codex_local = root / "codex"
            write_skill(claude_local, "shared", "shared")
            write_skill(codex_local, "shared", "shared")
            cfg = cli.Config(
                repo_dir=str(root / "repo"),
                targets=[
                    cli.SkillTarget("claude", str(claude_local), "claude-skills", True),
                    cli.SkillTarget("codex", str(codex_local), "codex-skills", True),
                ],
            )
            stdout = io.StringIO()
            with patch.object(cli.config, "load_config", return_value=cfg), contextlib.redirect_stdout(stdout):
                cli.cmd_validate(validate_args())

        output = stdout.getvalue()
        self.assertIn("Validation OK.", output)
        self.assertNotIn("duplicate", output)

    def test_duplicate_name_within_one_target_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = root / "claude"
            write_skill(local, "first", "dup")
            write_skill(local, "second", "dup")
            cfg = cli.Config(
                repo_dir=str(root / "repo"),
                targets=[cli.SkillTarget("claude", str(local), "claude-skills", True)],
            )
            stdout = io.StringIO()
            with patch.object(cli.config, "load_config", return_value=cfg), contextlib.redirect_stdout(stdout):
                with self.assertRaises(SystemExit):
                    cli.cmd_validate(validate_args())

        output = stdout.getvalue()
        self.assertIn("duplicate skill name 'dup' in target 'claude'", output)


class SecretScanTests(unittest.TestCase):
    def _validate_with_file(self, filename: str, body: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = root / "claude"
            write_skill(local, "demo", "demo")
            (local / "demo" / filename).write_text(body, encoding="utf-8")
            cfg = cli.Config(
                repo_dir=str(root / "repo"),
                targets=[cli.SkillTarget("claude", str(local), "claude-skills", True)],
            )
            stdout = io.StringIO()
            with patch.object(cli.config, "load_config", return_value=cfg), contextlib.redirect_stdout(stdout):
                cli.cmd_validate(validate_args())
            return stdout.getvalue()

    def test_real_secret_is_reported_with_line_number(self):
        body = "first line\napi_key = \"AKIA1234567890ABCDEFGHIJ\"\n"
        output = self._validate_with_file("creds.txt", body)
        self.assertIn("creds.txt:2: possible secret detected", output)

    def test_inline_pragma_allowlists_the_line(self):
        body = "api_key = \"AKIA1234567890ABCDEFGHIJ\"  # pragma: allowlist secret\n"
        output = self._validate_with_file("creds.txt", body)
        self.assertNotIn("possible secret", output)

    def test_placeholder_values_are_not_reported(self):
        body = "api_key = \"your-api-key-here-1234\"\n"
        output = self._validate_with_file("creds.txt", body)
        self.assertNotIn("possible secret", output)

    def test_private_key_marker_is_reported(self):
        body = "-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----\n"
        output = self._validate_with_file("id_rsa", body)
        self.assertIn("id_rsa:1: possible private key detected", output)


if __name__ == "__main__":
    unittest.main()
