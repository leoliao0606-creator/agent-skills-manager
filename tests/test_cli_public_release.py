import argparse
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_skills_manager import cli


class PublicReleaseUsabilityTests(unittest.TestCase):
    def test_config_show_marks_implicit_defaults_when_config_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            stdout = io.StringIO()
            with patch.object(cli, "CONFIG_PATH", config_path), contextlib.redirect_stdout(stdout):
                cli.cmd_config_show(argparse.Namespace(format="json"))

        data = json.loads(stdout.getvalue())
        self.assertFalse(data["config_exists"])
        self.assertTrue(data["using_implicit_defaults"])
        self.assertEqual(data["config"], str(config_path))
        self.assertIn("repo_dir", data["settings"])

    def test_scan_json_marks_implicit_defaults_when_config_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            args = argparse.Namespace(
                all=False,
                only=None,
                format="json",
                examples=False,
                limit=0,
            )
            stdout = io.StringIO()
            with patch.object(cli, "CONFIG_PATH", config_path), contextlib.redirect_stdout(stdout):
                cli.cmd_scan(args)

        data = json.loads(stdout.getvalue())
        self.assertFalse(data["config_exists"])
        self.assertTrue(data["using_implicit_defaults"])

    def test_real_push_requires_saved_config_but_dry_run_only_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.json"
            repo = root / "repo"
            local = root / "local"
            (repo / ".git").mkdir(parents=True)
            (local / "demo" ).mkdir(parents=True)
            (local / "demo" / "SKILL.md").write_text("# Demo\n", encoding="utf-8")
            cfg = cli.Config(repo_dir=str(repo), targets=[cli.SkillTarget("demo", str(local), "demo-skills", True)])
            args = argparse.Namespace(
                dry_run=False,
                mirror=False,
                no_pull=True,
                allow_dirty=False,
                create_repo=False,
                force=False,
                strict=False,
                yes=True,
                message="Sync",
            )
            with patch.object(cli, "CONFIG_PATH", config_path), patch.object(cli, "load_config", return_value=cfg):
                with self.assertRaises(SystemExit) as cm:
                    cli.cmd_push(args)
            self.assertIn("No config file found", str(cm.exception))

            args.dry_run = True
            stdout = io.StringIO()
            with patch.object(cli, "CONFIG_PATH", config_path), \
                 patch.object(cli, "load_config", return_value=cfg), \
                 patch.object(cli, "repo_dirty", return_value=False), \
                 contextlib.redirect_stdout(stdout):
                cli.cmd_push(args)
            self.assertIn("using implicit defaults", stdout.getvalue())
            self.assertIn("Dry run complete", stdout.getvalue())

    def test_key_subcommand_help_contains_examples_and_clear_flag_explanations(self):
        parser = cli.build_parser()
        checks = {
            "push": ["Examples:", "--dry-run", "preview file copies, commit, and push without writing"],
            "pull": ["Examples:", "repo skills -> local installed skill directories"],
            "sync": ["Examples:", "safe two-step flow"],
            "new": ["Examples:", "create the skill under the repository target"],
        }
        for command, expected_parts in checks.items():
            stdout = io.StringIO()
            with self.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(stdout):
                parser.parse_args([command, "--help"])
            self.assertEqual(cm.exception.code, 0)
            help_text = stdout.getvalue()
            for part in expected_parts:
                self.assertIn(part, help_text, command)

    def test_readme_has_public_release_onboarding_improvements(self):
        readme = Path("README.md").read_text(encoding="utf-8")
        self.assertIn("https://github.com/leoliao0606-creator/agent-skills-manager.git", readme)
        self.assertIn("3-minute local-only demo", readme)
        self.assertIn("Which command should I use?", readme)
        self.assertIn("python3 -m agent_skills_manager.cli --help", readme)
        self.assertNotIn("https://github.com/<your-user-or-org>/agent-skills-manager.git", readme)


if __name__ == "__main__":
    unittest.main()
