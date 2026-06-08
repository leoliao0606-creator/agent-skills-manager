"""Tests for the Qt-free service layer.

These must run *without* PySide6 installed, so they only import
``agent_skills_manager.qtgui.services`` (which imports no Qt).
"""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_skills_manager import config
from agent_skills_manager.config import SkillTarget
from agent_skills_manager.qtgui import services


def make_skill(root: Path, name: str, *, frontmatter_name=None, description="test", extra_files=None) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    text = ""
    if frontmatter_name is not None:
        text += f"---\nname: {frontmatter_name}\ndescription: {description}\n---\n"
    text += f"# {name}\n\nbody\n"
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")
    for filename, content in (extra_files or {}).items():
        (skill_dir / filename).write_text(content, encoding="utf-8")
    return skill_dir


class QtServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config_path = self.root / "config.json"
        # Isolate config storage and neutralise candidate-target merging so the
        # dev machine's real ~/.claude/skills etc. never leak into counts.
        self._patchers = [
            patch.object(config, "CONFIG_PATH", self.config_path),
            patch.object(config, "candidate_targets", return_value=[]),
        ]
        for p in self._patchers:
            p.start()
        config.ACTIVE_PROFILE = None

    def tearDown(self) -> None:
        for p in self._patchers:
            p.stop()
        self.tmp.cleanup()

    # --- helpers ---
    def write_config(self, targets, **kwargs) -> config.Config:
        cfg = config.Config(
            repo_dir=str(self.root / "repo"),
            backups_dir=str(self.root / "backups"),
            targets=targets,
            **kwargs,
        )
        config.save_config(cfg)
        return cfg

    # --- overview ---
    def test_overview_without_config_uses_implicit_defaults(self):
        status = services.load_overview_status()
        self.assertFalse(status.config_exists)
        self.assertTrue(status.using_implicit_defaults)
        self.assertEqual(status.target_count, 0)
        self.assertEqual(status.local_skill_count, 0)

    def test_overview_with_config_counts_skills(self):
        local = self.root / "claude-local"
        make_skill(local, "one", frontmatter_name="one")
        make_skill(local, "two", frontmatter_name="two")
        make_skill(self.root / "repo" / "claude-skills", "one", frontmatter_name="one")
        self.write_config([SkillTarget("claude", str(local), "claude-skills", True)])

        status = services.load_overview_status()
        self.assertTrue(status.config_exists)
        self.assertEqual(status.target_count, 1)
        self.assertEqual(status.enabled_target_count, 1)
        self.assertEqual(status.local_skill_count, 2)
        self.assertEqual(status.repo_skill_count, 1)

    # --- targets ---
    def test_load_target_statuses_reports_status(self):
        local = self.root / "claude-local"
        make_skill(local, "one", frontmatter_name="one")
        self.write_config([
            SkillTarget("claude", str(local), "claude-skills", True),
            SkillTarget("codex", str(self.root / "missing"), "codex-skills", False),
        ])
        statuses = {s.name: s for s in services.load_target_statuses()}
        self.assertEqual(statuses["claude"].status, "configured")
        self.assertEqual(statuses["claude"].local_skills, 1)
        self.assertEqual(statuses["codex"].status, "not exist")

    def test_save_targets_round_trips(self):
        self.write_config([SkillTarget("claude", str(self.root / "c"), "claude-skills", True)])
        services.save_targets([SkillTarget("custom", "~/custom/skills", "custom-skills", True)])
        statuses = services.load_target_statuses()
        self.assertEqual([s.name for s in statuses], ["custom"])

    # --- sync preview ---
    def _conflict_fixture(self):
        local = self.root / "claude-local"
        repo_sub = self.root / "repo" / "claude-skills"
        make_skill(local, "added", frontmatter_name="added")
        make_skill(local, "mod", frontmatter_name="mod", description="local")
        make_skill(repo_sub, "mod", frontmatter_name="mod", description="repo")
        make_skill(local, "conf", frontmatter_name="conf", description="local")
        make_skill(repo_sub, "conf", frontmatter_name="conf", description="repo")
        make_skill(repo_sub, "del", frontmatter_name="del")
        self.write_config([SkillTarget("claude", str(local), "claude-skills", True)])
        # Record a base hash for conf/SKILL.md that matches neither side -> conflict.
        repo_key = str(config.expand(self.root / "repo"))
        config.save_sync_state({"repos": {repo_key: {"targets": {"claude": {"conf/SKILL.md": "0" * 64}}}}})

    def test_build_sync_preview_classifies_changes(self):
        self._conflict_fixture()
        preview = services.build_sync_preview("push", mirror=False)
        self.assertEqual(preview.total_added, 1)
        self.assertEqual(preview.total_modified, 1)
        self.assertEqual(preview.total_conflict, 1)
        self.assertEqual(preview.total_deleted, 0)
        self.assertTrue(preview.has_conflict)

    def test_build_sync_preview_mirror_reports_deletes(self):
        self._conflict_fixture()
        preview = services.build_sync_preview("push", mirror=True)
        self.assertGreaterEqual(preview.total_deleted, 1)
        statuses = {c.status for t in preview.targets for c in t.files}
        self.assertIn("deleted", statuses)

    # --- validation ---
    def test_run_validation_classifies_findings(self):
        local = self.root / "claude-local"
        make_skill(local, "ok", frontmatter_name="ok")
        make_skill(local, "nofm")  # no frontmatter -> metadata error
        make_skill(local, "dupA", frontmatter_name="dup")
        make_skill(local, "dupB", frontmatter_name="dup")  # duplicate name
        make_skill(local, "leak", frontmatter_name="leak",
                   extra_files={"creds.txt": 'api_key = "AbCd1234EfGh5678IjKl9012"\n'})
        self.write_config([SkillTarget("claude", str(local), "claude-skills", True)])

        findings = services.run_validation("local", "claude")
        kinds = {f.kind for f in findings}
        self.assertIn("metadata", kinds)
        self.assertIn("duplicate", kinds)
        self.assertIn("secret", kinds)
        self.assertTrue(any(f.kind == "secret" and f.severity == "warning" for f in findings))

    # --- backups ---
    def test_list_backups_walks_target_dirs(self):
        backup_target = self.root / "backups" / "20260101-120000" / "claude"
        backup_target.mkdir(parents=True)
        (backup_target / "SKILL.md").write_text("data", encoding="utf-8")
        self.write_config([SkillTarget("claude", str(self.root / "c"), "claude-skills", True)])

        entries = services.list_backups()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].date, "20260101-120000")
        self.assertEqual(entries[0].target, "claude")
        self.assertGreater(entries[0].size_bytes, 0)

    # --- settings + profiles ---
    def test_settings_round_trip(self):
        before = services.load_config_settings()
        self.assertFalse(before.config_exists)
        services.save_config_settings(services.ConfigSettings(
            repo_dir="~/my-repo",
            remote_url="git@example.com:me/skills.git",
            default_branch="dev",
            backups_dir="~/my-backups",
            excludes=["*.tmp", "secret/"],
            config_path="",
            config_exists=True,
        ))
        after = services.load_config_settings()
        self.assertTrue(after.config_exists)
        self.assertEqual(after.repo_dir, "~/my-repo")
        self.assertEqual(after.default_branch, "dev")
        self.assertEqual(after.excludes, ["*.tmp", "secret/"])

    def test_list_profiles_includes_default_and_created(self):
        self.assertEqual(services.list_profiles(), ["default"])
        config.save_config(config.Config(repo_dir=str(self.root / "repo")), profile="work")
        self.assertIn("work", services.list_profiles())

    # --- preview + comparison ---
    def test_preview_target_returns_summaries(self):
        local = self.root / "claude-local"
        make_skill(local, "alpha", frontmatter_name="alpha", description="first")
        self.write_config([SkillTarget("claude", str(local), "claude-skills", True)])
        summaries = services.preview_target("claude", "local")
        self.assertEqual([s.name for s in summaries], ["alpha"])
        self.assertEqual(summaries[0].meta_name, "alpha")
        self.assertEqual(summaries[0].description, "first")
        self.assertEqual(summaries[0].location, "local")

    def test_compare_targets_statuses(self):
        a_local = self.root / "a-local"
        b_local = self.root / "b-local"
        make_skill(a_local, "shared-same", frontmatter_name="shared-same")
        make_skill(b_local, "shared-same", frontmatter_name="shared-same")
        make_skill(a_local, "shared-diff", frontmatter_name="shared-diff", description="a")
        make_skill(b_local, "shared-diff", frontmatter_name="shared-diff", description="b")
        make_skill(a_local, "only-a", frontmatter_name="only-a")
        make_skill(b_local, "only-b", frontmatter_name="only-b")
        self.write_config([
            SkillTarget("agentA", str(a_local), "a-skills", True),
            SkillTarget("agentB", str(b_local), "b-skills", True),
        ])
        comparison = services.compare_targets("agentA", "local", "agentB", "local")
        statuses = {r.name: r.status for r in comparison.rows}
        self.assertEqual(statuses["shared-same"], "same")
        self.assertEqual(statuses["shared-diff"], "different")
        self.assertEqual(statuses["only-a"], "only_a")
        self.assertEqual(statuses["only-b"], "only_b")

    def test_compare_same_target_local_vs_repo(self):
        local = self.root / "claude-local"
        repo_sub = self.root / "repo" / "claude-skills"
        make_skill(local, "alpha", frontmatter_name="alpha", description="local")
        make_skill(repo_sub, "alpha", frontmatter_name="alpha", description="repo")
        self.write_config([SkillTarget("claude", str(local), "claude-skills", True)])
        comparison = services.compare_targets("claude", "local", "claude", "repo")
        statuses = {r.name: r.status for r in comparison.rows}
        self.assertEqual(statuses["alpha"], "different")

    def test_skill_unified_diff_nonempty_when_different(self):
        a_local = self.root / "a-local"
        b_local = self.root / "b-local"
        a = make_skill(a_local, "alpha", frontmatter_name="alpha", description="a")
        b = make_skill(b_local, "alpha", frontmatter_name="alpha", description="b")
        diff = services.skill_unified_diff(str(a / "SKILL.md"), str(b / "SKILL.md"), "A", "B")
        self.assertIn("description: a", diff)
        self.assertIn("description: b", diff)
        same = services.skill_unified_diff(str(a / "SKILL.md"), str(a / "SKILL.md"), "A", "B")
        self.assertEqual(same, "")


if __name__ == "__main__":
    unittest.main()
