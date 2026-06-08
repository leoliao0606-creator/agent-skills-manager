"""Skill structure, metadata, duplicate, and secret validation."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import config, fsutil
from .config import Config, SkillTarget

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
    repo = config.expand(cfg.repo_dir)
    selected = [config.get_target(cfg, target_name)] if target_name else config.enabled_targets(cfg)
    roots: List[Tuple[SkillTarget, Path]] = []
    for target in selected:
        roots.append((target, repo / target.repo_dir if location == "repo" else config.expand(target.local_dir)))
    return roots


def cmd_validate(args: argparse.Namespace) -> None:
    cfg = config.load_config()
    errors: List[str] = []
    warnings: List[str] = []
    for target, root in validation_roots(cfg, args.location, args.target):
        if not root.exists():
            errors.append(f"[{target.name}] missing root: {root}")
            continue
        # Duplicate names are only a problem within a single target: two targets
        # (e.g. claude and codex) legitimately hold their own copy of a skill, so
        # cross-target name collisions are neither errors nor warnings.
        seen_names: Dict[str, Path] = {}
        for skill_dir in fsutil.iter_skill_dirs(root):
            meta = parse_frontmatter((skill_dir / "SKILL.md").read_text(encoding="utf-8", errors="ignore")) if (skill_dir / "SKILL.md").exists() else {}
            name = meta.get("name") or skill_dir.name
            if name in seen_names:
                errors.append(f"duplicate skill name '{name}' in target '{target.name}': {seen_names[name]} and {skill_dir}")
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
