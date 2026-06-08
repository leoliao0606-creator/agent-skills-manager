"""Filesystem helpers: skill discovery, hashing, and ignore-pattern matching."""
from __future__ import annotations

import fnmatch
import hashlib
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from . import config
from .config import Config


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
    patterns = list((cfg.excludes if cfg and cfg.excludes else config.DEFAULT_EXCLUDES))
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
