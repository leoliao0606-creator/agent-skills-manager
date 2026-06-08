"""Core operational and management commands.

Covers scanning/status reporting, the push/pull/sync/diff workflow, repo
initialization, doctor, the interactive setup wizard, and scriptable
config/target/profile management.
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List

from . import config, fsutil, gitutil, sync, tui


# ----- Config status helpers -----

def config_metadata() -> Dict[str, object]:
    path = config.current_config_path()
    exists = path.exists()
    return {
        "config": str(path),
        "config_exists": exists,
        "using_implicit_defaults": not exists,
    }


def require_saved_config_for_write(args: argparse.Namespace, command: str) -> None:
    if config.config_file_exists():
        return
    if getattr(args, "dry_run", False):
        print(f"Warning: no config file found at {config.current_config_path()}; using implicit defaults for this dry run only.")
        return
    raise SystemExit(
        f"No config file found at {config.current_config_path()}. "
        f"Run 'agent-skills setup' before 'agent-skills {command}', "
        "or use a dry run first to preview implicit defaults."
    )


# ----- Scan/status -----

def scan_target_status(target: config.SkillTarget, local: Path) -> str:
    if not local.exists():
        return "not exist"
    return "configured" if target.enabled else "not configured"


def scan_args_limit(args: argparse.Namespace) -> int:
    return max(0, int(getattr(args, "limit", 5)))


def target_matches_filter(target: config.SkillTarget, local: Path, args: argparse.Namespace) -> bool:
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


def collect_scan_targets(cfg: config.Config, args: argparse.Namespace) -> List[Dict[str, object]]:
    repo_root = config.expand(cfg.repo_dir)
    records: List[Dict[str, object]] = []
    example_limit = scan_args_limit(args)
    include_examples = bool(getattr(args, "examples", True))
    for target in cfg.targets or []:
        local = config.expand(target.local_dir)
        if not target_matches_filter(target, local, args):
            continue
        repo = repo_root / target.repo_dir
        skill_dirs = list(fsutil.iter_skill_dirs(local))
        examples = [str(p.relative_to(local)) for p in skill_dirs[:example_limit]] if include_examples else []
        status = scan_target_status(target, local)
        records.append({
            "name": target.name,
            "configured": target.enabled,
            "status": status,
            "local": str(local),
            "repo": str(repo),
            "local_skills": fsutil.count_skills(local),
            "repo_skills": fsutil.count_skills(repo),
            "examples": examples,
            "has_more_examples": include_examples and len(skill_dirs) > len(examples),
        })
    return records


def print_scan_records(cfg: config.Config, records: List[Dict[str, object]], args: argparse.Namespace, include_header: bool = True) -> None:
    output_format = getattr(args, "format", "text")
    if output_format == "json":
        payload = config_metadata()
        payload.update({
            "repo": str(config.expand(cfg.repo_dir)),
            "targets": records,
        })
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    if output_format == "names":
        for record in records:
            print(record["name"])
        return

    if include_header:
        tui.print_ascii_header("Agent Skills Scan", args)
        if config.current_config_path().exists():
            print(f"{tui.color_text('Config:', 'blue', args)} {config.current_config_path()}")
        else:
            print(f"{tui.color_text('Config:', 'blue', args)} (not created yet; using implicit defaults)")
            print("Run 'agent-skills setup' to save these defaults before real push/pull/sync operations.")
        print(f"{tui.color_text('Repo:', 'blue', args)}   {config.expand(cfg.repo_dir)}")
        print()
    for record in records:
        status = str(record["status"])
        print(f"[{tui.color_text(str(record['name']), 'bold', args)}] {tui.color_text(status, tui.status_color(status), args)}")
        if record["status"] == "not exist":
            print()
            continue
        print(f"  {tui.color_text('local:', 'dim', args)} {record['local']}  skills={record['local_skills']}")
        if record["status"] == "configured":
            print(f"  {tui.color_text('repo:', 'dim', args)}  {record['repo']}  skills={record['repo_skills']}")
            for example in record["examples"]:  # type: ignore[index]
                print(f"    - {example}")
            if record["has_more_examples"]:
                print("    ...")
        print()


def cmd_scan(args: argparse.Namespace) -> None:
    cfg = config.load_config()
    print_scan_records(cfg, collect_scan_targets(cfg, args), args)


# ----- Push/pull/sync -----

def cmd_push(args: argparse.Namespace) -> None:
    require_saved_config_for_write(args, "push")
    cfg = config.load_config()
    repo = sync.ensure_repo(cfg, create=getattr(args, "create_repo", False), clone=True)
    dirty_before = gitutil.repo_dirty(repo)
    if dirty_before and not getattr(args, "allow_dirty", False):
        if getattr(args, "dry_run", False):
            print("Repo has uncommitted changes; continuing because this is a dry run.")
        else:
            raise SystemExit(f"Repo has uncommitted changes. Inspect first: git -C {repo} status")

    if not getattr(args, "dry_run", False):
        gitutil.ensure_push_branch(repo, cfg.default_branch)
        gitutil.maybe_pull(repo, args.no_pull)

    state = config.load_sync_state()
    plans: List[Dict[str, object]] = []
    total = 0
    for target in config.enabled_targets(cfg):
        plan = sync.build_target_plan(cfg, repo, target, "push", args.mirror, state=state)
        if sync.fail_or_skip_missing(plan, target, getattr(args, "strict", False)):
            continue
        if plan.get("conflict") and not getattr(args, "force", False):
            sync.print_plan(plan, f"Sync local -> repo [{target.name}]")
            raise SystemExit("Conflicting files detected; inspect with agent-skills diff --direction push or re-run with --force.")
        plans.append(plan)
    sync.maybe_confirm_mirror(args, plans)

    for plan in plans:
        target = config.get_target(cfg, str(plan["target"]))
        src, dst = sync.target_source_destination(cfg, repo, target, "push")
        print(f"Sync local -> repo [{target.name}]\n  from: {src}\n  to:   {dst}")
        changed, deleted = sync.apply_copy_plan(src, dst, plan, dry_run=args.dry_run)
        print(f"  changed={changed} deleted={deleted}")
        total += changed + deleted
        if not args.dry_run and changed + deleted:
            sync.mark_state_after_sync(state, repo, target, cfg)

    if args.dry_run:
        print("Dry run complete; no commit or push.")
        return
    if total:
        config.save_sync_state(state)
    if not gitutil.repo_dirty(repo):
        print("No repo changes to commit or push.")
        return
    gitutil.run(["git", "add", "."], cwd=repo)
    gitutil.run(["git", "commit", "-m", args.message], cwd=repo)
    if gitutil.git_output(["remote", "get-url", "origin"], repo):
        gitutil.run(["git", "push", "-u", "origin", cfg.default_branch], cwd=repo)
    else:
        print("Committed locally. No origin remote configured, so nothing was pushed.")


def cmd_pull(args: argparse.Namespace) -> None:
    require_saved_config_for_write(args, "pull")
    cfg = config.load_config()
    repo = sync.ensure_repo(cfg, clone=True)
    gitutil.maybe_pull(repo, args.no_pull)
    state = config.load_sync_state()
    plans: List[Dict[str, object]] = []
    total = 0
    for target in config.enabled_targets(cfg):
        plan = sync.build_target_plan(cfg, repo, target, "pull", args.mirror, state=state)
        if sync.fail_or_skip_missing(plan, target, getattr(args, "strict", False)):
            continue
        if plan.get("conflict") and not getattr(args, "force", False):
            sync.print_plan(plan, f"Sync repo -> local [{target.name}]")
            raise SystemExit("Conflicting files detected; inspect with agent-skills diff --direction pull or re-run with --force.")
        plans.append(plan)
    sync.maybe_confirm_mirror(args, plans)

    for plan in plans:
        target = config.get_target(cfg, str(plan["target"]))
        src, dst = sync.target_source_destination(cfg, repo, target, "pull")
        print(f"Sync repo -> local [{target.name}]\n  from: {src}\n  to:   {dst}")
        if not args.dry_run and getattr(args, "backup", True) and sync.plan_write_count(plan) and dst.exists():
            sync.create_backup(cfg, target, dst)
        changed, deleted = sync.apply_copy_plan(src, dst, plan, dry_run=args.dry_run)
        print(f"  changed={changed} deleted={deleted}")
        total += changed + deleted
        if not args.dry_run and changed + deleted:
            sync.mark_state_after_sync(state, repo, target, cfg)
    if not args.dry_run and total:
        config.save_sync_state(state)
    print("Dry run complete." if args.dry_run else f"Done. File changes: {total}")
    print("Reload/restart your agent sessions so they see updated skills.")


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


def cmd_diff(args: argparse.Namespace) -> None:
    cfg = config.load_config()
    repo = config.expand(cfg.repo_dir)
    state = config.load_sync_state()
    plans = [sync.build_target_plan(cfg, repo, target, args.direction, args.mirror, state=state) for target in config.enabled_targets(cfg)]
    if getattr(args, "format", "text") == "json":
        print(json.dumps({"repo": str(repo), "direction": args.direction, "mirror": args.mirror, "plans": [sync.serializable_plan(p) for p in plans]}, indent=2, ensure_ascii=False))
        return
    tui.print_ascii_header("Agent Skills Diff", args)
    for plan in plans:
        sync.print_plan(plan, f"[{plan['target']}] {args.direction}: {plan['source']} -> {plan['destination']}")


def cmd_plan(args: argparse.Namespace) -> None:
    args.direction = args.direction or args.plan_direction
    cmd_diff(args)


# ----- Status/init-repo/doctor -----

def cmd_status(args: argparse.Namespace) -> None:
    cfg = config.load_config()
    repo = config.expand(cfg.repo_dir)
    output_format = getattr(args, "format", "text")
    include_git = not getattr(args, "no_git", False)
    include_scan = not getattr(args, "no_scan", False)

    if output_format == "json":
        payload: Dict[str, object] = config_metadata()
        payload["repo"] = str(repo)
        if include_git:
            payload["git"] = gitutil.collect_git_status(repo)
        if include_scan:
            payload["targets"] = collect_scan_targets(cfg, args)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    if output_format == "names":
        print_scan_records(cfg, collect_scan_targets(cfg, args), args, include_header=False)
        return

    if include_git:
        tui.print_ascii_header("Agent Skills Status", args)
        if config.current_config_path().exists():
            print(f"{tui.color_text('Config:', 'blue', args)} {config.current_config_path()}")
        else:
            print(f"{tui.color_text('Config:', 'blue', args)} (not created yet; using implicit defaults)")
            print("Run 'agent-skills setup' to save these defaults before real push/pull/sync operations.")
        print(f"{tui.color_text('Repo:', 'blue', args)} {repo}")
        git_status = gitutil.collect_git_status(repo)
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
    cfg = config.load_config()
    if args.repo:
        cfg.repo_dir = args.repo
    if args.remote is not None:
        cfg.remote_url = args.remote
    config.save_config(cfg)
    repo = sync.ensure_repo(cfg, create=True)
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
        ignore.write_text("\n".join(config.DEFAULT_EXCLUDES) + "\n", encoding="utf-8")
    print(f"Repo initialized: {repo}")


def cmd_doctor(args: argparse.Namespace) -> None:
    cfg = config.load_config()
    repo = config.expand(cfg.repo_dir)
    checks: List[Dict[str, str]] = []

    def add(level: str, message: str) -> None:
        checks.append({"level": level, "message": message})

    if gitutil.git_available():
        add("ok", "git is available")
    else:
        add("error", "git is not installed or not in PATH")
    if config.current_config_path().exists():
        add("ok", f"config exists: {config.current_config_path()}")
    else:
        add("warn", f"config has not been created yet: {config.current_config_path()}")
        add("warn", "using implicit defaults; run 'agent-skills setup' before real push/pull/sync operations")
    reasons = sync.dangerous_repo_reasons(repo, cfg)
    if reasons:
        for reason in reasons:
            add("error", reason)
    else:
        add("ok", f"repo path looks safe: {repo}")
    if (repo / ".git").exists():
        add("ok", "repo is initialized")
        if gitutil.repo_dirty(repo):
            add("warn", "repo has uncommitted changes")
        remote = gitutil.git_output(["remote", "get-url", "origin"], repo)
        add("ok" if remote else "warn", f"origin remote: {remote or '(not configured)'}")
    else:
        add("warn", "repo is not initialized yet")
    for target in cfg.targets or []:
        local = config.expand(target.local_dir)
        if target.enabled and local.exists():
            add("ok", f"target {target.name}: configured, local exists, skills={fsutil.count_skills(local)}")
        elif target.enabled:
            add("error", f"target {target.name}: configured local directory does not exist: {local}")
        elif local.exists():
            add("warn", f"target {target.name}: local exists but is not configured")
    if getattr(args, "format", "text") == "json":
        payload = config_metadata()
        payload.update({"repo": str(repo), "checks": checks})
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        tui.print_ascii_header("Agent Skills Doctor", args)
        for check in checks:
            print(f"{check['level'].upper()}: {check['message']}")
    if any(check["level"] == "error" for check in checks):
        raise SystemExit(1)


# ----- Setup wizard -----

def cmd_setup(args: argparse.Namespace) -> None:
    del args
    if not gitutil.git_available():
        raise SystemExit("git is required. Install git first.")
    cfg = config.load_config()
    cfg.repo_dir = config.detect_default_repo()
    cfg.remote_url = ""
    cfg.default_branch = "main"
    print("Agent Skills Manager setup wizard")
    print("I will scan installed skill folders and help you connect them to a private repo.\n")
    print("Local repo checkout path = the local Git checkout directory for your skills repo.")
    print("  Example: ~/agent-skills-library")
    print("  This should be the repo folder containing .git, not your home directory like /home or ~.\n")

    cfg.repo_dir = tui.read_path_answer("Local repo checkout path", cfg.repo_dir)
    cfg.remote_url = tui.read_answer("Git remote URL (SSH or HTTPS; empty is OK for local-only)", "")
    cfg.default_branch = tui.read_answer("Default branch", cfg.default_branch or "main")

    targets_by_name = {t.name: t for t in config.candidate_targets()}
    for existing in cfg.targets or []:
        targets_by_name[existing.name] = existing
    available_targets = list(targets_by_name.values())
    default_indexes = [idx for idx, target in enumerate(available_targets) if target.enabled]
    selected_indexes = tui.read_multiselect("\nChoose which agents to sync:", available_targets, default_indexes)
    selected_set = set(selected_indexes)

    new_targets: List[config.SkillTarget] = []
    for idx, t in enumerate(available_targets):
        enable = idx in selected_set
        if enable:
            print(f"\n[{t.name}]")
            local = tui.read_path_answer(f"{t.name} local skills directory", t.local_dir)
            found = fsutil.count_skills(config.expand(local))
            print(f"  found {found} skills in {config.expand(local)}")
            repo_dir = tui.read_answer(f"{t.name} directory inside repo", t.repo_dir)
            new_targets.append(config.SkillTarget(t.name, local, repo_dir, True))
        else:
            new_targets.append(config.SkillTarget(t.name, t.local_dir, t.repo_dir, False))

    cfg.targets = new_targets
    config.save_config(cfg)
    print(f"\nSaved config: {config.current_config_path()}")

    if not (config.expand(cfg.repo_dir) / ".git").exists():
        if cfg.remote_url and tui.yes("Clone the remote repo now", True):
            sync.ensure_repo(cfg, clone=True)
        elif tui.yes("Create a new local git repo now", True):
            sync.ensure_repo(cfg, create=True)

    if tui.yes("Do an initial push of installed local skills into the repo", True):
        cmd_push(argparse.Namespace(message="Initial skill sync", dry_run=False, mirror=False, no_pull=True, allow_dirty=False, create_repo=True, force=False, strict=False, yes=False))
    else:
        print("Next: agent-skills push --dry-run")


# ----- Scriptable config/target/profile management -----

def cmd_config_show(args: argparse.Namespace) -> None:
    cfg = config.load_config()
    payload = config_metadata()
    payload["settings"] = asdict(cfg)
    if getattr(args, "format", "text") == "json":
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        status = "exists" if payload["config_exists"] else "not created yet; using implicit defaults"
        print(f"Config: {config.current_config_path()} ({status})")
        if payload["using_implicit_defaults"]:
            print("Run 'agent-skills setup' to save a config before real push/pull/sync operations.")
        print(json.dumps(asdict(cfg), indent=2, ensure_ascii=False))


def cmd_config_path(args: argparse.Namespace) -> None:
    del args
    print(config.current_config_path())


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
    cfg = config.load_config()
    if args.key not in {"repo_dir", "remote_url", "default_branch", "backups_dir", "excludes"}:
        raise SystemExit(f"Unsupported config key: {args.key}")
    setattr(cfg, args.key, parse_config_value(args.key, args.value))
    config.save_config(cfg)
    print(f"Set {args.key} in {config.current_config_path()}")


def cmd_target_list(args: argparse.Namespace) -> None:
    cfg = config.load_config()
    records = [asdict(target) for target in cfg.targets or []]
    if getattr(args, "format", "text") == "json":
        print(json.dumps(records, indent=2, ensure_ascii=False))
        return
    for target in cfg.targets or []:
        status = "configured" if target.enabled else "not configured"
        print(f"{target.name}\t{status}\t{target.local_dir}\t{target.repo_dir}")


def cmd_target_add(args: argparse.Namespace) -> None:
    cfg = config.load_config()
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
        targets.insert(0, config.SkillTarget(args.name, args.local, args.repo, not getattr(args, "disabled", False)))
    cfg.targets = targets
    config.save_config(cfg)
    print(("Updated" if updated else "Added") + f" target: {args.name}")


def set_target_enabled(name: str, enabled: bool) -> None:
    cfg = config.load_config()
    target = config.get_target(cfg, name)
    target.enabled = enabled
    config.save_config(cfg)
    print(f"{'Enabled' if enabled else 'Disabled'} target: {name}")


def cmd_target_enable(args: argparse.Namespace) -> None:
    set_target_enabled(args.name, True)


def cmd_target_disable(args: argparse.Namespace) -> None:
    set_target_enabled(args.name, False)


def cmd_target_remove(args: argparse.Namespace) -> None:
    cfg = config.load_config()
    before = len(cfg.targets or [])
    cfg.targets = [target for target in (cfg.targets or []) if target.name != args.name]
    if len(cfg.targets) == before:
        raise SystemExit(f"Unknown target: {args.name}")
    config.save_config(cfg)
    print(f"Removed target: {args.name}")


def cmd_profile_list(args: argparse.Namespace) -> None:
    del args
    print("default")
    if config.profile_dir().exists():
        for path in sorted(config.profile_dir().glob("*.json")):
            print(path.stem)


def cmd_profile_create(args: argparse.Namespace) -> None:
    cfg = config.load_config()
    config.save_config(cfg, profile=args.name)
    print(f"Created profile {args.name}: {config.config_path_for_profile(args.name)}")


def cmd_profile_use(args: argparse.Namespace) -> None:
    source = config.config_path_for_profile(args.name)
    if not source.exists():
        raise SystemExit(f"Profile not found: {args.name}")
    config.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, config.CONFIG_PATH)
    print(f"Activated profile {args.name}: {config.CONFIG_PATH}")


def cmd_install_shell(args: argparse.Namespace) -> None:
    if platform.system() == "Windows":
        raise SystemExit(
            "install-shell creates POSIX shell wrappers and is not supported on Windows. "
            "Use: py -m pip install -e ."
        )
    bindir = config.expand(args.bindir)
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
