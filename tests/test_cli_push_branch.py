import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_skills_manager import cli


class PushBranchTests(unittest.TestCase):
    def test_push_asks_and_creates_missing_default_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            cfg = cli.Config(repo_dir=str(repo), default_branch="test", targets=[])
            calls = []

            def fake_git_output(args, cwd):
                if args == ["rev-parse", "--verify", "refs/heads/test"]:
                    return ""
                if args == ["remote", "get-url", "origin"]:
                    return "git@github.com:owner/repo.git"
                if args == ["status", "--porcelain"]:
                    return "changed-file"
                if args == ["remote"]:
                    return "origin"
                return ""

            def fake_run(cmd, cwd=None, check=True, capture=False):
                calls.append(cmd)

            with patch.object(cli.config, "load_config", return_value=cfg):
                with patch.object(cli.config, "config_file_exists", return_value=True):
                    with patch.object(cli.sync, "ensure_repo", return_value=repo):
                        with patch.object(cli.gitutil, "repo_dirty", side_effect=[False, True]):
                            with patch.object(cli.gitutil, "maybe_pull"):
                                with patch.object(cli.gitutil, "git_output", side_effect=fake_git_output):
                                    with patch.object(cli.tui, "yes", return_value=True) as yes_mock:
                                        with patch.object(cli.gitutil, "run", side_effect=fake_run):
                                            cli.cmd_push(argparse.Namespace(
                                                message="Sync local agent skills",
                                                dry_run=False,
                                                mirror=False,
                                                no_pull=True,
                                                allow_dirty=False,
                                                create_repo=True,
                                            ))

            yes_mock.assert_called_once()
            self.assertIn(["git", "checkout", "-B", "test"], calls)
            self.assertIn(["git", "push", "-u", "origin", "test"], calls)

    def test_push_exits_if_user_declines_creating_missing_default_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            cfg = cli.Config(repo_dir=str(repo), default_branch="test", targets=[])

            def fake_git_output(args, cwd):
                if args == ["rev-parse", "--verify", "refs/heads/test"]:
                    return ""
                return ""

            with patch.object(cli.config, "load_config", return_value=cfg):
                with patch.object(cli.config, "config_file_exists", return_value=True):
                    with patch.object(cli.sync, "ensure_repo", return_value=repo):
                        with patch.object(cli.gitutil, "repo_dirty", return_value=False):
                            with patch.object(cli.gitutil, "maybe_pull"):
                                with patch.object(cli.gitutil, "git_output", side_effect=fake_git_output):
                                    with patch.object(cli.tui, "yes", return_value=False):
                                        with self.assertRaises(SystemExit) as cm:
                                            cli.cmd_push(argparse.Namespace(
                                                message="Sync local agent skills",
                                                dry_run=False,
                                                mirror=False,
                                                no_pull=True,
                                                allow_dirty=False,
                                                create_repo=True,
                                            ))

            self.assertIn("Branch not found", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
