"""Skill browsing and authoring commands: list, search, show, open, new,
export, import, and backup listing/restore."""
from __future__ import annotations

import argparse
import difflib
import json
import os
import platform
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import config, fsutil, sync, validate
from .config import Config


def skill_records(cfg: Config, location: str = "local", target_name: Optional[str] = None) -> List[Dict[str, str]]:
    repo = config.expand(cfg.repo_dir)
    selected = [config.get_target(cfg, target_name)] if target_name else config.enabled_targets(cfg)
    records: List[Dict[str, str]] = []
    for target in selected:
        root = repo / target.repo_dir if location == "repo" else config.expand(target.local_dir)
        if not root.exists():
            continue
        for skill_dir in fsutil.iter_skill_dirs(root):
            rel = skill_dir.relative_to(root).as_posix()
            records.append({"target": target.name, "name": rel, "path": str(skill_dir), "skill_file": str(skill_dir / "SKILL.md"), "location": location})
    return sorted(records, key=lambda item: (item["target"], item["name"]))


def skill_summary(skill_file: Path) -> Dict[str, str]:
    """Return the SKILL.md frontmatter summary (name/description/version)."""
    text = skill_file.read_text(encoding="utf-8", errors="ignore") if skill_file.exists() else ""
    meta = validate.parse_frontmatter(text)
    return {
        "name": meta.get("name", ""),
        "description": meta.get("description", ""),
        "version": meta.get("version", ""),
    }


def compare_skill_records(
    cfg: Config,
    target_a: str,
    loc_a: str,
    target_b: str,
    loc_b: str,
) -> List[Dict[str, object]]:
    """Compare two targets' skills by name, then by directory content.

    Each row is ``{"name", "status", "a", "b"}`` where ``status`` is one of
    ``only_a``/``only_b``/``same``/``different`` and ``a``/``b`` are the matching
    skill records (or ``None`` when the skill is missing on that side).
    """
    patterns = fsutil.read_ignore_patterns(cfg=cfg)
    a_map = {rec["name"]: rec for rec in skill_records(cfg, loc_a, target_a)}
    b_map = {rec["name"]: rec for rec in skill_records(cfg, loc_b, target_b)}
    rows: List[Dict[str, object]] = []
    for name in sorted(set(a_map) | set(b_map)):
        a_rec = a_map.get(name)
        b_rec = b_map.get(name)
        if a_rec and not b_rec:
            status = "only_a"
        elif b_rec and not a_rec:
            status = "only_b"
        else:
            a_hashes = fsutil.collect_file_hashes(Path(a_rec["path"]), patterns)
            b_hashes = fsutil.collect_file_hashes(Path(b_rec["path"]), patterns)
            status = "same" if a_hashes == b_hashes else "different"
        rows.append({"name": name, "status": status, "a": a_rec, "b": b_rec})
    return rows


def cmd_preview(args: argparse.Namespace) -> None:
    cfg = config.load_config()
    records = skill_records(cfg, args.location, args.target)
    for record in records:
        record.update(skill_summary(Path(record["skill_file"])))
    fmt = getattr(args, "format", "text")
    if fmt == "json":
        print(json.dumps(records, indent=2, ensure_ascii=False))
    elif fmt == "names":
        for record in records:
            print(f"{record['target']}:{record['name']}")
    else:
        for record in records:
            version = record.get("version") or "-"
            description = record.get("description") or ""
            print(f"{record['name']}\t{version}\t{description}")


def cmd_compare(args: argparse.Namespace) -> None:
    cfg = config.load_config()
    rows = compare_skill_records(cfg, args.target_a, args.a_location, args.target_b, args.b_location)
    if getattr(args, "format", "text") == "json":
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        for row in rows:
            print(f"  {row['status']:<10}{row['name']}")


def cmd_copy_skill(args: argparse.Namespace) -> None:
    cfg = config.load_config()
    src_record = resolve_skill_spec(cfg, args.spec, repo=getattr(args, "from_location", "local") == "repo")
    src = Path(src_record["path"])
    skill_name = src_record["name"]
    dst_target = config.get_target(cfg, args.to_target)
    to_repo = getattr(args, "to_location", "local") == "repo"
    dst_root = (config.expand(cfg.repo_dir) / dst_target.repo_dir) if to_repo else config.expand(dst_target.local_dir)
    dst = dst_root / skill_name
    # Back up the whole destination *local* target before overwriting an existing
    # skill, mirroring how pull backs up local dirs. Repo copies rely on git, and
    # backing up the target root (not just the skill) keeps restore-backup usable.
    if not to_repo and dst.exists() and getattr(args, "backup", True) and not getattr(args, "dry_run", False):
        sync.create_backup(cfg, dst_target, dst_root)
    patterns = fsutil.read_ignore_patterns(src, dst, cfg=cfg)
    plan = sync.build_copy_plan(src, dst, mirror=getattr(args, "mirror", False), patterns=patterns)
    if plan.get("conflict") and not getattr(args, "force", False):
        sync.print_plan(plan, f"Copy {args.spec} -> {dst_target.name}")
        raise SystemExit("Conflicting files detected; re-run with --force after reviewing.")
    sync.maybe_confirm_mirror(args, [plan])
    changed, deleted = sync.apply_copy_plan(src, dst, plan, dry_run=getattr(args, "dry_run", False))
    print(f"Copied {args.spec} into {dst}; changed={changed} deleted={deleted}")


def cmd_list(args: argparse.Namespace) -> None:
    cfg = config.load_config()
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
    cfg = config.load_config()
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
    cfg = config.load_config()
    record = resolve_skill_spec(cfg, args.spec, repo=getattr(args, "repo", False))
    print(Path(record["skill_file"]).read_text(encoding="utf-8"), end="")


def cmd_open(args: argparse.Namespace) -> None:
    cfg = config.load_config()
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
    cfg = config.load_config()
    target = config.get_target(cfg, args.target)
    root = (config.expand(cfg.repo_dir) / target.repo_dir) if getattr(args, "repo", False) else config.expand(target.local_dir)
    slug = config.slugify(args.name)
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
    cfg = config.load_config()
    target = config.get_target(cfg, args.target)
    root = (config.expand(cfg.repo_dir) / target.repo_dir) if getattr(args, "repo", False) else config.expand(target.local_dir)
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
    cfg = config.load_config()
    target = config.get_target(cfg, args.target)
    dst = (config.expand(cfg.repo_dir) / target.repo_dir) if getattr(args, "repo", False) else config.expand(target.local_dir)
    source_arg = Path(args.path).expanduser().resolve()
    if not source_arg.exists():
        raise SystemExit(f"Import source not found: {source_arg}")
    temp, src = extract_import_source(source_arg)
    try:
        patterns = fsutil.read_ignore_patterns(src, dst, cfg=cfg)
        plan = sync.build_copy_plan(src, dst, mirror=getattr(args, "mirror", False), patterns=patterns)
        if plan.get("conflict") and not getattr(args, "force", False):
            sync.print_plan(plan, f"Import -> {target.name}")
            raise SystemExit("Conflicting files detected; re-run with --force after reviewing.")
        sync.maybe_confirm_mirror(args, [plan])
        changed, deleted = sync.apply_copy_plan(src, dst, plan, dry_run=getattr(args, "dry_run", False))
        print(f"Imported into {dst}; changed={changed} deleted={deleted}")
    finally:
        temp.cleanup()


def cmd_backups_list(args: argparse.Namespace) -> None:
    cfg = config.load_config()
    root = config.expand(cfg.backups_dir)
    if not root.exists():
        return
    for path in sorted(root.glob("*")):
        if path.is_dir():
            print(path)


def cmd_restore_backup(args: argparse.Namespace) -> None:
    cfg = config.load_config()
    target = config.get_target(cfg, args.target)
    src = Path(args.path).expanduser().resolve()
    if not src.exists():
        raise SystemExit(f"Backup path not found: {src}")
    dst = config.expand(target.local_dir)
    patterns = fsutil.read_ignore_patterns(src, dst, cfg=cfg)
    plan = sync.build_copy_plan(src, dst, mirror=getattr(args, "mirror", True), patterns=patterns)
    sync.maybe_confirm_mirror(args, [plan])
    changed, deleted = sync.apply_copy_plan(src, dst, plan, dry_run=getattr(args, "dry_run", False))
    print(f"Restored backup to {dst}; changed={changed} deleted={deleted}")
