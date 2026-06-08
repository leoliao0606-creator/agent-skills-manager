"""Terminal interaction helpers: prompts, path completion, and colored output."""
from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path
from typing import List, Optional

from . import config
from .config import SkillTarget
from .fsutil import count_skills

try:
    import readline  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - readline is not available on some platforms.
    readline = None  # type: ignore[assignment]


# ----- Prompts -----

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


def confirm_destructive(args: argparse.Namespace, message: str) -> None:
    if getattr(args, "dry_run", False) or getattr(args, "yes", False):
        return
    if not yes(message, False):
        raise SystemExit("Cancelled.")


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
        found = count_skills(config.expand(target.local_dir))
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


# ----- Colored output -----

def ansi_enabled(args: argparse.Namespace) -> bool:
    mode = getattr(args, "color", "auto")
    if mode == "always":
        return True
    if mode == "never" or os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def color_text(text: str, color: str, args: argparse.Namespace) -> str:
    if not ansi_enabled(args):
        return text
    colors = {
        "green": "\033[32m",
        "yellow": "\033[33m",
        "red": "\033[31m",
        "cyan": "\033[36m",
        "blue": "\033[34m",
        "dim": "\033[2m",
        "bold": "\033[1m",
    }
    return f"{colors[color]}{text}\033[0m"


def status_color(status: str) -> str:
    if status == "configured":
        return "green"
    if status == "not configured":
        return "yellow"
    if status == "not exist":
        return "red"
    return "cyan"


def print_ascii_header(title: str, args: argparse.Namespace) -> None:
    if not getattr(args, "ascii_art", True):
        return
    line = f"| {title} |"
    border = "+" + "-" * (len(line) - 2) + "+"
    print(color_text(border, "cyan", args))
    print(color_text(line, "cyan", args))
    print(color_text(border, "cyan", args))
