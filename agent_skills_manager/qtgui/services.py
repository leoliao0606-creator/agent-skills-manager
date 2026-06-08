"""Qt-free service layer between the GUI and the existing core modules.

This is the only module in :mod:`agent_skills_manager.qtgui` that must import
*without* PySide6, so the bulk of the GUI behaviour stays unit-testable without
the ``[qt]`` extra. It contains no business logic of its own: every function
delegates to ``config``/``commands``/``sync``/``gitutil``/``validate``/``fsutil``
and reshapes the result into plain dataclasses the Qt widgets can render.
"""
from __future__ import annotations

import argparse
import difflib
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from .. import commands, config, fsutil, gitutil, skills, sync, validate
from ..config import SkillTarget


# --------------------------------------------------------------------------- #
# Dataclasses (plain, Qt-free result types)
# --------------------------------------------------------------------------- #

@dataclass
class OverviewStatus:
    config_path: str
    config_exists: bool
    using_implicit_defaults: bool
    repo_dir: str
    repo_initialized: bool
    repo_branch: str
    repo_dirty: bool
    repo_remote: str
    git_available: bool
    target_count: int
    enabled_target_count: int
    local_skill_count: int
    repo_skill_count: int


@dataclass
class TargetStatus:
    name: str
    enabled: bool
    local_dir: str
    repo_dir: str
    local_dir_expanded: str
    repo_dir_expanded: str
    local_skills: int
    repo_skills: int
    status: str


@dataclass
class FileChange:
    path: str            # path relative to the target root
    status: str          # added | modified | deleted | conflict
    source: str
    destination: str


@dataclass
class TargetPlanSummary:
    target: str
    direction: str
    source: str
    destination: str
    missing_source: bool
    added: int
    modified: int
    deleted: int
    conflict: int
    unchanged: int
    files: List[FileChange] = field(default_factory=list)

    @property
    def change_count(self) -> int:
        return self.added + self.modified + self.deleted + self.conflict


@dataclass
class SyncPreview:
    direction: str
    mirror: bool
    targets: List[TargetPlanSummary] = field(default_factory=list)

    @property
    def total_added(self) -> int:
        return sum(t.added for t in self.targets)

    @property
    def total_modified(self) -> int:
        return sum(t.modified for t in self.targets)

    @property
    def total_deleted(self) -> int:
        return sum(t.deleted for t in self.targets)

    @property
    def total_conflict(self) -> int:
        return sum(t.conflict for t in self.targets)

    @property
    def has_conflict(self) -> bool:
        return self.total_conflict > 0


@dataclass
class ValidationFinding:
    severity: str        # error | warning
    target: str
    skill: str           # skill directory name (relative to its root)
    path: str            # file path to open / copy
    message: str
    kind: str            # structure | metadata | duplicate | secret


@dataclass
class SkillSummary:
    target: str
    name: str            # relative skill path, e.g. "category/skill-name"
    location: str        # local | repo
    path: str            # skill directory
    skill_file: str      # SKILL.md path
    meta_name: str       # frontmatter name
    description: str
    version: str


@dataclass
class SkillComparisonRow:
    name: str
    status: str          # only_a | only_b | same | different
    a: Optional[SkillSummary]
    b: Optional[SkillSummary]


@dataclass
class TargetComparison:
    target_a: str
    location_a: str
    target_b: str
    location_b: str
    rows: List[SkillComparisonRow] = field(default_factory=list)


@dataclass
class BackupEntry:
    date: str            # raw timestamp directory name (sortable)
    target: str
    path: str            # per-target backup directory (restore source)
    size_bytes: int
    size_human: str


@dataclass
class ConfigSettings:
    repo_dir: str
    remote_url: str
    default_branch: str
    backups_dir: str
    excludes: List[str]
    config_path: str
    config_exists: bool


# --------------------------------------------------------------------------- #
# Overview
# --------------------------------------------------------------------------- #

def _scan_namespace() -> argparse.Namespace:
    """A Namespace that makes ``collect_scan_targets`` return every target."""
    return argparse.Namespace(all=True, only=None, limit=0, examples=False, format="text")


def load_overview_status() -> OverviewStatus:
    cfg = config.load_config()
    config_path = config.current_config_path()
    records = commands.collect_scan_targets(cfg, _scan_namespace())
    repo = config.expand(cfg.repo_dir)
    git_status = gitutil.collect_git_status(repo)
    initialized = bool(git_status["initialized"])
    branch = gitutil.git_output(["rev-parse", "--abbrev-ref", "HEAD"], repo) if initialized else ""
    return OverviewStatus(
        config_path=str(config_path),
        config_exists=config_path.exists(),
        using_implicit_defaults=not config_path.exists(),
        repo_dir=str(repo),
        repo_initialized=initialized,
        repo_branch=branch,
        repo_dirty=gitutil.repo_dirty(repo) if initialized else False,
        repo_remote=str(git_status["remote"]),
        git_available=gitutil.git_available(),
        target_count=len(cfg.targets or []),
        enabled_target_count=len(config.enabled_targets(cfg)),
        local_skill_count=sum(int(r["local_skills"]) for r in records),
        repo_skill_count=sum(int(r["repo_skills"]) for r in records),
    )


# --------------------------------------------------------------------------- #
# Targets
# --------------------------------------------------------------------------- #

def load_target_statuses() -> List[TargetStatus]:
    cfg = config.load_config()
    repo_root = config.expand(cfg.repo_dir)
    statuses: List[TargetStatus] = []
    for target in cfg.targets or []:
        local = config.expand(target.local_dir)
        repo = repo_root / target.repo_dir
        statuses.append(TargetStatus(
            name=target.name,
            enabled=target.enabled,
            local_dir=target.local_dir,
            repo_dir=target.repo_dir,
            local_dir_expanded=str(local),
            repo_dir_expanded=str(repo),
            local_skills=fsutil.count_skills(local),
            repo_skills=fsutil.count_skills(repo),
            status=commands.scan_target_status(target, local),
        ))
    return statuses


def save_targets(targets: List[SkillTarget]) -> str:
    """Persist an edited target list, preserving all other config fields."""
    cfg = config.load_config()
    cfg.targets = [
        SkillTarget(t.name, t.local_dir, t.repo_dir, bool(t.enabled)) for t in targets
    ]
    config.save_config(cfg)
    return str(config.current_config_path())


# --------------------------------------------------------------------------- #
# Sync preview (read-only)
# --------------------------------------------------------------------------- #

def _summarize_plan(plan: dict) -> TargetPlanSummary:
    src = str(plan["source"])
    dst = str(plan["destination"])
    files: List[FileChange] = []
    for rel in plan["add"]:
        files.append(FileChange(rel, "added", os.path.join(src, rel), os.path.join(dst, rel)))
    for rel in plan["update"]:
        files.append(FileChange(rel, "modified", os.path.join(src, rel), os.path.join(dst, rel)))
    for rel in plan["delete"]:
        files.append(FileChange(rel, "deleted", os.path.join(src, rel), os.path.join(dst, rel)))
    for rel in plan["conflict"]:
        files.append(FileChange(rel, "conflict", os.path.join(src, rel), os.path.join(dst, rel)))
    return TargetPlanSummary(
        target=str(plan["target"]),
        direction=str(plan["direction"]),
        source=src,
        destination=dst,
        missing_source=bool(plan["missing_source"]),
        added=len(plan["add"]),
        modified=len(plan["update"]),
        deleted=len(plan["delete"]),
        conflict=len(plan["conflict"]),
        unchanged=len(plan["unchanged"]),
        files=files,
    )


def build_sync_preview(direction: str, mirror: bool = False) -> SyncPreview:
    """Preview a push/pull without touching any files (same plan as ``cmd_diff``)."""
    cfg = config.load_config()
    repo = config.expand(cfg.repo_dir)
    state = config.load_sync_state()
    preview = SyncPreview(direction=direction, mirror=mirror)
    for target in config.enabled_targets(cfg):
        plan = sync.build_target_plan(cfg, repo, target, direction, mirror, state=state)
        preview.targets.append(_summarize_plan(plan))
    return preview


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def _classify_finding(message: str) -> str:
    low = message.lower()
    if "secret" in low or "private key" in low:
        return "secret"
    if "duplicate" in low:
        return "duplicate"
    if "frontmatter" in low:
        return "metadata"
    return "structure"


def run_validation(location: str = "local", target: Optional[str] = None) -> List[ValidationFinding]:
    """Validate skill structure/metadata/duplicates/secrets (mirrors ``cmd_validate``)."""
    cfg = config.load_config()
    findings: List[ValidationFinding] = []
    for tgt, root in validate.validation_roots(cfg, location, target):
        if not root.exists():
            findings.append(ValidationFinding("error", tgt.name, "", str(root), f"missing root: {root}", "structure"))
            continue
        seen_names: dict = {}
        for skill_dir in fsutil.iter_skill_dirs(root):
            skill_file = skill_dir / "SKILL.md"
            skill_name = skill_dir.relative_to(root).as_posix()
            meta = validate.parse_frontmatter(skill_file.read_text(encoding="utf-8", errors="ignore")) if skill_file.exists() else {}
            name = meta.get("name") or skill_dir.name
            if name in seen_names:
                findings.append(ValidationFinding(
                    "error", tgt.name, skill_name, str(skill_dir),
                    f"duplicate skill name '{name}': also {seen_names[name]}", "duplicate",
                ))
            else:
                seen_names[name] = skill_dir
            errors, warnings = validate.validate_skill_dir(skill_dir)
            for err in errors:
                findings.append(ValidationFinding("error", tgt.name, skill_name, str(skill_file), err, _classify_finding(err)))
            for warn in warnings:
                file_path, line = _split_warning_location(warn)
                findings.append(ValidationFinding(
                    "warning", tgt.name, skill_name, file_path or str(skill_file),
                    warn, "secret",
                ))
    return findings


def _split_warning_location(warning: str) -> tuple:
    """Pull the ``path`` out of a ``path:line: message`` secret warning."""
    parts = warning.rsplit(":", 2)
    if len(parts) == 3 and parts[1].strip().isdigit():
        return parts[0], parts[1].strip()
    return "", ""


# --------------------------------------------------------------------------- #
# Skill preview + comparison (read-only)
# --------------------------------------------------------------------------- #

def _to_summary(record: dict, location: str) -> SkillSummary:
    meta = skills.skill_summary(Path(record["skill_file"]))
    return SkillSummary(
        target=record["target"],
        name=record["name"],
        location=location,
        path=record["path"],
        skill_file=record["skill_file"],
        meta_name=meta["name"],
        description=meta["description"],
        version=meta["version"],
    )


def preview_target(target: str, location: str = "local") -> List[SkillSummary]:
    """Summarize one target's skills with frontmatter metadata."""
    cfg = config.load_config()
    return [_to_summary(rec, location) for rec in skills.skill_records(cfg, location, target)]


def compare_targets(target_a: str, location_a: str, target_b: str, location_b: str) -> TargetComparison:
    """Compare two targets' skills by name and directory content (read-only)."""
    cfg = config.load_config()
    comparison = TargetComparison(target_a=target_a, location_a=location_a, target_b=target_b, location_b=location_b)
    for row in skills.compare_skill_records(cfg, target_a, location_a, target_b, location_b):
        a = _to_summary(row["a"], location_a) if row["a"] else None
        b = _to_summary(row["b"], location_b) if row["b"] else None
        comparison.rows.append(SkillComparisonRow(name=str(row["name"]), status=str(row["status"]), a=a, b=b))
    return comparison


def skill_unified_diff(a_skill_file: str, b_skill_file: str, a_label: str, b_label: str) -> str:
    """Unified diff of two SKILL.md files; empty when a side is missing."""
    a_path = Path(a_skill_file) if a_skill_file else None
    b_path = Path(b_skill_file) if b_skill_file else None
    if not a_path or not b_path or not a_path.exists() or not b_path.exists():
        return ""
    a_lines = a_path.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
    b_lines = b_path.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
    return "".join(difflib.unified_diff(a_lines, b_lines, fromfile=a_label, tofile=b_label))


# --------------------------------------------------------------------------- #
# Backups
# --------------------------------------------------------------------------- #

def _dir_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


def _human_size(num: int) -> str:
    size = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def list_backups() -> List[BackupEntry]:
    """List per-target backup directories under ``backups_dir`` (newest first)."""
    cfg = config.load_config()
    root = config.expand(cfg.backups_dir)
    entries: List[BackupEntry] = []
    if not root.exists():
        return entries
    for stamp_dir in sorted(root.glob("*"), reverse=True):
        if not stamp_dir.is_dir():
            continue
        for target_dir in sorted(stamp_dir.iterdir()):
            if not target_dir.is_dir():
                continue
            size = _dir_size(target_dir)
            entries.append(BackupEntry(
                date=stamp_dir.name,
                target=target_dir.name,
                path=str(target_dir),
                size_bytes=size,
                size_human=_human_size(size),
            ))
    return entries


# --------------------------------------------------------------------------- #
# Settings + profiles
# --------------------------------------------------------------------------- #

def load_config_settings() -> ConfigSettings:
    cfg = config.load_config()
    path = config.current_config_path()
    return ConfigSettings(
        repo_dir=cfg.repo_dir,
        remote_url=cfg.remote_url,
        default_branch=cfg.default_branch,
        backups_dir=cfg.backups_dir,
        excludes=list(cfg.excludes or []),
        config_path=str(path),
        config_exists=path.exists(),
    )


def save_config_settings(settings: ConfigSettings) -> str:
    """Persist scalar settings + excludes, leaving the target list untouched."""
    cfg = config.load_config()
    cfg.repo_dir = settings.repo_dir
    cfg.remote_url = settings.remote_url
    cfg.default_branch = settings.default_branch
    cfg.backups_dir = settings.backups_dir
    cfg.excludes = list(settings.excludes)
    config.save_config(cfg)
    return str(config.current_config_path())


def list_profiles() -> List[str]:
    profiles = ["default"]
    profile_dir = config.profile_dir()
    if profile_dir.exists():
        profiles.extend(sorted(path.stem for path in profile_dir.glob("*.json")))
    return profiles


def active_profile() -> str:
    return config.ACTIVE_PROFILE or "default"


def set_active_profile(name: Optional[str]) -> None:
    config.ACTIVE_PROFILE = None if not name or name == "default" else name


# --------------------------------------------------------------------------- #
# Misc helpers used by pages
# --------------------------------------------------------------------------- #

def export_summary() -> str:
    """A plain-text snapshot of config + targets, for the Settings export action."""
    overview = load_overview_status()
    lines = [
        "Agent Skills Manager — summary",
        time.strftime("Generated: %Y-%m-%d %H:%M:%S"),
        "",
        f"Config:  {overview.config_path}" + ("" if overview.config_exists else "  (implicit defaults)"),
        f"Repo:    {overview.repo_dir}",
        f"Branch:  {overview.repo_branch or '(n/a)'}",
        f"Targets: {overview.enabled_target_count} enabled / {overview.target_count} total",
        f"Skills:  local={overview.local_skill_count}  repo={overview.repo_skill_count}",
        "",
        "Targets:",
    ]
    for target in load_target_statuses():
        state = "on " if target.enabled else "off"
        lines.append(
            f"  [{state}] {target.name}: {target.local_dir} -> {target.repo_dir} "
            f"(local={target.local_skills}, repo={target.repo_skills}, {target.status})"
        )
    return "\n".join(lines) + "\n"
