"""Thin wrappers around the ``git`` CLI and small repository state helpers."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from . import tui


def run(cmd: List[str], cwd: Optional[Path] = None, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    kwargs = {"cwd": str(cwd) if cwd else None, "text": True}
    if capture:
        kwargs.update({"stdout": subprocess.PIPE, "stderr": subprocess.PIPE})
    print("$", " ".join(cmd), file=sys.stderr)
    proc = subprocess.run(cmd, **kwargs)
    if check and proc.returncode != 0:
        if capture:
            sys.stderr.write(proc.stdout or "")
            sys.stderr.write(proc.stderr or "")
        raise SystemExit(proc.returncode)
    return proc


def git_available() -> bool:
    return shutil.which("git") is not None


def git_output(args: List[str], cwd: Path) -> str:
    proc = run(["git"] + args, cwd=cwd, check=False, capture=True)
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def maybe_pull(repo: Path, no_pull: bool) -> None:
    if no_pull:
        return
    if git_output(["remote"], repo):
        run(["git", "pull", "--ff-only"], cwd=repo)


def repo_dirty(repo: Path) -> bool:
    return bool(git_output(["status", "--porcelain"], repo))


def local_branch_exists(repo: Path, branch: str) -> bool:
    return bool(git_output(["rev-parse", "--verify", f"refs/heads/{branch}"], repo))


def ensure_push_branch(repo: Path, branch: str) -> None:
    if local_branch_exists(repo, branch):
        run(["git", "checkout", branch], cwd=repo)
        return
    if not tui.yes(f"Local branch '{branch}' does not exist. Create it from the current HEAD now", True):
        raise SystemExit(f"Branch not found: {branch}. Create it first or choose an existing default branch.")
    run(["git", "checkout", "-B", branch], cwd=repo)


def collect_git_status(repo: Path) -> Dict[str, object]:
    if (repo / ".git").exists():
        return {
            "initialized": True,
            "status": git_output(["status", "--short", "--branch"], repo) or "clean",
            "remote": git_output(["remote", "-v"], repo),
        }
    return {"initialized": False, "status": "Repo is not initialized yet.", "remote": ""}
