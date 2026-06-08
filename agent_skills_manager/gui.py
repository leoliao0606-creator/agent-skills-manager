"""Experimental Tkinter settings-and-sync window.

The GUI is intentionally secondary to the CLI: it edits the same config and
runs the same subcommands as background subprocesses, streaming their output
into a log pane so the window stays responsive during git operations.
"""
from __future__ import annotations

import argparse
import queue
import subprocess
import sys
import threading
from typing import Dict, List, Optional

from . import config
from .config import Config, SkillTarget

# Read-only actions never touch files; sync actions accept dry-run/mirror flags.
GUI_SYNC_ACTIONS = ("pull", "push")
GUI_READONLY_ACTIONS = ("scan", "status", "diff", "validate")


def gui_action_command(
    action: str,
    *,
    dry_run: bool = False,
    mirror: bool = False,
    message: str = "Sync local agent skills",
    python: Optional[str] = None,
) -> List[str]:
    """Build the ``python -m agent_skills_manager.cli ...`` argv for a GUI action.

    Kept as a pure function so the flag assembly is unit-testable without a
    display. ``dry_run``/``mirror`` only apply to the sync actions; ``diff``
    always previews and ``scan``/``status``/``validate`` are read-only.
    """
    python = python or sys.executable
    cmd = [python, "-m", "agent_skills_manager.cli", action]
    if action == "diff":
        cmd += ["--direction", "push"]
    if action in GUI_SYNC_ACTIONS:
        if dry_run:
            cmd.append("--dry-run")
        if mirror:
            cmd += ["--mirror", "--yes"]
    if action == "push":
        cmd += ["-m", message]
    return cmd


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
    root.geometry("820x620")

    repo_var = tk.StringVar(value=cfg.repo_dir)
    remote_var = tk.StringVar(value=cfg.remote_url)
    branch_var = tk.StringVar(value=cfg.default_branch)
    dry_run_var = tk.BooleanVar(value=True)
    mirror_var = tk.BooleanVar(value=False)

    # Each target row keeps its own tk variables so add/remove can re-render.
    target_rows: List[Dict[str, object]] = []
    for target in cfg.targets or []:
        target_rows.append({
            "name": target.name,
            "enabled": tk.BooleanVar(value=target.enabled),
            "local": tk.StringVar(value=target.local_dir),
            "repo": tk.StringVar(value=target.repo_dir),
        })

    output_queue: "queue.Queue[Optional[str]]" = queue.Queue()
    state = {"running": False}
    action_buttons: List[object] = []

    def browse_repo() -> None:
        path = filedialog.askdirectory(initialdir=str(config.expand(repo_var.get()).parent))
        if path:
            repo_var.set(path)

    def collect() -> Config:
        targets = [
            SkillTarget(str(row["name"]), str(row["local"].get()), str(row["repo"].get()), bool(row["enabled"].get()))
            for row in target_rows
        ]
        return Config(repo_var.get(), remote_var.get(), branch_var.get(), targets, cfg.backups_dir, cfg.excludes)

    def save() -> None:
        config.save_config(collect())
        messagebox.showinfo("Saved", f"Saved config:\n{config.current_config_path()}")

    def append(text: str) -> None:
        output.insert(tk.END, text)
        output.see(tk.END)

    def set_running(running: bool) -> None:
        state["running"] = running
        for button in action_buttons:
            try:
                button.config(state="disabled" if running else "normal")
            except Exception:  # pragma: no cover - defensive against widget teardown
                pass

    def poll_output() -> None:
        try:
            while True:
                item = output_queue.get_nowait()
                if item is None:
                    set_running(False)
                else:
                    append(item)
        except queue.Empty:
            pass
        root.after(100, poll_output)

    def worker(cmd: List[str]) -> None:
        try:
            proc = subprocess.Popen(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            assert proc.stdout is not None
            for line in proc.stdout:
                output_queue.put(line)
            proc.wait()
            output_queue.put(f"\n[exit code {proc.returncode}]\n")
        except Exception as exc:  # pragma: no cover - surfaced into the log pane
            output_queue.put(f"\n[error] {exc}\n")
        finally:
            output_queue.put(None)

    def run_action(action: str) -> None:
        if state["running"]:
            return
        dry_run = bool(dry_run_var.get())
        mirror = bool(mirror_var.get())
        if mirror and not dry_run and action in GUI_SYNC_ACTIONS:
            if not messagebox.askyesno("Mirror", f"Mirror {action} can delete files in the destination. Continue?"):
                return
        config.save_config(collect())
        cmd = gui_action_command(action, dry_run=dry_run, mirror=mirror)
        append(f"\n$ agent-skills {' '.join(cmd[3:])}\n")
        set_running(True)
        threading.Thread(target=worker, args=(cmd,), daemon=True).start()

    def render_targets() -> None:
        for child in targets_frame.winfo_children():
            child.destroy()
        for i, row in enumerate(target_rows):
            tk.Checkbutton(targets_frame, text=f"Enable {row['name']}", variable=row["enabled"]).grid(row=i, column=0, sticky="w", padx=8, pady=4)
            tk.Entry(targets_frame, textvariable=row["local"], width=40).grid(row=i, column=1, sticky="we", padx=8)
            tk.Entry(targets_frame, textvariable=row["repo"], width=20).grid(row=i, column=2, sticky="we", padx=8)
            tk.Button(targets_frame, text="Remove", command=lambda r=row: remove_target(r)).grid(row=i, column=3, padx=8)
        targets_frame.grid_columnconfigure(1, weight=1)

    def remove_target(row: Dict[str, object]) -> None:
        target_rows.remove(row)
        render_targets()

    def add_target() -> None:
        from tkinter import simpledialog
        name = simpledialog.askstring("Add target", "Target name (e.g. my-agent):")
        if not name:
            return
        target_rows.append({
            "name": name,
            "enabled": tk.BooleanVar(value=True),
            "local": tk.StringVar(value=f"~/.{name}/skills"),
            "repo": tk.StringVar(value=f"{name}-skills"),
        })
        render_targets()

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

    targets_frame = tk.Frame(root)
    targets_frame.grid(row=row, column=0, columnspan=3, sticky="we", padx=4)
    render_targets()
    row += 1

    options = tk.Frame(root)
    options.grid(row=row, column=0, columnspan=3, sticky="w", padx=8, pady=4)
    tk.Checkbutton(options, text="Dry run (preview only)", variable=dry_run_var).pack(side=tk.LEFT, padx=4)
    tk.Checkbutton(options, text="Mirror (delete extras)", variable=mirror_var).pack(side=tk.LEFT, padx=4)
    tk.Button(options, text="Add target", command=add_target).pack(side=tk.LEFT, padx=12)
    row += 1

    buttons = tk.Frame(root)
    buttons.grid(row=row, column=0, columnspan=3, sticky="w", padx=8, pady=8)
    tk.Button(buttons, text="Save", command=save).pack(side=tk.LEFT, padx=4)
    for action in ("scan", "status", "diff", "validate", "pull", "push"):
        button = tk.Button(buttons, text=action.capitalize(), command=lambda a=action: run_action(a))
        button.pack(side=tk.LEFT, padx=4)
        action_buttons.append(button)
    row += 1

    output = tk.Text(root, height=18)
    output.grid(row=row, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)
    root.grid_columnconfigure(1, weight=1)
    root.grid_rowconfigure(row, weight=1)
    output.insert(
        tk.END,
        "Edit settings, then run an action. Read-only actions (scan/status/diff/validate) "
        "never write files. Dry run previews push/pull; the GUI is experimental and the CLI "
        "has the full feature set.\n",
    )
    poll_output()
    root.mainloop()
