#!/usr/bin/env python3
"""Manage private AI agent skill repositories.

This tool intentionally uses only the Python standard library so it can run on a
fresh VPS or laptop without bootstrapping dependencies.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

APP_NAME = "agent-skills-manager"
CONFIG_PATH = Path(os.environ.get("AGENT_SKILLS_CONFIG", Path.home() / ".config" / APP_NAME / "config.json"))
DEFAULT_REPO = Path.home() / "Projects" / "personal-agent-skills"
LEGACY_REPO = Path("/home/Projects/personal-agent-skills")


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


def default_targets() -> List[SkillTarget]:
    return [
        SkillTarget("claude", "~/.claude/skills", "agent-skills", True),
        SkillTarget("hermes", "~/.hermes/skills", "hermes-skills", True),
    ]


def detect_default_repo() -> Path:
    if LEGACY_REPO.exists():
        return LEGACY_REPO
    if DEFAULT_REPO.exists():
        return DEFAULT_REPO
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


def yes(prompt: str, default: bool = True) -> bool:
    d = "Y/n" if default else "y/N"
    ans = input(f"{prompt} [{d}]: ").strip().lower()
    if not ans:
        return default
    return ans in {"y", "yes", "是", "好", "1"}


def cmd_setup(args: argparse.Namespace) -> None:
    if not git_available():
        raise SystemExit("git is required. Install git first.")
    cfg = load_config()
    print("Agent Skills Manager setup wizard")
    print("I will scan installed skill folders and help you connect them to a private repo.\n")

    cfg.repo_dir = read_answer("Local repo checkout path", cfg.repo_dir)
    detected_remote = ""
    repo = expand(cfg.repo_dir)
    if (repo / ".git").exists():
        detected_remote = git_output(["remote", "get-url", "origin"], repo)
    cfg.remote_url = read_answer("Git remote URL (SSH or HTTPS; empty is OK for local-only)", cfg.remote_url or detected_remote)
    cfg.default_branch = read_answer("Default branch", cfg.default_branch or "main")

    new_targets: List[SkillTarget] = []
    for t in default_targets():
        local = read_answer(f"{t.name} local skills directory", t.local_dir)
        found = count_skills(expand(local))
        print(f"  found {found} skills in {expand(local)}")
        enable = yes(f"Enable {t.name} sync", found > 0)
        repo_dir = read_answer(f"{t.name} directory inside repo", t.repo_dir)
        new_targets.append(SkillTarget(t.name, local, repo_dir, enable))

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


def cmd_scan(args: argparse.Namespace) -> None:
    cfg = load_config()
    print(f"Config: {CONFIG_PATH if CONFIG_PATH.exists() else '(not created yet)'}")
    print(f"Repo:   {expand(cfg.repo_dir)}")
    print()
    for t in cfg.targets:
        local = expand(t.local_dir)
        repo = expand(cfg.repo_dir) / t.repo_dir
        print(f"[{t.name}] {'enabled' if t.enabled else 'disabled'}")
        print(f"  local: {local}  skills={count_skills(local)}")
        print(f"  repo:  {repo}  skills={count_skills(repo)}")
        examples = list(iter_skill_dirs(local))[:5]
        for e in examples:
            print(f"    - {e.relative_to(local)}")
        if count_skills(local) > len(examples):
            print("    ...")
        print()


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


def cmd_push(args: argparse.Namespace) -> None:
    cfg = load_config()
    repo = ensure_repo(cfg, create=getattr(args, "create_repo", False), clone=True)
    if repo_dirty(repo) and not args.allow_dirty:
        raise SystemExit(f"Repo has uncommitted changes. Inspect first: git -C {repo} status")
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


def cmd_status(args: argparse.Namespace) -> None:
    cfg = load_config()
    repo = expand(cfg.repo_dir)
    print(f"Config: {CONFIG_PATH}")
    print(f"Repo: {repo}")
    if (repo / ".git").exists():
        print(git_output(["status", "--short", "--branch"], repo) or "clean")
        remote = git_output(["remote", "-v"], repo)
        if remote:
            print(remote)
    else:
        print("Repo is not initialized yet.")
    print()
    cmd_scan(args)


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
    root = tk.Tk()
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
        alias.symlink_to(wrapper)
    print(f"Installed wrappers:\n  {wrapper}\n  {alias}")
    print(f"Make sure {bindir} is in PATH.")


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
    sub.add_parser("scan", help="scan installed skills and repo skills").set_defaults(func=cmd_scan)
    sub.add_parser("status", help="show git status and skill counts").set_defaults(func=cmd_status)

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


def main(argv: Optional[List[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
