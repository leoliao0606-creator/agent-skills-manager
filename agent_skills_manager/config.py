"""Configuration, profiles, sync-state, and skill-target model.

This module owns the persisted settings (``Config``/``SkillTarget``), where they
live on disk, and the per-profile sync state. It depends only on the standard
library so it can be imported without pulling in git or filesystem helpers.
"""
from __future__ import annotations

import json
import os
import platform
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional

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


def slugify(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip().lower()).strip("-._")
    return slug or "skill"


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


def enabled_targets(cfg: Config) -> List[SkillTarget]:
    return [target for target in (cfg.targets or []) if target.enabled]


def get_target(cfg: Config, name: str) -> SkillTarget:
    for target in cfg.targets or []:
        if target.name == name:
            return target
    raise SystemExit(f"Unknown target: {name}")
