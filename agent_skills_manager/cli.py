#!/usr/bin/env python3
"""Manage private AI agent skill repositories.

This tool intentionally uses only the Python standard library so it can run on a
fresh VPS or laptop without bootstrapping dependencies.
"""
from __future__ import annotations

import argparse
import fnmatch
import glob
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import zipfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    import readline  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - readline is not available on some platforms.
    readline = None  # type: ignore[assignment]

APP_NAME = "agent-skills-manager"
DEFAULT_REPO = "~/agent-skills-library"
DEFAULT_BACKUPS_DIR = "~/.agent-skills-manager/backups"
DEFAULT_EXCLUDES = [
    ".git/",
    ".DS_Store",
    "Thumbs.db",
    "__pycache__/",
    "*.pyc",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".env",
    ".venv/",
    "venv/",
    "node_modules/",
]
ACTIVE_PROFILE: Optional[str] = None


def default_config_path() -> Path:
    """Return a per-user config path that works on Windows, macOS, and Linux."""
    override = os.environ.get("AGENT_SKILLS_CONFIG")
    if override:
        return Path(override)
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / APP_NAME / "config.json"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME / "config.json"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME / "config.json"


CONFIG_PATH = default_config_path()


@dataclass
class SkillTarget:
    name: str
    local_dir: str
    repo_dir: str
    enabled: bool = True


@dataclass
class Config:
    repo_dir: str
    remote_url: str = ""
    default_branch: str = "main"
    targets: Optional[List[SkillTarget]] = None
    backups_dir: str = DEFAULT_BACKUPS_DIR
    excludes: Optional[List[str]] = None

    def __post_init__(self) -> None:
        if self.targets is None:
            self.targets = default_targets()
        if self.excludes is None:
            self.excludes = list(DEFAULT_EXCLUDES)


def profile_dir() -> Path:
    return CONFIG_PATH.parent / "profiles"


def config_path_for_profile(profile: Optional[str] = None) -> Path:
    selected = profile if profile is not None else ACTIVE_PROFILE
    if selected and selected != "default":
        safe = slugify(selected)
        return profile_dir() / f"{safe}.json"
    return CONFIG_PATH


def current_config_path() -> Path:
    return config_path_for_profile()


def state_path_for_profile(profile: Optional[str] = None) -> Path:
    cfg_path = config_path_for_profile(profile)
    if profile and profile != "default":
        return cfg_path.with_suffix(".state.json")
    if ACTIVE_PROFILE and ACTIVE_PROFILE != "default":
        return cfg_path.with_suffix(".state.json")
    return cfg_path.parent / "sync-state.json"


def expand(path: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(path))).resolve()


def has_skills(path: str) -> bool:
    expanded = expand(path)
    if not expanded.exists():
        return False
    try:
        return any(expanded.rglob("SKILL.md"))
    except OSError:
        return False


def candidate_targets() -> List[SkillTarget]:
    """Known skill locations users can enable during setup.

    All paths are configurable. The list is intentionally broad so setup works
    as a terminal checklist for different agent ecosystems.
    """
    candidates = [
        SkillTarget("claude", "~/.claude/skills", "claude-skills", False),
        SkillTarget("codex", "~/.codex/skills", "codex-skills", False),
        SkillTarget("gemini", "~/.gemini/skills", "gemini-skills", False),
        SkillTarget("cursor", "~/.cursor/skills", "cursor-skills", False),
        SkillTarget("windsurf", "~/.windsurf/skills", "windsurf-skills", False),
        SkillTarget("opencode", "~/.config/opencode/skills", "opencode-skills", False),
        SkillTarget("goose", "~/.config/goose/skills", "goose-skills", False),
        SkillTarget("aider", "~/.aider/skills", "aider-skills", False),
        SkillTarget("continue", "~/.continue/skills", "continue-skills", False),
        SkillTarget("hermes", "~/.hermes/skills", "hermes-skills", False),
    ]
    for target in candidates:
        target.enabled = has_skills(target.local_dir)
    return candidates


def default_targets() -> List[SkillTarget]:
    return candidate_targets()


def detect_default_repo() -> str:
    return DEFAULT_REPO


def merge_candidate_targets(targets: List[SkillTarget]) -> List[SkillTarget]:
    """Keep user targets and append newly-known candidates without clobbering config."""
    merged = list(targets)
    names = {target.name for target in merged}
    for candidate in candidate_targets():
        if candidate.name not in names:
            candidate.enabled = False
            merged.append(candidate)
    return merged


def config_file_exists(profile: Optional[str] = None) -> bool:
    return config_path_for_profile(profile).exists()


def load_config(profile: Optional[str] = None) -> Config:
    path = config_path_for_profile(profile)
    if not path.exists():
        return Config(repo_dir=str(detect_default_repo()), targets=default_targets())
    data = json.loads(path.read_text(encoding="utf-8"))
    targets = [SkillTarget(**t) for t in data.get("targets", [])]
    if targets:
        targets = merge_candidate_targets(targets)
    else:
        targets = default_targets()
    return Config(
        repo_dir=data.get("repo_dir", str(detect_default_repo())),
        remote_url=data.get("remote_url", ""),
        default_branch=data.get("default_branch", "main"),
        targets=targets,
        backups_dir=data.get("backups_dir", DEFAULT_BACKUPS_DIR),
        excludes=data.get("excludes", list(DEFAULT_EXCLUDES)),
    )


def save_config(cfg: Config, profile: Optional[str] = None) -> None:
    path = config_path_for_profile(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(cfg)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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


def count_skills(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for _ in path.rglob("SKILL.md"))


def iter_skill_dirs(path: Path) -> Iterable[Path]:
    if not path.exists():
        return []
    return sorted(p.parent for p in path.rglob("SKILL.md"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_ignore_patterns(*roots: Path, cfg: Optional[Config] = None) -> List[str]:
    patterns = list((cfg.excludes if cfg and cfg.excludes else DEFAULT_EXCLUDES))
    for root in roots:
        ignore = root / ".agent-skills-ignore"
        if ignore.exists():
            for line in ignore.read_text(encoding="utf-8", errors="ignore").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    patterns.append(stripped)
    return patterns


def rel_matches_pattern(rel: str, pattern: str) -> bool:
    pattern = pattern.strip()
    if not pattern or pattern.startswith("#"):
        return False
    rel = rel.replace(os.sep, "/")
    pattern = pattern.replace(os.sep, "/")
    directory_pattern = pattern.endswith("/")
    pattern = pattern.rstrip("/")
    name = rel.rsplit("/", 1)[-1]
    if directory_pattern:
        return rel == pattern or rel.startswith(pattern + "/") or any(fnmatch.fnmatch(part, pattern) for part in rel.split("/"))
    return fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(name, pattern) or rel.startswith(pattern + "/")


def should_exclude(rel: Path, patterns: List[str]) -> bool:
    rel_s = rel.as_posix()
    return any(rel_matches_pattern(rel_s, pattern) for pattern in patterns)


def collect_file_hashes(root: Path, patterns: Optional[List[str]] = None) -> Dict[str, str]:
    if not root.exists():
        return {}
    patterns = patterns or []
    hashes: Dict[str, str] = {}
    for item in root.rglob("*"):
        if not item.is_file():
            continue
        rel = item.relative_to(root)
        if should_exclude(rel, patterns):
            continue
        hashes[rel.as_posix()] = sha256_file(item)
    return hashes


def load_sync_state() -> Dict[str, object]:
    path = state_path_for_profile()
    if not path.exists():
        return {"repos": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"repos": {}}


def save_sync_state(state: Dict[str, object]) -> None:
    path = state_path_for_profile()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def state_target_hashes(state: Dict[str, object], repo: Path, target: SkillTarget) -> Dict[str, str]:
    repos = state.get("repos", {})
    if not isinstance(repos, dict):
        return {}
    repo_state = repos.get(str(repo), {})
    if not isinstance(repo_state, dict):
        return {}
    targets = repo_state.get("targets", {})
    if not isinstance(targets, dict):
        return {}
    hashes = targets.get(target.name, {})
    return hashes if isinstance(hashes, dict) else {}


def update_state_target(state: Dict[str, object], repo: Path, target: SkillTarget, hashes: Dict[str, str]) -> None:
    repos = state.setdefault("repos", {})
    if not isinstance(repos, dict):
        state["repos"] = repos = {}
    repo_state = repos.setdefault(str(repo), {})
    if not isinstance(repo_state, dict):
        repos[str(repo)] = repo_state = {}
    targets = repo_state.setdefault("targets", {})
    if not isinstance(targets, dict):
        repo_state["targets"] = targets = {}
    targets[target.name] = hashes


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
    src_hashes = collect_file_hashes(src, patterns)
    dst_hashes = collect_file_hashes(dst, patterns)
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
            local = expand(target.local_dir)
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
    repo = expand(cfg.repo_dir)
    if repo.exists() and (repo / ".git").exists():
        return repo
    ensure_safe_repo_path(cfg, repo)
    if clone and cfg.remote_url:
        repo.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", cfg.remote_url, str(repo)])
        return repo
    if create:
        repo.mkdir(parents=True, exist_ok=True)
        run(["git", "init", "-b", cfg.default_branch], cwd=repo, check=False)
        if not (repo / ".git").exists():  # older git may not support -b
            run(["git", "init"], cwd=repo)
            run(["git", "checkout", "-B", cfg.default_branch], cwd=repo)
        if cfg.remote_url and not git_output(["remote", "get-url", "origin"], repo):
            run(["git", "remote", "add", "origin", cfg.remote_url], cwd=repo)
        return repo
    raise SystemExit(f"Repo not found: {repo}. Run: agent-skills setup")


def read_answer(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    ans = input(f"{prompt}{suffix}: ").strip()
    return ans or default


def complete_path(text: str, state: int) -> Optional[str]:
    """readline completer for filesystem paths, preserving a leading ~/."""
    if not text:
        text = "~"
    expanded = os.path.expandvars(os.path.expanduser(text))
    matches = glob.glob(expanded + "*")
    completions: List[str] = []
    for match in sorted(matches):
        completion = match
        if text.startswith("~"):
            home = str(Path.home())
            if completion == home:
                completion = "~"
            elif completion.startswith(home + os.sep):
                completion = "~" + completion[len(home):]
        if os.path.isdir(os.path.expanduser(completion)):
            completion += os.sep
        completions.append(completion)
    try:
        return completions[state]
    except IndexError:
        return None


def read_path_answer(prompt: str, default: str = "") -> str:
    """Read a filesystem path prompt with Tab completion when readline exists."""
    if readline is None:
        return read_answer(prompt, default)
    previous_completer = readline.get_completer()
    readline.set_completer(complete_path)
    readline.parse_and_bind("tab: complete")
    try:
        return read_answer(prompt, default)
    finally:
        readline.set_completer(previous_completer)


def yes(prompt: str, default: bool = True) -> bool:
    d = "Y/n" if default else "y/N"
    ans = input(f"{prompt} [{d}]: ").strip().lower()
    if not ans:
        return default
    return ans in {"y", "yes", "是", "好", "1"}


def confirm_destructive(args: argparse.Namespace, message: str) -> None:
    if getattr(args, "dry_run", False) or getattr(args, "yes", False):
        return
    if not yes(message, False):
        raise SystemExit("Cancelled.")


def parse_selection(text: str, total: int) -> List[int]:
    text = text.strip().lower()
    if text in {"all", "a", "*"}:
        return list(range(total))
    if text in {"none", "n"}:
        return []
    selected = set()
    for raw_part in text.replace(" ", ",").split(","):
        part = raw_part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start = int(start_s)
            end = int(end_s)
            if start > end:
                start, end = end, start
            selected.update(range(start - 1, end))
        else:
            selected.add(int(part) - 1)
    invalid = [i + 1 for i in selected if i < 0 or i >= total]
    if invalid:
        raise ValueError(f"selection out of range: {invalid}")
    return sorted(selected)


def read_multiselect(prompt: str, options: List[SkillTarget], default_indexes: List[int]) -> List[int]:
    print(prompt)
    for idx, target in enumerate(options, start=1):
        mark = "x" if idx - 1 in default_indexes else " "
        found = count_skills(expand(target.local_dir))
        print(f"  [{mark}] {idx:2d}. {target.name:<10} {target.local_dir:<30} -> {target.repo_dir:<18} skills={found}")
    default_text = ",".join(str(i + 1) for i in default_indexes) or "none"
    print("\nSelect by number, comma list, or range. Examples: 1,2,5 or 1-4. Use 'all' or 'none'.")
    while True:
        ans = input(f"Enabled agents [{default_text}]: ").strip()
        if not ans:
            return default_indexes
        try:
            return parse_selection(ans, len(options))
        except ValueError as exc:
            print(f"Invalid selection: {exc}")


def cmd_setup(args: argparse.Namespace) -> None:
    del args
    if not git_available():
        raise SystemExit("git is required. Install git first.")
    cfg = load_config()
    cfg.repo_dir = detect_default_repo()
    cfg.remote_url = ""
    cfg.default_branch = "main"
    print("Agent Skills Manager setup wizard")
    print("I will scan installed skill folders and help you connect them to a private repo.\n")
    print("Local repo checkout path = the local Git checkout directory for your skills repo.")
    print("  Example: ~/agent-skills-library")
    print("  This should be the repo folder containing .git, not your home directory like /home or ~.\n")

    cfg.repo_dir = read_path_answer("Local repo checkout path", cfg.repo_dir)
    cfg.remote_url = read_answer("Git remote URL (SSH or HTTPS; empty is OK for local-only)", "")
    cfg.default_branch = read_answer("Default branch", cfg.default_branch or "main")

    targets_by_name = {t.name: t for t in candidate_targets()}
    for existing in cfg.targets or []:
        targets_by_name[existing.name] = existing
    available_targets = list(targets_by_name.values())
    default_indexes = [idx for idx, target in enumerate(available_targets) if target.enabled]
    selected_indexes = read_multiselect("\nChoose which agents to sync:", available_targets, default_indexes)
    selected_set = set(selected_indexes)

    new_targets: List[SkillTarget] = []
    for idx, t in enumerate(available_targets):
        enable = idx in selected_set
        if enable:
            print(f"\n[{t.name}]")
            local = read_path_answer(f"{t.name} local skills directory", t.local_dir)
            found = count_skills(expand(local))
            print(f"  found {found} skills in {expand(local)}")
            repo_dir = read_answer(f"{t.name} directory inside repo", t.repo_dir)
            new_targets.append(SkillTarget(t.name, local, repo_dir, True))
        else:
            new_targets.append(SkillTarget(t.name, t.local_dir, t.repo_dir, False))

    cfg.targets = new_targets
    save_config(cfg)
    print(f"\nSaved config: {current_config_path()}")

    if not (expand(cfg.repo_dir) / ".git").exists():
        if cfg.remote_url and yes("Clone the remote repo now", True):
            ensure_repo(cfg, clone=True)
        elif yes("Create a new local git repo now", True):
            ensure_repo(cfg, create=True)

    if yes("Do an initial push of installed local skills into the repo", True):
        cmd_push(argparse.Namespace(message="Initial skill sync", dry_run=False, mirror=False, no_pull=True, allow_dirty=False, create_repo=True, force=False, strict=False, yes=False))
    else:
        print("Next: agent-skills push --dry-run")


# ----- Output helpers -----

def ansi_enabled(args: argparse.Namespace) -> bool:
    mode = getattr(args, "color", "auto")
    if mode == "always":
        return True
    if mode == "never" or os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def color_text(text: str, color: str, args: argparse.Namespace) -> str:
    if not ansi_enabled(args):
        return text
    colors = {
        "green": "\033[32m",
        "yellow": "\033[33m",
        "red": "\033[31m",
        "cyan": "\033[36m",
        "blue": "\033[34m",
        "dim": "\033[2m",
        "bold": "\033[1m",
    }
    return f"{colors[color]}{text}\033[0m"


def status_color(status: str) -> str:
    if status == "configured":
        return "green"
    if status == "not configured":
        return "yellow"
    if status == "not exist":
        return "red"
    return "cyan"


def print_ascii_header(title: str, args: argparse.Namespace) -> None:
    if not getattr(args, "ascii_art", True):
        return
    line = f"| {title} |"
    border = "+" + "-" * (len(line) - 2) + "+"
    print(color_text(border, "cyan", args))
    print(color_text(line, "cyan", args))
    print(color_text(border, "cyan", args))


def config_metadata() -> Dict[str, object]:
    path = current_config_path()
    exists = path.exists()
    return {
        "config": str(path),
        "config_exists": exists,
        "using_implicit_defaults": not exists,
    }


def require_saved_config_for_write(args: argparse.Namespace, command: str) -> None:
    if config_file_exists():
        return
    if getattr(args, "dry_run", False):
        print(f"Warning: no config file found at {current_config_path()}; using implicit defaults for this dry run only.")
        return
    raise SystemExit(
        f"No config file found at {current_config_path()}. "
        f"Run 'agent-skills setup' before 'agent-skills {command}', "
        "or use a dry run first to preview implicit defaults."
    )


# ----- Scan/status -----

def scan_target_status(target: SkillTarget, local: Path) -> str:
    if not local.exists():
        return "not exist"
    return "configured" if target.enabled else "not configured"


def scan_args_limit(args: argparse.Namespace) -> int:
    return max(0, int(getattr(args, "limit", 5)))


def target_matches_filter(target: SkillTarget, local: Path, args: argparse.Namespace) -> bool:
    only = getattr(args, "only", None)
    status = scan_target_status(target, local)
    if only == "configured":
        return status == "configured"
    if only == "not-configured":
        return status == "not configured"
    if only == "missing":
        return status == "not exist"
    if only == "existing":
        return local.exists()
    if getattr(args, "all", False):
        return True
    return target.enabled


def collect_scan_targets(cfg: Config, args: argparse.Namespace) -> List[Dict[str, object]]:
    repo_root = expand(cfg.repo_dir)
    records: List[Dict[str, object]] = []
    example_limit = scan_args_limit(args)
    include_examples = bool(getattr(args, "examples", True))
    for target in cfg.targets or []:
        local = expand(target.local_dir)
        if not target_matches_filter(target, local, args):
            continue
        repo = repo_root / target.repo_dir
        skill_dirs = list(iter_skill_dirs(local))
        examples = [str(p.relative_to(local)) for p in skill_dirs[:example_limit]] if include_examples else []
        status = scan_target_status(target, local)
        records.append({
            "name": target.name,
            "configured": target.enabled,
            "status": status,
            "local": str(local),
            "repo": str(repo),
            "local_skills": count_skills(local),
            "repo_skills": count_skills(repo),
            "examples": examples,
            "has_more_examples": include_examples and len(skill_dirs) > len(examples),
        })
    return records


def print_scan_records(cfg: Config, records: List[Dict[str, object]], args: argparse.Namespace, include_header: bool = True) -> None:
    output_format = getattr(args, "format", "text")
    if output_format == "json":
        payload = config_metadata()
        payload.update({
            "repo": str(expand(cfg.repo_dir)),
            "targets": records,
        })
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    if output_format == "names":
        for record in records:
            print(record["name"])
        return

    if include_header:
        print_ascii_header("Agent Skills Scan", args)
        if current_config_path().exists():
            print(f"{color_text('Config:', 'blue', args)} {current_config_path()}")
        else:
            print(f"{color_text('Config:', 'blue', args)} (not created yet; using implicit defaults)")
            print("Run 'agent-skills setup' to save these defaults before real push/pull/sync operations.")
        print(f"{color_text('Repo:', 'blue', args)}   {expand(cfg.repo_dir)}")
        print()
    for record in records:
        status = str(record["status"])
        print(f"[{color_text(str(record['name']), 'bold', args)}] {color_text(status, status_color(status), args)}")
        if record["status"] == "not exist":
            print()
            continue
        print(f"  {color_text('local:', 'dim', args)} {record['local']}  skills={record['local_skills']}")
        if record["status"] == "configured":
            print(f"  {color_text('repo:', 'dim', args)}  {record['repo']}  skills={record['repo_skills']}")
            for example in record["examples"]:  # type: ignore[index]
                print(f"    - {example}")
            if record["has_more_examples"]:
                print("    ...")
        print()


def cmd_scan(args: argparse.Namespace) -> None:
    cfg = load_config()
    print_scan_records(cfg, collect_scan_targets(cfg, args), args)


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
    if not yes(f"Local branch '{branch}' does not exist. Create it from the current HEAD now", True):
        raise SystemExit(f"Branch not found: {branch}. Create it first or choose an existing default branch.")
    run(["git", "checkout", "-B", branch], cwd=repo)


def enabled_targets(cfg: Config) -> List[SkillTarget]:
    return [target for target in (cfg.targets or []) if target.enabled]


def get_target(cfg: Config, name: str) -> SkillTarget:
    for target in cfg.targets or []:
        if target.name == name:
            return target
    raise SystemExit(f"Unknown target: {name}")


def target_source_destination(cfg: Config, repo: Path, target: SkillTarget, direction: str) -> Tuple[Path, Path]:
    if direction == "push":
        return expand(target.local_dir), repo / target.repo_dir
    if direction == "pull":
        return repo / target.repo_dir, expand(target.local_dir)
    raise ValueError(direction)


def build_target_plan(cfg: Config, repo: Path, target: SkillTarget, direction: str, mirror: bool, state: Optional[Dict[str, object]] = None) -> Dict[str, object]:
    src, dst = target_source_destination(cfg, repo, target, direction)
    patterns = read_ignore_patterns(src, dst, cfg=cfg)
    base_hashes = state_target_hashes(state or load_sync_state(), repo, target)
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
        confirm_destructive(args, f"Mirror mode will delete {delete_count} files. Continue")


def mark_state_after_sync(state: Dict[str, object], repo: Path, target: SkillTarget, cfg: Config) -> None:
    repo_target = repo / target.repo_dir
    patterns = read_ignore_patterns(repo_target, expand(target.local_dir), cfg=cfg)
    update_state_target(state, repo, target, collect_file_hashes(repo_target, patterns))


def cmd_push(args: argparse.Namespace) -> None:
    require_saved_config_for_write(args, "push")
    cfg = load_config()
    repo = ensure_repo(cfg, create=getattr(args, "create_repo", False), clone=True)
    dirty_before = repo_dirty(repo)
    if dirty_before and not getattr(args, "allow_dirty", False):
        if getattr(args, "dry_run", False):
            print("Repo has uncommitted changes; continuing because this is a dry run.")
        else:
            raise SystemExit(f"Repo has uncommitted changes. Inspect first: git -C {repo} status")

    if not getattr(args, "dry_run", False):
        ensure_push_branch(repo, cfg.default_branch)
        maybe_pull(repo, args.no_pull)

    state = load_sync_state()
    plans: List[Dict[str, object]] = []
    total = 0
    for target in enabled_targets(cfg):
        plan = build_target_plan(cfg, repo, target, "push", args.mirror, state=state)
        if fail_or_skip_missing(plan, target, getattr(args, "strict", False)):
            continue
        if plan.get("conflict") and not getattr(args, "force", False):
            print_plan(plan, f"Sync local -> repo [{target.name}]")
            raise SystemExit("Conflicting files detected; inspect with agent-skills diff --direction push or re-run with --force.")
        plans.append(plan)
    maybe_confirm_mirror(args, plans)

    for plan in plans:
        target = get_target(cfg, str(plan["target"]))
        src, dst = target_source_destination(cfg, repo, target, "push")
        print(f"Sync local -> repo [{target.name}]\n  from: {src}\n  to:   {dst}")
        changed, deleted = apply_copy_plan(src, dst, plan, dry_run=args.dry_run)
        print(f"  changed={changed} deleted={deleted}")
        total += changed + deleted
        if not args.dry_run and changed + deleted:
            mark_state_after_sync(state, repo, target, cfg)

    if args.dry_run:
        print("Dry run complete; no commit or push.")
        return
    if total:
        save_sync_state(state)
    if not repo_dirty(repo):
        print("No repo changes to commit or push.")
        return
    run(["git", "add", "."], cwd=repo)
    run(["git", "commit", "-m", args.message], cwd=repo)
    if git_output(["remote", "get-url", "origin"], repo):
        run(["git", "push", "-u", "origin", cfg.default_branch], cwd=repo)
    else:
        print("Committed locally. No origin remote configured, so nothing was pushed.")


def create_backup(cfg: Config, target: SkillTarget, local: Path) -> Path:
    backups_root = expand(cfg.backups_dir)
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


def cmd_pull(args: argparse.Namespace) -> None:
    require_saved_config_for_write(args, "pull")
    cfg = load_config()
    repo = ensure_repo(cfg, clone=True)
    maybe_pull(repo, args.no_pull)
    state = load_sync_state()
    plans: List[Dict[str, object]] = []
    total = 0
    for target in enabled_targets(cfg):
        plan = build_target_plan(cfg, repo, target, "pull", args.mirror, state=state)
        if fail_or_skip_missing(plan, target, getattr(args, "strict", False)):
            continue
        if plan.get("conflict") and not getattr(args, "force", False):
            print_plan(plan, f"Sync repo -> local [{target.name}]")
            raise SystemExit("Conflicting files detected; inspect with agent-skills diff --direction pull or re-run with --force.")
        plans.append(plan)
    maybe_confirm_mirror(args, plans)

    for plan in plans:
        target = get_target(cfg, str(plan["target"]))
        src, dst = target_source_destination(cfg, repo, target, "pull")
        print(f"Sync repo -> local [{target.name}]\n  from: {src}\n  to:   {dst}")
        if not args.dry_run and getattr(args, "backup", True) and plan_write_count(plan) and dst.exists():
            create_backup(cfg, target, dst)
        changed, deleted = apply_copy_plan(src, dst, plan, dry_run=args.dry_run)
        print(f"  changed={changed} deleted={deleted}")
        total += changed + deleted
        if not args.dry_run and changed + deleted:
            mark_state_after_sync(state, repo, target, cfg)
    if not args.dry_run and total:
        save_sync_state(state)
    print("Dry run complete." if args.dry_run else f"Done. File changes: {total}")
    print("Reload/restart your agent sessions so they see updated skills.")


def collect_git_status(repo: Path) -> Dict[str, object]:
    if (repo / ".git").exists():
        return {
            "initialized": True,
            "status": git_output(["status", "--short", "--branch"], repo) or "clean",
            "remote": git_output(["remote", "-v"], repo),
        }
    return {"initialized": False, "status": "Repo is not initialized yet.", "remote": ""}


def cmd_status(args: argparse.Namespace) -> None:
    cfg = load_config()
    repo = expand(cfg.repo_dir)
    output_format = getattr(args, "format", "text")
    include_git = not getattr(args, "no_git", False)
    include_scan = not getattr(args, "no_scan", False)

    if output_format == "json":
        payload: Dict[str, object] = config_metadata()
        payload["repo"] = str(repo)
        if include_git:
            payload["git"] = collect_git_status(repo)
        if include_scan:
            payload["targets"] = collect_scan_targets(cfg, args)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    if output_format == "names":
        print_scan_records(cfg, collect_scan_targets(cfg, args), args, include_header=False)
        return

    if include_git:
        print_ascii_header("Agent Skills Status", args)
        if current_config_path().exists():
            print(f"{color_text('Config:', 'blue', args)} {current_config_path()}")
        else:
            print(f"{color_text('Config:', 'blue', args)} (not created yet; using implicit defaults)")
            print("Run 'agent-skills setup' to save these defaults before real push/pull/sync operations.")
        print(f"{color_text('Repo:', 'blue', args)} {repo}")
        git_status = collect_git_status(repo)
        if git_status["initialized"]:
            print(git_status["status"])
            if git_status["remote"]:
                print(git_status["remote"])
        else:
            print(git_status["status"])
        if include_scan:
            print()
    if include_scan:
        print_scan_records(cfg, collect_scan_targets(cfg, args), args, include_header=not include_git)


def cmd_init_repo(args: argparse.Namespace) -> None:
    cfg = load_config()
    if args.repo:
        cfg.repo_dir = args.repo
    if args.remote is not None:
        cfg.remote_url = args.remote
    save_config(cfg)
    repo = ensure_repo(cfg, create=True)
    for target in cfg.targets or []:
        if target.enabled:
            (repo / target.repo_dir).mkdir(parents=True, exist_ok=True)
    readme = repo / "README.md"
    if not readme.exists():
        readme.write_text("# Private agent skills\n\nManaged by agent-skills-manager.\n", encoding="utf-8")
    gitignore = repo / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(".DS_Store\n__pycache__/\n*.pyc\n.env\n", encoding="utf-8")
    ignore = repo / ".agent-skills-ignore"
    if not ignore.exists():
        ignore.write_text("\n".join(DEFAULT_EXCLUDES) + "\n", encoding="utf-8")
    print(f"Repo initialized: {repo}")


# ----- Diff/plan/sync -----

def serializable_plan(plan: Dict[str, object]) -> Dict[str, object]:
    return {key: value for key, value in plan.items() if key != "unchanged"}


def cmd_diff(args: argparse.Namespace) -> None:
    cfg = load_config()
    repo = expand(cfg.repo_dir)
    state = load_sync_state()
    plans = [build_target_plan(cfg, repo, target, args.direction, args.mirror, state=state) for target in enabled_targets(cfg)]
    if getattr(args, "format", "text") == "json":
        print(json.dumps({"repo": str(repo), "direction": args.direction, "mirror": args.mirror, "plans": [serializable_plan(p) for p in plans]}, indent=2, ensure_ascii=False))
        return
    print_ascii_header("Agent Skills Diff", args)
    for plan in plans:
        print_plan(plan, f"[{plan['target']}] {args.direction}: {plan['source']} -> {plan['destination']}")


def cmd_plan(args: argparse.Namespace) -> None:
    args.direction = args.direction or args.plan_direction
    cmd_diff(args)


def cmd_sync(args: argparse.Namespace) -> None:
    """Two-way safe sync: pull repo changes, then push local changes."""
    require_saved_config_for_write(args, "sync")
    pull_args = argparse.Namespace(**vars(args))
    pull_args.no_pull = getattr(args, "no_pull", False)
    pull_args.backup = not getattr(args, "no_backup", False)
    push_args = argparse.Namespace(**vars(args))
    push_args.no_pull = True
    push_args.message = getattr(args, "message", "Sync local agent skills")
    print("Sync step 1/2: repo -> local")
    cmd_pull(pull_args)
    print("\nSync step 2/2: local -> repo")
    cmd_push(push_args)


# ----- Doctor/validate -----

def cmd_doctor(args: argparse.Namespace) -> None:
    cfg = load_config()
    repo = expand(cfg.repo_dir)
    checks: List[Dict[str, str]] = []

    def add(level: str, message: str) -> None:
        checks.append({"level": level, "message": message})

    if git_available():
        add("ok", "git is available")
    else:
        add("error", "git is not installed or not in PATH")
    if current_config_path().exists():
        add("ok", f"config exists: {current_config_path()}")
    else:
        add("warn", f"config has not been created yet: {current_config_path()}")
        add("warn", "using implicit defaults; run 'agent-skills setup' before real push/pull/sync operations")
    reasons = dangerous_repo_reasons(repo, cfg)
    if reasons:
        for reason in reasons:
            add("error", reason)
    else:
        add("ok", f"repo path looks safe: {repo}")
    if (repo / ".git").exists():
        add("ok", "repo is initialized")
        if repo_dirty(repo):
            add("warn", "repo has uncommitted changes")
        remote = git_output(["remote", "get-url", "origin"], repo)
        add("ok" if remote else "warn", f"origin remote: {remote or '(not configured)'}")
    else:
        add("warn", "repo is not initialized yet")
    for target in cfg.targets or []:
        local = expand(target.local_dir)
        if target.enabled and local.exists():
            add("ok", f"target {target.name}: configured, local exists, skills={count_skills(local)}")
        elif target.enabled:
            add("error", f"target {target.name}: configured local directory does not exist: {local}")
        elif local.exists():
            add("warn", f"target {target.name}: local exists but is not configured")
    if getattr(args, "format", "text") == "json":
        payload = config_metadata()
        payload.update({"repo": str(repo), "checks": checks})
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print_ascii_header("Agent Skills Doctor", args)
        for check in checks:
            print(f"{check['level'].upper()}: {check['message']}")
    if any(check["level"] == "error" for check in checks):
        raise SystemExit(1)


FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
SECRET_RE = re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+\-=]{20,}")


def parse_frontmatter(text: str) -> Dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    data: Dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip().strip('"\'')
    return data


def validate_skill_dir(skill_dir: Path) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        return [f"{skill_dir}: missing SKILL.md"], warnings
    text = skill_file.read_text(encoding="utf-8", errors="ignore")
    if not text.strip():
        errors.append(f"{skill_file}: empty SKILL.md")
    meta = parse_frontmatter(text)
    if not meta:
        errors.append(f"{skill_file}: missing frontmatter")
    else:
        for required in ["name", "description"]:
            if not meta.get(required):
                errors.append(f"{skill_file}: missing frontmatter field '{required}'")
    for path in skill_dir.rglob("*"):
        if path.is_file() and path.stat().st_size <= 1024 * 1024:
            content = path.read_text(encoding="utf-8", errors="ignore")
            if "-----BEGIN PRIVATE KEY-----" in content or SECRET_RE.search(content):
                warnings.append(f"{path}: possible secret detected")
    return errors, warnings


def validation_roots(cfg: Config, location: str, target_name: Optional[str]) -> List[Tuple[SkillTarget, Path]]:
    repo = expand(cfg.repo_dir)
    selected = [get_target(cfg, target_name)] if target_name else enabled_targets(cfg)
    roots: List[Tuple[SkillTarget, Path]] = []
    for target in selected:
        roots.append((target, repo / target.repo_dir if location == "repo" else expand(target.local_dir)))
    return roots


def cmd_validate(args: argparse.Namespace) -> None:
    cfg = load_config()
    errors: List[str] = []
    warnings: List[str] = []
    seen_names: Dict[str, Path] = {}
    for target, root in validation_roots(cfg, args.location, args.target):
        if not root.exists():
            errors.append(f"[{target.name}] missing root: {root}")
            continue
        for skill_dir in iter_skill_dirs(root):
            meta = parse_frontmatter((skill_dir / "SKILL.md").read_text(encoding="utf-8", errors="ignore")) if (skill_dir / "SKILL.md").exists() else {}
            name = meta.get("name") or skill_dir.name
            if name in seen_names:
                errors.append(f"duplicate skill name '{name}': {seen_names[name]} and {skill_dir}")
            else:
                seen_names[name] = skill_dir
            skill_errors, skill_warnings = validate_skill_dir(skill_dir)
            errors.extend(skill_errors)
            warnings.extend(skill_warnings)
    if getattr(args, "format", "text") == "json":
        print(json.dumps({"ok": not errors, "errors": errors, "warnings": warnings}, indent=2, ensure_ascii=False))
    else:
        if errors:
            print("Validation failed:")
            for error in errors:
                print(f"  - {error}")
        else:
            print("Validation OK.")
        if warnings:
            print("Warnings:")
            for warning in warnings:
                print(f"  - {warning}")
    if errors:
        raise SystemExit(1)


# ----- Config/target/profile -----

def cmd_config_show(args: argparse.Namespace) -> None:
    cfg = load_config()
    payload = config_metadata()
    payload["settings"] = asdict(cfg)
    if getattr(args, "format", "text") == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        status = "exists" if payload["config_exists"] else "not created yet; using implicit defaults"
        print(f"Config: {current_config_path()} ({status})")
        if payload["using_implicit_defaults"]:
            print("Run 'agent-skills setup' to save a config before real push/pull/sync operations.")
        print(json.dumps(asdict(cfg), indent=2, ensure_ascii=False))


def cmd_config_path(args: argparse.Namespace) -> None:
    del args
    print(current_config_path())


def parse_config_value(key: str, value: str):
    if key == "excludes":
        stripped = value.strip()
        if stripped.startswith("["):
            parsed = json.loads(stripped)
            if not isinstance(parsed, list):
                raise SystemExit("excludes must be a list or comma-separated string")
            return [str(item) for item in parsed]
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


def cmd_config_set(args: argparse.Namespace) -> None:
    cfg = load_config()
    if args.key not in {"repo_dir", "remote_url", "default_branch", "backups_dir", "excludes"}:
        raise SystemExit(f"Unsupported config key: {args.key}")
    setattr(cfg, args.key, parse_config_value(args.key, args.value))
    save_config(cfg)
    print(f"Set {args.key} in {current_config_path()}")


def cmd_target_list(args: argparse.Namespace) -> None:
    cfg = load_config()
    records = [asdict(target) for target in cfg.targets or []]
    if getattr(args, "format", "text") == "json":
        print(json.dumps(records, indent=2, ensure_ascii=False))
        return
    for target in cfg.targets or []:
        status = "configured" if target.enabled else "not configured"
        print(f"{target.name}\t{status}\t{target.local_dir}\t{target.repo_dir}")


def cmd_target_add(args: argparse.Namespace) -> None:
    cfg = load_config()
    targets = list(cfg.targets or [])
    updated = False
    for target in targets:
        if target.name == args.name:
            target.local_dir = args.local
            target.repo_dir = args.repo
            target.enabled = not getattr(args, "disabled", False)
            updated = True
            break
    if not updated:
        targets.insert(0, SkillTarget(args.name, args.local, args.repo, not getattr(args, "disabled", False)))
    cfg.targets = targets
    save_config(cfg)
    print(("Updated" if updated else "Added") + f" target: {args.name}")


def set_target_enabled(name: str, enabled: bool) -> None:
    cfg = load_config()
    target = get_target(cfg, name)
    target.enabled = enabled
    save_config(cfg)
    print(f"{'Enabled' if enabled else 'Disabled'} target: {name}")


def cmd_target_enable(args: argparse.Namespace) -> None:
    set_target_enabled(args.name, True)


def cmd_target_disable(args: argparse.Namespace) -> None:
    set_target_enabled(args.name, False)


def cmd_target_remove(args: argparse.Namespace) -> None:
    cfg = load_config()
    before = len(cfg.targets or [])
    cfg.targets = [target for target in (cfg.targets or []) if target.name != args.name]
    if len(cfg.targets) == before:
        raise SystemExit(f"Unknown target: {args.name}")
    save_config(cfg)
    print(f"Removed target: {args.name}")


def cmd_profile_list(args: argparse.Namespace) -> None:
    del args
    print("default")
    if profile_dir().exists():
        for path in sorted(profile_dir().glob("*.json")):
            print(path.stem)


def cmd_profile_create(args: argparse.Namespace) -> None:
    cfg = load_config()
    save_config(cfg, profile=args.name)
    print(f"Created profile {args.name}: {config_path_for_profile(args.name)}")


def cmd_profile_use(args: argparse.Namespace) -> None:
    source = config_path_for_profile(args.name)
    if not source.exists():
        raise SystemExit(f"Profile not found: {args.name}")
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, CONFIG_PATH)
    print(f"Activated profile {args.name}: {CONFIG_PATH}")


# ----- Browse/show/new/import/export -----

def slugify(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip().lower()).strip("-._")
    return slug or "skill"


def skill_records(cfg: Config, location: str = "local", target_name: Optional[str] = None) -> List[Dict[str, str]]:
    repo = expand(cfg.repo_dir)
    selected = [get_target(cfg, target_name)] if target_name else enabled_targets(cfg)
    records: List[Dict[str, str]] = []
    for target in selected:
        root = repo / target.repo_dir if location == "repo" else expand(target.local_dir)
        if not root.exists():
            continue
        for skill_dir in iter_skill_dirs(root):
            rel = skill_dir.relative_to(root).as_posix()
            records.append({"target": target.name, "name": rel, "path": str(skill_dir), "skill_file": str(skill_dir / "SKILL.md"), "location": location})
    return sorted(records, key=lambda item: (item["target"], item["name"]))


def cmd_list(args: argparse.Namespace) -> None:
    cfg = load_config()
    records = skill_records(cfg, args.location, args.target)
    if getattr(args, "format", "text") == "json":
        print(json.dumps(records, indent=2, ensure_ascii=False))
    elif getattr(args, "format", "text") == "names":
        for record in records:
            print(f"{record['target']}:{record['name']}")
    else:
        for record in records:
            print(f"{record['target']}:{record['name']}\t{record['path']}")


def cmd_search(args: argparse.Namespace) -> None:
    cfg = load_config()
    query = args.query.lower()
    matches: List[Dict[str, str]] = []
    for record in skill_records(cfg, args.location, args.target):
        text = Path(record["skill_file"]).read_text(encoding="utf-8", errors="ignore")
        if query in record["name"].lower() or query in text.lower():
            matches.append(record)
    if getattr(args, "format", "text") == "json":
        print(json.dumps(matches, indent=2, ensure_ascii=False))
    elif getattr(args, "format", "text") == "names":
        for record in matches:
            print(f"{record['target']}:{record['name']}")
    else:
        for record in matches:
            print(f"{record['target']}:{record['name']}\t{record['path']}")


def resolve_skill_spec(cfg: Config, spec: str, repo: bool = False) -> Dict[str, str]:
    location = "repo" if repo else "local"
    if ":" in spec:
        target_name, skill_name = spec.split(":", 1)
        records = [record for record in skill_records(cfg, location, target_name) if record["name"] == skill_name]
    else:
        records = [record for record in skill_records(cfg, location, None) if record["name"] == spec or record["name"].endswith("/" + spec)]
    if not records:
        raise SystemExit(f"Skill not found: {spec}")
    if len(records) > 1:
        raise SystemExit("Skill name is ambiguous; use target:skill. Matches: " + ", ".join(f"{r['target']}:{r['name']}" for r in records))
    return records[0]


def cmd_show(args: argparse.Namespace) -> None:
    cfg = load_config()
    record = resolve_skill_spec(cfg, args.spec, repo=getattr(args, "repo", False))
    print(Path(record["skill_file"]).read_text(encoding="utf-8"), end="")


def cmd_open(args: argparse.Namespace) -> None:
    cfg = load_config()
    record = resolve_skill_spec(cfg, args.spec, repo=getattr(args, "repo", False))
    path = Path(record["path"])
    if getattr(args, "print_only", False):
        print(path)
        return
    opener = None
    if platform.system() == "Darwin":
        opener = "open"
    elif platform.system() == "Windows":  # pragma: no cover - platform-specific
        os.startfile(str(path))  # type: ignore[attr-defined]
        print(path)
        return
    else:
        opener = shutil.which("xdg-open")
    if opener:
        subprocess.Popen([opener, str(path)])
    print(path)


def skill_template(slug: str, title: str) -> str:
    description = f"Describe when to use {title}."
    return f"---\nname: {slug}\ndescription: \"{description}\"\nversion: 1.0.0\n---\n\n# {title}\n\n## When to Use\n\n- TODO\n\n## Steps\n\n1. TODO\n\n## Verification\n\n- TODO\n"


def cmd_new(args: argparse.Namespace) -> None:
    cfg = load_config()
    target = get_target(cfg, args.target)
    root = (expand(cfg.repo_dir) / target.repo_dir) if getattr(args, "repo", False) else expand(target.local_dir)
    slug = slugify(args.name)
    skill_dir = root / slug
    if skill_dir.exists() and not getattr(args, "force", False):
        raise SystemExit(f"Skill already exists: {skill_dir}")
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    if skill_file.exists() and not getattr(args, "force", False):
        raise SystemExit(f"SKILL.md already exists: {skill_file}")
    skill_file.write_text(skill_template(slug, args.name), encoding="utf-8")
    (skill_dir / "references").mkdir(exist_ok=True)
    (skill_dir / "scripts").mkdir(exist_ok=True)
    (skill_dir / "templates").mkdir(exist_ok=True)
    print(f"Created skill: {skill_dir}")


def zip_dir(root: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in root.rglob("*"):
            if item.is_file():
                zf.write(item, item.relative_to(root).as_posix())


def cmd_export(args: argparse.Namespace) -> None:
    cfg = load_config()
    target = get_target(cfg, args.target)
    root = (expand(cfg.repo_dir) / target.repo_dir) if getattr(args, "repo", False) else expand(target.local_dir)
    if not root.exists():
        raise SystemExit(f"Target root does not exist: {root}")
    output = Path(args.output) if args.output else Path(f"{target.name}-skills.zip")
    zip_dir(root, output)
    print(f"Exported {target.name} skills to {output}")


def extract_import_source(path: Path) -> Tuple[tempfile.TemporaryDirectory, Path]:
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            zf.extractall(root)
        return temp, root
    temp.cleanup()
    return tempfile.TemporaryDirectory(), path


def cmd_import(args: argparse.Namespace) -> None:
    cfg = load_config()
    target = get_target(cfg, args.target)
    dst = (expand(cfg.repo_dir) / target.repo_dir) if getattr(args, "repo", False) else expand(target.local_dir)
    source_arg = Path(args.path).expanduser().resolve()
    if not source_arg.exists():
        raise SystemExit(f"Import source not found: {source_arg}")
    temp, src = extract_import_source(source_arg)
    try:
        patterns = read_ignore_patterns(src, dst, cfg=cfg)
        plan = build_copy_plan(src, dst, mirror=getattr(args, "mirror", False), patterns=patterns)
        if plan.get("conflict") and not getattr(args, "force", False):
            print_plan(plan, f"Import -> {target.name}")
            raise SystemExit("Conflicting files detected; re-run with --force after reviewing.")
        maybe_confirm_mirror(args, [plan])
        changed, deleted = apply_copy_plan(src, dst, plan, dry_run=getattr(args, "dry_run", False))
        print(f"Imported into {dst}; changed={changed} deleted={deleted}")
    finally:
        temp.cleanup()


# ----- Backups -----

def cmd_backups_list(args: argparse.Namespace) -> None:
    cfg = load_config()
    root = expand(cfg.backups_dir)
    if not root.exists():
        return
    for path in sorted(root.glob("*")):
        if path.is_dir():
            print(path)


def cmd_restore_backup(args: argparse.Namespace) -> None:
    cfg = load_config()
    target = get_target(cfg, args.target)
    src = Path(args.path).expanduser().resolve()
    if not src.exists():
        raise SystemExit(f"Backup path not found: {src}")
    dst = expand(target.local_dir)
    patterns = read_ignore_patterns(src, dst, cfg=cfg)
    plan = build_copy_plan(src, dst, mirror=getattr(args, "mirror", True), patterns=patterns)
    maybe_confirm_mirror(args, [plan])
    changed, deleted = apply_copy_plan(src, dst, plan, dry_run=getattr(args, "dry_run", False))
    print(f"Restored backup to {dst}; changed={changed} deleted={deleted}")


# ----- GUI/install -----

def cmd_gui(args: argparse.Namespace) -> None:
    del args
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"Tkinter GUI is not available on this system: {exc}")

    cfg = load_config()
    try:
        root = tk.Tk()
    except Exception as exc:
        raise SystemExit(
            "GUI is not available in this environment: "
            f"{exc}\n\n"
            "The GUI is experimental and optional. Use the CLI commands instead:\n"
            "  agent-skills setup\n"
            "  agent-skills scan\n"
            "  agent-skills status\n"
            "  agent-skills push --dry-run"
        )
    root.title("Agent Skills Manager")
    root.geometry("760x520")

    repo_var = tk.StringVar(value=cfg.repo_dir)
    remote_var = tk.StringVar(value=cfg.remote_url)
    branch_var = tk.StringVar(value=cfg.default_branch)
    target_vars: Dict[str, Dict[str, tk.Variable]] = {}

    def browse_repo() -> None:
        path = filedialog.askdirectory(initialdir=str(expand(repo_var.get()).parent))
        if path:
            repo_var.set(path)

    def collect() -> Config:
        targets: List[SkillTarget] = []
        for name, vs in target_vars.items():
            targets.append(SkillTarget(name, str(vs["local"].get()), str(vs["repo"].get()), bool(vs["enabled"].get())))
        return Config(repo_var.get(), remote_var.get(), branch_var.get(), targets, cfg.backups_dir, cfg.excludes)

    def save() -> None:
        save_config(collect())
        messagebox.showinfo("Saved", f"Saved config:\n{current_config_path()}")

    def run_action(action: str) -> None:
        save_config(collect())
        cmd = [sys.executable, "-m", "agent_skills_manager.cli", action]
        if action == "push":
            cmd += ["-m", "Sync local agent skills"]
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        output.delete("1.0", tk.END)
        output.insert(tk.END, proc.stdout)
        if proc.returncode != 0:
            messagebox.showerror(action, f"Command failed with exit code {proc.returncode}")

    row = 0
    tk.Label(root, text="Local skills repo").grid(row=row, column=0, sticky="w", padx=8, pady=6)
    tk.Entry(root, textvariable=repo_var, width=68).grid(row=row, column=1, sticky="we", padx=8)
    tk.Button(root, text="Browse", command=browse_repo).grid(row=row, column=2, padx=8)
    row += 1
    tk.Label(root, text="Remote URL").grid(row=row, column=0, sticky="w", padx=8, pady=6)
    tk.Entry(root, textvariable=remote_var, width=68).grid(row=row, column=1, columnspan=2, sticky="we", padx=8)
    row += 1
    tk.Label(root, text="Branch").grid(row=row, column=0, sticky="w", padx=8, pady=6)
    tk.Entry(root, textvariable=branch_var, width=20).grid(row=row, column=1, sticky="w", padx=8)
    row += 1

    for target in cfg.targets or []:
        enabled = tk.BooleanVar(value=target.enabled)
        local = tk.StringVar(value=target.local_dir)
        repo_d = tk.StringVar(value=target.repo_dir)
        target_vars[target.name] = {"enabled": enabled, "local": local, "repo": repo_d}
        tk.Checkbutton(root, text=f"Enable {target.name}", variable=enabled).grid(row=row, column=0, sticky="w", padx=8, pady=6)
        tk.Entry(root, textvariable=local, width=45).grid(row=row, column=1, sticky="we", padx=8)
        tk.Entry(root, textvariable=repo_d, width=22).grid(row=row, column=2, sticky="we", padx=8)
        row += 1

    buttons = tk.Frame(root)
    buttons.grid(row=row, column=0, columnspan=3, sticky="w", padx=8, pady=8)
    tk.Button(buttons, text="Save", command=save).pack(side=tk.LEFT, padx=4)
    tk.Button(buttons, text="Scan", command=lambda: run_action("scan")).pack(side=tk.LEFT, padx=4)
    tk.Button(buttons, text="Pull", command=lambda: run_action("pull")).pack(side=tk.LEFT, padx=4)
    tk.Button(buttons, text="Push", command=lambda: run_action("push")).pack(side=tk.LEFT, padx=4)
    row += 1
    output = tk.Text(root, height=18)
    output.grid(row=row, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)
    root.grid_columnconfigure(1, weight=1)
    root.grid_rowconfigure(row, weight=1)
    output.insert(tk.END, "Use Save, Scan, Pull, or Push. The GUI is experimental; CLI has the full feature set.\n")
    root.mainloop()


def cmd_install_shell(args: argparse.Namespace) -> None:
    if platform.system() == "Windows":
        raise SystemExit(
            "install-shell creates POSIX shell wrappers and is not supported on Windows. "
            "Use: py -m pip install -e ."
        )
    bindir = expand(args.bindir)
    bindir.mkdir(parents=True, exist_ok=True)
    project_root = Path(__file__).resolve().parent.parent
    wrapper = bindir / "agent-skills"
    wrapper.write_text(
        "#!/usr/bin/env sh\n"
        "set -eu\n"
        f"export PYTHONPATH={project_root}:${{PYTHONPATH:-}}\n"
        f"exec {sys.executable} -m agent_skills_manager.cli \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    alias = bindir / "askills"
    if not alias.exists():
        try:
            alias.symlink_to(wrapper)
        except OSError:
            shutil.copy2(wrapper, alias)
    print(f"Installed wrappers:\n  {wrapper}\n  {alias}")
    print(f"Make sure {bindir} is in PATH. Prefer pip/venv entry points when available.")


# ----- Parser -----

def add_output_filter_args(parser: argparse.ArgumentParser, include_status_flags: bool = False) -> None:
    parser.add_argument("--all", action="store_true", help="include not configured and missing targets")
    parser.add_argument(
        "--only",
        choices=["configured", "not-configured", "missing", "existing"],
        help="show only targets with this status; default shows configured targets only",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "names"],
        default="text",
        help="output format; names prints only target names for scripts",
    )
    parser.add_argument("--no-examples", dest="examples", action="store_false", help="hide example skill names")
    parser.add_argument("--limit", type=int, default=5, help="maximum skill examples per target in text output")
    parser.add_argument(
        "--color",
        choices=["auto", "always", "never"],
        default="auto",
        help="colorize text output: auto for terminals, always to force ANSI, never to disable",
    )
    parser.add_argument("--no-ascii", dest="ascii_art", action="store_false", help="hide decorative ASCII headers")
    parser.set_defaults(examples=True, ascii_art=True)
    if include_status_flags:
        parser.add_argument("--no-git", action="store_true", help="hide git status/remotes and show only skill target output")
        parser.add_argument("--no-scan", action="store_true", help="hide skill target output and show only git status/remotes")


def add_sync_flags(parser: argparse.ArgumentParser, include_message: bool = False) -> None:
    parser.add_argument("--dry-run", action="store_true", help="preview file copies, commit, and push without writing files or modifying git state")
    parser.add_argument("--mirror", action="store_true", help="delete destination files that are not in source")
    parser.add_argument("--force", action="store_true", help="allow overwriting files reported as conflicts")
    parser.add_argument("--strict", action="store_true", help="fail instead of skipping missing source target directories")
    parser.add_argument("--yes", action="store_true", help="skip destructive confirmation prompts")
    if include_message:
        parser.add_argument("-m", "--message", default="Sync local agent skills")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent-skills",
        description="Scan installed AI agent skills and sync them with a private Git repository.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Typical workflow:
          agent-skills setup                    # hand-holding wizard
          agent-skills doctor                   # diagnose config/repo safety
          agent-skills diff --direction push    # preview changes
          agent-skills push --dry-run           # safe local -> repo preview
          agent-skills push                     # local skills -> repo -> git push
          agent-skills pull                     # git pull -> repo skills -> local
          agent-skills validate                 # validate skill files
        """),
    )
    p.add_argument("--profile", help="use a named config profile for this invocation")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup", help="interactive setup wizard").set_defaults(func=cmd_setup)

    scan = sub.add_parser("scan", help="scan configured skills by default; use filters to include disabled/missing targets")
    add_output_filter_args(scan)
    scan.set_defaults(func=cmd_scan)

    status = sub.add_parser("status", help="show git status and configured skill counts")
    add_output_filter_args(status, include_status_flags=True)
    status.set_defaults(func=cmd_status)

    diff = sub.add_parser("diff", help="preview file changes without copying anything")
    diff.add_argument("--direction", choices=["push", "pull"], default="push")
    diff.add_argument("--mirror", action="store_true")
    diff.add_argument("--format", choices=["text", "json"], default="text")
    diff.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    diff.add_argument("--no-ascii", dest="ascii_art", action="store_false")
    diff.set_defaults(func=cmd_diff, ascii_art=True)

    plan = sub.add_parser("plan", help="alias for diff; usage: agent-skills plan push|pull")
    plan.add_argument("plan_direction", choices=["push", "pull"])
    plan.add_argument("--direction", choices=["push", "pull"], default=None, help=argparse.SUPPRESS)
    plan.add_argument("--mirror", action="store_true")
    plan.add_argument("--format", choices=["text", "json"], default="text")
    plan.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    plan.add_argument("--no-ascii", dest="ascii_art", action="store_false")
    plan.set_defaults(func=cmd_plan, ascii_art=True)

    pull = sub.add_parser(
        "pull",
        help="sync repo skills into local installed skill dirs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          agent-skills pull --dry-run          # preview repo skills -> local installed skill directories
          agent-skills pull                   # apply repo skills -> local installed skill directories with backups
          agent-skills pull --mirror --yes    # make local match repo; may delete local-only files
        """),
    )
    add_sync_flags(pull)
    pull.add_argument("--no-pull", action="store_true", help="skip git pull --ff-only")
    pull.add_argument("--no-backup", dest="backup", action="store_false", help="do not back up local skill directories before writing")
    pull.set_defaults(func=cmd_pull, backup=True)

    push = sub.add_parser(
        "push",
        help="sync local installed skills into repo, commit, and push",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          agent-skills push --dry-run              # preview local -> repo without writing
          agent-skills push -m "Sync my skills"    # copy, commit, and push local skills
          agent-skills push --mirror --yes         # make repo match local; may delete repo-only files
        """),
    )
    add_sync_flags(push, include_message=True)
    push.add_argument("--no-pull", action="store_true", help="skip git pull --ff-only")
    push.add_argument("--allow-dirty", action="store_true", help="allow starting while repo already has uncommitted changes")
    push.add_argument("--create-repo", action="store_true", help="create repo if missing")
    push.set_defaults(func=cmd_push)

    sync = sub.add_parser(
        "sync",
        help="safe two-step sync: pull then push",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          agent-skills sync --dry-run          # preview the safe two-step flow
          agent-skills sync                   # pull repo -> local, then push local -> repo
          agent-skills sync -m "Sync skills"  # use a custom commit message for the push phase
        """),
    )
    add_sync_flags(sync, include_message=True)
    sync.add_argument("--no-pull", action="store_true", help="skip git pull --ff-only before pull phase")
    sync.add_argument("--no-backup", action="store_true", help="do not back up local skill directories before pull phase")
    sync.add_argument("--allow-dirty", action="store_true")
    sync.add_argument("--create-repo", action="store_true")
    sync.set_defaults(func=cmd_sync)

    init_repo = sub.add_parser("init-repo", help="create the local private skills repo skeleton")
    init_repo.add_argument("--repo")
    init_repo.add_argument("--remote", default=None)
    init_repo.set_defaults(func=cmd_init_repo)

    doctor = sub.add_parser("doctor", help="diagnose config, git, path, and target safety")
    doctor.add_argument("--format", choices=["text", "json"], default="text")
    doctor.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    doctor.add_argument("--no-ascii", dest="ascii_art", action="store_false")
    doctor.set_defaults(func=cmd_doctor, ascii_art=True)

    validate = sub.add_parser("validate", help="validate skill structure, metadata, duplicates, and possible secrets")
    validate.add_argument("--location", choices=["local", "repo"], default="local")
    validate.add_argument("--target")
    validate.add_argument("--format", choices=["text", "json"], default="text")
    validate.set_defaults(func=cmd_validate)

    config = sub.add_parser("config", help="scriptable configuration management")
    config_sub = config.add_subparsers(dest="config_cmd", required=True)
    config_show = config_sub.add_parser("show")
    config_show.add_argument("--format", choices=["text", "json"], default="text")
    config_show.set_defaults(func=cmd_config_show)
    config_sub.add_parser("path").set_defaults(func=cmd_config_path)
    config_set = config_sub.add_parser("set")
    config_set.add_argument("key")
    config_set.add_argument("value")
    config_set.set_defaults(func=cmd_config_set)

    target = sub.add_parser("target", help="scriptable skill target management")
    target_sub = target.add_subparsers(dest="target_cmd", required=True)
    target_list = target_sub.add_parser("list")
    target_list.add_argument("--format", choices=["text", "json"], default="text")
    target_list.set_defaults(func=cmd_target_list)
    target_add = target_sub.add_parser("add")
    target_add.add_argument("name")
    target_add.add_argument("--local", required=True)
    target_add.add_argument("--repo", required=True)
    target_add.add_argument("--disabled", action="store_true")
    target_add.set_defaults(func=cmd_target_add)
    for name, func in [("enable", cmd_target_enable), ("disable", cmd_target_disable), ("remove", cmd_target_remove)]:
        sp = target_sub.add_parser(name)
        sp.add_argument("name")
        sp.set_defaults(func=func)

    profile = sub.add_parser("profile", help="manage named config profiles")
    profile_sub = profile.add_subparsers(dest="profile_cmd", required=True)
    profile_sub.add_parser("list").set_defaults(func=cmd_profile_list)
    profile_create = profile_sub.add_parser("create")
    profile_create.add_argument("name")
    profile_create.set_defaults(func=cmd_profile_create)
    profile_use = profile_sub.add_parser("use")
    profile_use.add_argument("name")
    profile_use.set_defaults(func=cmd_profile_use)

    list_cmd = sub.add_parser("list", help="list skills")
    list_cmd.add_argument("--location", choices=["local", "repo"], default="local")
    list_cmd.add_argument("--target")
    list_cmd.add_argument("--format", choices=["text", "json", "names"], default="text")
    list_cmd.set_defaults(func=cmd_list)

    search = sub.add_parser("search", help="search skill names and SKILL.md contents")
    search.add_argument("query")
    search.add_argument("--location", choices=["local", "repo"], default="local")
    search.add_argument("--target")
    search.add_argument("--format", choices=["text", "json", "names"], default="text")
    search.set_defaults(func=cmd_search)

    show = sub.add_parser("show", help="print one skill's SKILL.md")
    show.add_argument("spec", help="skill name or target:skill")
    show.add_argument("--repo", action="store_true", help="read from repository copy instead of local target")
    show.set_defaults(func=cmd_show)

    open_cmd = sub.add_parser("open", help="open or print one skill directory")
    open_cmd.add_argument("spec", help="skill name or target:skill")
    open_cmd.add_argument("--repo", action="store_true")
    open_cmd.add_argument("--print", dest="print_only", action="store_true", help="print path without launching a desktop opener")
    open_cmd.set_defaults(func=cmd_open)

    new = sub.add_parser(
        "new",
        help="create a new skill skeleton",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          agent-skills new "Docker Management" --target claude
          agent-skills new "Work Skill" --target my-agent --repo
        """),
    )
    new.add_argument("name", help="human-readable skill name; converted to a lowercase directory slug")
    new.add_argument("--target", required=True, help="configured target name such as claude, hermes, or a custom target")
    new.add_argument("--repo", action="store_true", help="create the skill under the repository target instead of the installed local agent target")
    new.add_argument("--force", action="store_true", help="overwrite an existing skill directory if it already exists")
    new.set_defaults(func=cmd_new)

    export = sub.add_parser("export", help="export a target's skills as a zip archive")
    export.add_argument("--target", required=True)
    export.add_argument("--output")
    export.add_argument("--repo", action="store_true")
    export.set_defaults(func=cmd_export)

    import_cmd = sub.add_parser("import", help="import a directory or zip into a target")
    import_cmd.add_argument("path")
    import_cmd.add_argument("--target", required=True)
    import_cmd.add_argument("--repo", action="store_true")
    add_sync_flags(import_cmd)
    import_cmd.set_defaults(func=cmd_import)

    backups = sub.add_parser("backups", help="list backups")
    backups_sub = backups.add_subparsers(dest="backups_cmd", required=True)
    backups_sub.add_parser("list").set_defaults(func=cmd_backups_list)

    restore = sub.add_parser("restore-backup", help="restore a backup directory into a local target")
    restore.add_argument("path")
    restore.add_argument("--target", required=True)
    restore.add_argument("--dry-run", action="store_true")
    restore.add_argument("--mirror", action="store_true", default=True)
    restore.add_argument("--yes", action="store_true")
    restore.set_defaults(func=cmd_restore_backup)

    sub.add_parser("gui", help="open experimental graphical settings and sync window").set_defaults(func=cmd_gui)
    install = sub.add_parser("install-shell", help="install POSIX shell wrapper commands into ~/bin (fallback for source checkouts)")
    install.add_argument("--bindir", default="~/bin")
    install.set_defaults(func=cmd_install_shell)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    global ACTIVE_PROFILE
    previous_profile = ACTIVE_PROFILE
    try:
        args = build_parser().parse_args(argv)
        ACTIVE_PROFILE = getattr(args, "profile", None)
        args.func(args)
        return 0
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except EOFError:
        print("\nNo input received; cancelled.", file=sys.stderr)
        return 130
    finally:
        ACTIVE_PROFILE = previous_profile


if __name__ == "__main__":
    sys.exit(main())
