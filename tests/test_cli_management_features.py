import argparse
import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from agent_skills_manager import cli


def ns(**overrides):
    values = {
        "all": False,
        "only": None,
        "format": "text",
        "examples": True,
        "limit": 5,
        "color": "auto",
        "ascii_art": True,
        "dry_run": False,
        "mirror": False,
        "no_pull": True,
        "allow_dirty": False,
        "create_repo": False,
        "force": False,
        "strict": False,
        "yes": True,
        "backup": True,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class ManagementFeatureTests(unittest.TestCase):
    def test_push_dry_run_allows_dirty_repo_and_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            local = root / "local"
            repo.mkdir()
            local.mkdir()
            (repo / ".git").mkdir()
            (local / "demo" / "SKILL.md").parent.mkdir()
            (local / "demo" / "SKILL.md").write_text("# Demo\n", encoding="utf-8")
            cfg = cli.Config(repo_dir=str(repo), targets=[cli.SkillTarget("claude", str(local), "claude-skills", True)])
            stdout = io.StringIO()

            with patch.object(cli, "load_config", return_value=cfg), \
                 patch.object(cli, "repo_dirty", return_value=True), \
                 contextlib.redirect_stdout(stdout):
                cli.cmd_push(ns(dry_run=True, message="Sync"))

        self.assertIn("Repo has uncommitted changes; continuing because this is a dry run", stdout.getvalue())
        self.assertIn("Dry run complete", stdout.getvalue())

    def test_missing_targets_skip_by_default_and_strict_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            (repo / ".git").mkdir()
            missing = root / "missing"
            cfg = cli.Config(repo_dir=str(repo), targets=[cli.SkillTarget("claude", str(missing), "claude-skills", True)])
            stdout = io.StringIO()

            with patch.object(cli, "load_config", return_value=cfg), \
                 patch.object(cli, "repo_dirty", return_value=False), \
                 contextlib.redirect_stdout(stdout):
                cli.cmd_push(ns(message="Sync", dry_run=True))

            self.assertIn("Skipping missing source for claude", stdout.getvalue())
            with patch.object(cli, "load_config", return_value=cfg), \
                 patch.object(cli, "repo_dirty", return_value=False):
                with self.assertRaises(SystemExit):
                    cli.cmd_push(ns(message="Sync", strict=True, dry_run=True))

    def test_doctor_reports_dangerous_repo_path_as_error(self):
        cfg = cli.Config(repo_dir=str(Path.home()), targets=[])
        stdout = io.StringIO()
        with patch.object(cli, "load_config", return_value=cfg), contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as cm:
                cli.cmd_doctor(ns(format="text"))
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("dangerous", stdout.getvalue().lower())

    def test_config_and_target_commands_are_scriptable(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            with patch.object(cli, "CONFIG_PATH", config_path):
                cli.cmd_config_set(argparse.Namespace(key="repo_dir", value="~/skills"))
                cli.cmd_target_add(argparse.Namespace(name="custom", local="~/.custom/skills", repo="custom-skills", disabled=False))
                cli.cmd_target_disable(argparse.Namespace(name="custom"))
                cfg = cli.load_config()

        self.assertEqual(cfg.repo_dir, "~/skills")
        self.assertEqual(cfg.targets[0].name, "custom")
        self.assertFalse(cfg.targets[0].enabled)

    def test_diff_json_reports_add_update_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = root / "local"
            repo = root / "repo"
            local.mkdir()
            (repo / "claude-skills").mkdir(parents=True)
            (local / "new.txt").write_text("new\n", encoding="utf-8")
            (local / "changed.txt").write_text("local\n", encoding="utf-8")
            (repo / "claude-skills" / "changed.txt").write_text("repo\n", encoding="utf-8")
            (repo / "claude-skills" / "old.txt").write_text("old\n", encoding="utf-8")
            cfg = cli.Config(repo_dir=str(repo), targets=[cli.SkillTarget("claude", str(local), "claude-skills", True)])
            stdout = io.StringIO()

            with patch.object(cli, "load_config", return_value=cfg), contextlib.redirect_stdout(stdout):
                cli.cmd_diff(ns(direction="push", mirror=True, format="json"))

        data = json.loads(stdout.getvalue())
        plan = data["plans"][0]
        self.assertEqual(plan["target"], "claude")
        self.assertIn("new.txt", plan["add"])
        self.assertIn("changed.txt", plan["update"])
        self.assertIn("old.txt", plan["delete"])

    def test_validate_rejects_skill_without_required_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = root / "local"
            skill = local / "bad"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("# Bad\n", encoding="utf-8")
            cfg = cli.Config(repo_dir=str(root / "repo"), targets=[cli.SkillTarget("claude", str(local), "claude-skills", True)])
            stdout = io.StringIO()
            with patch.object(cli, "load_config", return_value=cfg), contextlib.redirect_stdout(stdout):
                with self.assertRaises(SystemExit):
                    cli.cmd_validate(ns(location="local", target=None, format="text"))
        self.assertIn("missing frontmatter", stdout.getvalue())

    def test_new_list_search_show_export_import_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = root / "local"
            repo = root / "repo"
            cfg = cli.Config(repo_dir=str(repo), targets=[cli.SkillTarget("claude", str(local), "claude-skills", True)])
            with patch.object(cli, "load_config", return_value=cfg):
                cli.cmd_new(argparse.Namespace(name="Demo Skill", target="claude", repo=False, force=False))
                self.assertTrue((local / "demo-skill" / "SKILL.md").exists())

                listed = io.StringIO()
                with contextlib.redirect_stdout(listed):
                    cli.cmd_list(ns(location="local", target=None, format="names"))
                self.assertEqual(listed.getvalue(), "claude:demo-skill\n")

                searched = io.StringIO()
                with contextlib.redirect_stdout(searched):
                    cli.cmd_search(ns(query="Demo", location="local", target=None, format="names"))
                self.assertIn("claude:demo-skill", searched.getvalue())

                shown = io.StringIO()
                with contextlib.redirect_stdout(shown):
                    cli.cmd_show(argparse.Namespace(spec="claude:demo-skill", repo=False))
                self.assertIn("name: demo-skill", shown.getvalue())

                archive = root / "skills.zip"
                cli.cmd_export(argparse.Namespace(target="claude", output=str(archive), repo=False))
                self.assertTrue(zipfile.is_zipfile(archive))

                imported = root / "imported"
                import_cfg = cli.Config(repo_dir=str(repo), targets=[cli.SkillTarget("claude", str(imported), "claude-skills", True)])
                with patch.object(cli, "load_config", return_value=import_cfg):
                    cli.cmd_import(argparse.Namespace(path=str(archive), target="claude", repo=False, dry_run=False, mirror=False, force=False, strict=False, yes=True))
                self.assertTrue((imported / "demo-skill" / "SKILL.md").exists())

    def test_backup_and_restore_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            local = root / "local"
            local.mkdir()
            (local / "demo.txt").write_text("before\n", encoding="utf-8")
            cfg = cli.Config(repo_dir=str(root / "repo"), backups_dir=str(root / "backups"), targets=[cli.SkillTarget("claude", str(local), "claude-skills", True)])
            backup_path = cli.create_backup(cfg, cfg.targets[0], local)
            (local / "demo.txt").write_text("after\n", encoding="utf-8")

            with patch.object(cli, "load_config", return_value=cfg):
                cli.cmd_restore_backup(argparse.Namespace(path=str(backup_path), target="claude", dry_run=False, mirror=True, yes=True))

            self.assertEqual((local / "demo.txt").read_text(encoding="utf-8"), "before\n")


if __name__ == "__main__":
    unittest.main()
