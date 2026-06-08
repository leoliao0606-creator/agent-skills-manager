"""Experimental Tkinter settings-and-sync window."""
from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Dict, List

from . import config
from .config import Config, SkillTarget


def cmd_gui(args: argparse.Namespace) -> None:
    del args
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except Exception as exc:  # pragma: no cover
        raise SystemExit(f"Tkinter GUI is not available on this system: {exc}")

    cfg = config.load_config()
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
        path = filedialog.askdirectory(initialdir=str(config.expand(repo_var.get()).parent))
        if path:
            repo_var.set(path)

    def collect() -> Config:
        targets: List[SkillTarget] = []
        for name, vs in target_vars.items():
            targets.append(SkillTarget(name, str(vs["local"].get()), str(vs["repo"].get()), bool(vs["enabled"].get())))
        return Config(repo_var.get(), remote_var.get(), branch_var.get(), targets, cfg.backups_dir, cfg.excludes)

    def save() -> None:
        config.save_config(collect())
        messagebox.showinfo("Saved", f"Saved config:\n{config.current_config_path()}")

    def run_action(action: str) -> None:
        config.save_config(collect())
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
