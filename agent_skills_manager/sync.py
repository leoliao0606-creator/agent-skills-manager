"""Copy planning and application, repository safety checks, and backups.

The copy plan is a plain dict describing add/update/delete/conflict/unchanged
sets between a source and destination tree. Plans are built once and can be
previewed (diff) or applied (push/pull/import/restore).
"""
from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import config, fsutil, gitutil, tui
from .config import Config, SkillTarget


def build_copy_plan(
    src: Path,
    dst: Path,
    dry_run: bool = False,
    mirror: bool = False,
    patterns: Optional[List[str]] = None,
    base_hashes: Optional[Dict[str, str]] = None,
) -> Dict[str, object]:
    """Return an additive/mirror copy plan from src to dst."""
    del dry_run  # Plan shape is independent of dry-run; kept for API compatibility.
    patterns = patterns or []
    plan: Dict[str, object] = {
        "source": str(src),
        "destination": str(dst),
        "missing_source": not src.exists(),
        "add": [],
        "update": [],
        "delete": [],
        "conflict": [],
        "unchanged": [],
    }
    if not src.exists():
        return plan
    src_hashes = fsutil.collect_file_hashes(src, patterns)
    dst_hashes = fsutil.collect_file_hashes(dst, patterns)
    base_hashes = base_hashes or {}

    for rel, src_hash in sorted(src_hashes.items()):
        dst_hash = dst_hashes.get(rel)
        if dst_hash is None:
            plan["add"].append(rel)  # type: ignore[index]
        elif dst_hash == src_hash:
            plan["unchanged"].append(rel)  # type: ignore[index]
        else:
            base_hash = base_hashes.get(rel)
            if base_hash and src_hash != base_hash and dst_hash != base_hash:
                plan["conflict"].append(rel)  # type: ignore[index]
            else:
                plan["update"].append(rel)  # type: ignore[index]

    if mirror:
        for rel in sorted(set(dst_hashes) - set(src_hashes)):
            plan["delete"].append(rel)  # type: ignore[index]
    return plan


def plan_change_count(plan: Dict[str, object]) -> int:
    return sum(len(plan[key]) for key in ["add", "update", "delete", "conflict"])  # type: ignore[arg-type]


def plan_write_count(plan: Dict[str, object]) -> int:
    return sum(len(plan[key]) for key in ["add", "update", "delete"])  # type: ignore[arg-type]


def print_plan(plan: Dict[str, object], label: str = "") -> None:
    if label:
        print(label)
    if plan.get("missing_source"):
        print(f"  missing source: {plan['source']}")
        return
    for key, title in [("add", "add"), ("update", "update"), ("delete", "delete"), ("conflict", "conflict")]:
        for rel in plan[key]:  # type: ignore[index]
            print(f"  {title}: {rel}")
    if plan_change_count(plan) == 0:
        print("  no file changes")


def apply_copy_plan(src: Path, dst: Path, plan: Dict[str, object], dry_run: bool = False) -> Tuple[int, int]:
    if plan.get("missing_source"):
        raise SystemExit(f"Missing source directory: {src}")
    raw_conflicts = plan.get("conflict", [])
    conflicts = [str(rel) for rel in raw_conflicts] if isinstance(raw_conflicts, list) else []
    if conflicts:
        raise SystemExit("Conflicting files detected. Re-run with --force after reviewing: " + ", ".join(conflicts))
    changed = 0
    deleted = 0
    for key in ["add", "update"]:
        for rel in plan[key]:  # type: ignore[index]
            print(f"  copy {rel}")
            changed += 1
            if not dry_run:
                source = src / rel
                target = dst / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    for rel in plan["delete"]:  # type: ignore[index]
        print(f"  delete {rel}")
        deleted += 1
        if not dry_run:
            target = dst / rel
            if target.exists():
                target.unlink()
    if not dry_run and dst.exists():
        for item in sorted([p for p in dst.rglob("*") if p.is_dir()], reverse=True):
            try:
                item.rmdir()
            except OSError:
                pass
    return changed, deleted


def copy_tree(
    src: Path,
    dst: Path,
    dry_run: bool = False,
    mirror: bool = False,
    excludes: Optional[List[str]] = None,
    base_hashes: Optional[Dict[str, str]] = None,
) -> Tuple[int, int]:
    """Copy files from src to dst. Returns (copied_or_updated, deleted)."""
    patterns = excludes if excludes is not None else []
    plan = build_copy_plan(src, dst, dry_run=dry_run, mirror=mirror, patterns=patterns, base_hashes=base_hashes)
    return apply_copy_plan(src, dst, plan, dry_run=dry_run)


def serializable_plan(plan: Dict[str, object]) -> Dict[str, object]:
    return {key: value for key, value in plan.items() if key != "unchanged"}


def dangerous_repo_reasons(repo: Path, cfg: Optional[Config] = None) -> List[str]:
    reasons: List[str] = []
    home = Path.home().resolve()
    root = Path(repo.anchor).resolve() if repo.anchor else Path("/").resolve()
    if repo in {root, home, home.parent}:
        reasons.append("dangerous repo path: use a dedicated checkout directory, not /, your home directory, or a parent home directory")
    if repo.exists() and not (repo / ".git").exists():
        try:
            entries = [p for p in repo.iterdir() if p.name not in {".git", ".DS_Store"}]
        except OSError:
            entries = []
        if entries:
            reasons.append("repo path exists, is not a git repository, and is not empty")
    if cfg:
        for target in cfg.targets or []:
            local = config.expand(target.local_dir)
            if repo == local:
                reasons.append(f"repo path is the same as target '{target.name}' local skill directory")
            if repo in local.parents:
                reasons.append(f"repo path is inside target '{target.name}' local skill directory")
            if local in repo.parents:
                reasons.append(f"target '{target.name}' local skill directory is inside the repo path")
    return reasons


def ensure_safe_repo_path(cfg: Config, repo: Path) -> None:
    reasons = dangerous_repo_reasons(repo, cfg)
    if reasons:
        raise SystemExit("Unsafe repository path:\n  - " + "\n  - ".join(reasons))


def ensure_repo(cfg: Config, create: bool = False, clone: bool = False) -> Path:
    repo = config.expand(cfg.repo_dir)
    if repo.exists() and (repo / ".git").exists():
        return repo
    ensure_safe_repo_path(cfg, repo)
    if clone and cfg.remote_url:
        repo.parent.mkdir(parents=True, exist_ok=True)
        gitutil.run(["git", "clone", cfg.remote_url, str(repo)])
        return repo
    if create:
        repo.mkdir(parents=True, exist_ok=True)
        gitutil.run(["git", "init", "-b", cfg.default_branch], cwd=repo, check=False)
        if not (repo / ".git").exists():  # older git may not support -b
            gitutil.run(["git", "init"], cwd=repo)
            gitutil.run(["git", "checkout", "-B", cfg.default_branch], cwd=repo)
        if cfg.remote_url and not gitutil.git_output(["remote", "get-url", "origin"], repo):
            gitutil.run(["git", "remote", "add", "origin", cfg.remote_url], cwd=repo)
        return repo
    raise SystemExit(f"Repo not found: {repo}. Run: agent-skills setup")


def target_source_destination(cfg: Config, repo: Path, target: SkillTarget, direction: str) -> Tuple[Path, Path]:
    if direction == "push":
        return config.expand(target.local_dir), repo / target.repo_dir
    if direction == "pull":
        return repo / target.repo_dir, config.expand(target.local_dir)
    raise ValueError(direction)


def build_target_plan(cfg: Config, repo: Path, target: SkillTarget, direction: str, mirror: bool, state: Optional[Dict[str, object]] = None) -> Dict[str, object]:
    src, dst = target_source_destination(cfg, repo, target, direction)
    patterns = fsutil.read_ignore_patterns(src, dst, cfg=cfg)
    base_hashes = config.state_target_hashes(state or config.load_sync_state(), repo, target)
    plan = build_copy_plan(src, dst, mirror=mirror, patterns=patterns, base_hashes=base_hashes)
    plan["target"] = target.name
    plan["direction"] = direction
    return plan


def fail_or_skip_missing(plan: Dict[str, object], target: SkillTarget, strict: bool) -> bool:
    if not plan.get("missing_source"):
        return False
    message = f"Skipping missing source for {target.name}: {plan['source']}"
    if strict:
        raise SystemExit(message)
    print(message)
    return True


def maybe_confirm_mirror(args: argparse.Namespace, plans: List[Dict[str, object]]) -> None:
    delete_count = sum(len(plan["delete"]) for plan in plans)  # type: ignore[arg-type]
    if getattr(args, "mirror", False) and delete_count:
        tui.confirm_destructive(args, f"Mirror mode will delete {delete_count} files. Continue")


def mark_state_after_sync(state: Dict[str, object], repo: Path, target: SkillTarget, cfg: Config) -> None:
    repo_target = repo / target.repo_dir
    patterns = fsutil.read_ignore_patterns(repo_target, config.expand(target.local_dir), cfg=cfg)
    config.update_state_target(state, repo, target, fsutil.collect_file_hashes(repo_target, patterns))


def create_backup(cfg: Config, target: SkillTarget, local: Path) -> Path:
    backups_root = config.expand(cfg.backups_dir)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    destination = backups_root / stamp / target.name
    counter = 1
    while destination.exists():
        destination = backups_root / f"{stamp}-{counter}" / target.name
        counter += 1
    destination.parent.mkdir(parents=True, exist_ok=True)
    if local.exists():
        shutil.copytree(local, destination, dirs_exist_ok=True)
    else:
        destination.mkdir(parents=True, exist_ok=True)
    print(f"Backup [{target.name}]: {destination}")
    return destination
