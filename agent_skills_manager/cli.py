#!/usr/bin/env python3
"""Manage private AI agent skill repositories.

This tool intentionally uses only the Python standard library so it can run on a
fresh VPS or laptop without bootstrapping dependencies.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    import readline  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - readline is not available on some platforms.
    readline = None  # type: ignore[assignment]

APP_NAME = "agent-skills-manager"


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
DEFAULT_REPO = "~/agent-skills-library"


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
    targets: List[SkillTarget] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.targets is None:
            self.targets = default_targets()


def expand(path: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(path))).resolve()


def has_skills(path: str) -> bool:
    expanded = expand(path)
    if not expanded.exists():
        return False
    return any(expanded.rglob("SKILL.md"))


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


def load_config() -> Config:
    if not CONFIG_PATH.exists():
        return Config(repo_dir=str(detect_default_repo()), targets=default_targets())
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    targets = [SkillTarget(**t) for t in data.get("targets", [])] or default_targets()
    return Config(
        repo_dir=data.get("repo_dir", str(detect_default_repo())),
        remote_url=data.get("remote_url", ""),
        default_branch=data.get("default_branch", "main"),
        targets=targets,
    )


def save_config(cfg: Config) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(cfg)
    CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


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


def copy_tree(src: Path, dst: Path, dry_run: bool = False, mirror: bool = False) -> Tuple[int, int]:
    """Copy files from src to dst. Returns (copied_or_updated, deleted)."""
    if not src.exists():
        raise SystemExit(f"Missing source directory: {src}")
    copied = 0
    deleted = 0
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            if not dry_run:
                target.mkdir(parents=True, exist_ok=True)
            continue
        if not target.exists() or item.read_bytes() != target.read_bytes():
            print(f"  copy {rel}")
            copied += 1
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
    if mirror and dst.exists():
        src_rels = {p.relative_to(src) for p in src.rglob("*")}
        for item in sorted(dst.rglob("*"), reverse=True):
            rel = item.relative_to(dst)
            if rel not in src_rels:
                print(f"  delete {rel}")
                deleted += 1
                if not dry_run:
                    if item.is_dir():
                        try:
                            item.rmdir()
                        except OSError:
                            pass
                    else:
                        item.unlink()
    return copied, deleted


def ensure_repo(cfg: Config, create: bool = False, clone: bool = False) -> Path:
    repo = expand(cfg.repo_dir)
    if repo.exists() and (repo / ".git").exists():
        return repo
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
    for existing in cfg.targets:
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
    print(f"\nSaved config: {CONFIG_PATH}")

    if not (expand(cfg.repo_dir) / ".git").exists():
        if cfg.remote_url and yes("Clone the remote repo now", True):
            ensure_repo(cfg, clone=True)
        elif yes("Create a new local git repo now", True):
            ensure_repo(cfg, create=True)

    if yes("Do an initial push of installed local skills into the repo", True):
        cmd_push(argparse.Namespace(message="Initial skill sync", dry_run=False, mirror=False, no_pull=True, allow_dirty=False, create_repo=True))
    else:
        print("Next: agent-skills push --dry-run")


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
    for target in cfg.targets:
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
        print(json.dumps({
            "config": str(CONFIG_PATH) if CONFIG_PATH.exists() else None,
            "repo": str(expand(cfg.repo_dir)),
            "targets": records,
        }, indent=2, ensure_ascii=False))
        return
    if output_format == "names":
        for record in records:
            print(record["name"])
        return

    if include_header:
        print(f"Config: {CONFIG_PATH if CONFIG_PATH.exists() else '(not created yet)'}")
        print(f"Repo:   {expand(cfg.repo_dir)}")
        print()
    for record in records:
        print(f"[{record['name']}] {record['status']}")
        if record["status"] == "not exist":
            print()
            continue
        print(f"  local: {record['local']}  skills={record['local_skills']}")
        if record["status"] == "configured":
            print(f"  repo:  {record['repo']}  skills={record['repo_skills']}")
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


def cmd_pull(args: argparse.Namespace) -> None:
    cfg = load_config()
    repo = ensure_repo(cfg, clone=True)
    maybe_pull(repo, args.no_pull)
    total = 0
    for t in cfg.targets:
        if not t.enabled:
            continue
        src = repo / t.repo_dir
        dst = expand(t.local_dir)
        print(f"Sync repo -> local [{t.name}]\n  from: {src}\n  to:   {dst}")
        copied, deleted = copy_tree(src, dst, dry_run=args.dry_run, mirror=args.mirror)
        print(f"  changed={copied} deleted={deleted}")
        total += copied + deleted
    print("Dry run complete." if args.dry_run else f"Done. File changes: {total}")
    print("Reload/restart your agent sessions so they see updated skills.")


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


def cmd_push(args: argparse.Namespace) -> None:
    cfg = load_config()
    repo = ensure_repo(cfg, create=getattr(args, "create_repo", False), clone=True)
    if repo_dirty(repo) and not args.allow_dirty:
        raise SystemExit(f"Repo has uncommitted changes. Inspect first: git -C {repo} status")
    ensure_push_branch(repo, cfg.default_branch)
    maybe_pull(repo, args.no_pull)
    total = 0
    for t in cfg.targets:
        if not t.enabled:
            continue
        src = expand(t.local_dir)
        dst = repo / t.repo_dir
        print(f"Sync local -> repo [{t.name}]\n  from: {src}\n  to:   {dst}")
        copied, deleted = copy_tree(src, dst, dry_run=args.dry_run, mirror=args.mirror)
        print(f"  changed={copied} deleted={deleted}")
        total += copied + deleted
    if args.dry_run:
        print("Dry run complete; no commit or push.")
        return
    if not repo_dirty(repo):
        print("No repo changes to commit or push.")
        return
    run(["git", "add", "."], cwd=repo)
    run(["git", "commit", "-m", args.message], cwd=repo)
    if git_output(["remote", "get-url", "origin"], repo):
        run(["git", "push", "-u", "origin", cfg.default_branch], cwd=repo)
    else:
        print("Committed locally. No origin remote configured, so nothing was pushed.")


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
        payload: Dict[str, object] = {
            "config": str(CONFIG_PATH),
            "repo": str(repo),
        }
        if include_git:
            payload["git"] = collect_git_status(repo)
        if include_scan:
            payload["targets"] = collect_scan_targets(cfg, args)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    if include_git:
        print(f"Config: {CONFIG_PATH}")
        print(f"Repo: {repo}")
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
    for t in cfg.targets:
        if t.enabled:
            (repo / t.repo_dir).mkdir(parents=True, exist_ok=True)
    readme = repo / "README.md"
    if not readme.exists():
        readme.write_text("# Private agent skills\n\nManaged by agent-skills-manager.\n", encoding="utf-8")
    gitignore = repo / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(".DS_Store\n__pycache__/\n*.pyc\n", encoding="utf-8")
    print(f"Repo initialized: {repo}")


def cmd_gui(args: argparse.Namespace) -> None:
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
            "If you are on a headless server or SSH session, use the CLI commands instead:\n"
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
        return Config(repo_var.get(), remote_var.get(), branch_var.get(), targets)

    def save() -> None:
        save_config(collect())
        messagebox.showinfo("Saved", f"Saved config:\n{CONFIG_PATH}")

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

    for t in cfg.targets:
        enabled = tk.BooleanVar(value=t.enabled)
        local = tk.StringVar(value=t.local_dir)
        repo_d = tk.StringVar(value=t.repo_dir)
        target_vars[t.name] = {"enabled": enabled, "local": local, "repo": repo_d}
        tk.Checkbutton(root, text=f"Enable {t.name}", variable=enabled).grid(row=row, column=0, sticky="w", padx=8, pady=6)
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
    output.insert(tk.END, "Use Save, Scan, Pull, or Push.\n")
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
    print(f"Make sure {bindir} is in PATH.")


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
    parser.set_defaults(examples=True)
    if include_status_flags:
        parser.add_argument("--no-git", action="store_true", help="hide git status/remotes and show only skill target output")
        parser.add_argument("--no-scan", action="store_true", help="hide skill target output and show only git status/remotes")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent-skills",
        description="Scan installed AI agent skills and sync them with a private Git repository.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Typical workflow:
          agent-skills setup          # hand-holding wizard
          agent-skills scan           # see installed/repo skills
          agent-skills push           # local skills -> repo -> git push
          agent-skills pull           # git pull -> repo skills -> local
          agent-skills gui            # graphical settings window
        """),
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup", help="interactive setup wizard").set_defaults(func=cmd_setup)
    scan = sub.add_parser("scan", help="scan configured skills by default; use filters to include disabled/missing targets")
    add_output_filter_args(scan)
    scan.set_defaults(func=cmd_scan)
    status = sub.add_parser("status", help="show git status and configured skill counts")
    add_output_filter_args(status, include_status_flags=True)
    status.set_defaults(func=cmd_status)

    pull = sub.add_parser("pull", help="sync repo skills into local installed skill dirs")
    pull.add_argument("--dry-run", action="store_true")
    pull.add_argument("--mirror", action="store_true", help="delete destination files that are not in source")
    pull.add_argument("--no-pull", action="store_true", help="skip git pull --ff-only")
    pull.set_defaults(func=cmd_pull)

    push = sub.add_parser("push", help="sync local installed skills into repo, commit, and push")
    push.add_argument("-m", "--message", default="Sync local agent skills")
    push.add_argument("--dry-run", action="store_true")
    push.add_argument("--mirror", action="store_true", help="delete destination files that are not in source")
    push.add_argument("--no-pull", action="store_true", help="skip git pull --ff-only")
    push.add_argument("--allow-dirty", action="store_true", help="allow starting while repo already has uncommitted changes")
    push.add_argument("--create-repo", action="store_true", help="create repo if missing")
    push.set_defaults(func=cmd_push)

    init_repo = sub.add_parser("init-repo", help="create the local private skills repo skeleton")
    init_repo.add_argument("--repo")
    init_repo.add_argument("--remote", default=None)
    init_repo.set_defaults(func=cmd_init_repo)

    sub.add_parser("gui", help="open graphical settings and sync window").set_defaults(func=cmd_gui)
    install = sub.add_parser("install-shell", help="install shell wrapper commands into ~/bin")
    install.add_argument("--bindir", default="~/bin")
    install.set_defaults(func=cmd_install_shell)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        args.func(args)
        return 0
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except EOFError:
        print("\nNo input received; cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
