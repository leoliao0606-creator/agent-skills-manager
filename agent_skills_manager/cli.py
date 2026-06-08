#!/usr/bin/env python3
"""Manage private AI agent skill repositories.

This module is the command-line entry point and a thin facade over the package
modules. It builds the argument parser, dispatches subcommands, and re-exports
the public names that scripts and tests rely on. The implementation lives in:

  config    settings, profiles, sync-state, skill-target model
  fsutil    skill discovery, hashing, ignore-pattern matching
  gitutil   git CLI wrappers and repo state
  sync      copy planning/application, repo safety, backups
  tui       prompts, path completion, colored output
  validate  skill structure/metadata/secret validation
  skills    list/search/show/open/new/export/import/restore commands
  commands  scan/status/push/pull/sync/diff/doctor/setup + config/target/profile
  gui       experimental Tkinter window

The tool intentionally uses only the Python standard library so it can run on a
fresh VPS or laptop without bootstrapping dependencies.
"""
from __future__ import annotations

import argparse
import sys
import textwrap
from typing import List, Optional

from . import config, fsutil, gitutil, sync, tui, validate, skills, commands, gui

# ----- Re-exported public API (kept stable for scripts and tests) -----
from .config import (  # noqa: F401
    APP_NAME,
    DEFAULT_REPO,
    DEFAULT_BACKUPS_DIR,
    DEFAULT_EXCLUDES,
    CONFIG_PATH,
    Config,
    SkillTarget,
    default_config_path,
    profile_dir,
    config_path_for_profile,
    current_config_path,
    state_path_for_profile,
    expand,
    has_skills,
    candidate_targets,
    default_targets,
    detect_default_repo,
    merge_candidate_targets,
    config_file_exists,
    load_config,
    save_config,
    slugify,
    load_sync_state,
    save_sync_state,
    enabled_targets,
    get_target,
)
from .fsutil import (  # noqa: F401
    count_skills,
    iter_skill_dirs,
    sha256_file,
    read_ignore_patterns,
    collect_file_hashes,
)
from .gitutil import (  # noqa: F401
    run,
    git_available,
    git_output,
    maybe_pull,
    repo_dirty,
    local_branch_exists,
    ensure_push_branch,
    collect_git_status,
)
from .sync import (  # noqa: F401
    build_copy_plan,
    plan_change_count,
    plan_write_count,
    print_plan,
    apply_copy_plan,
    copy_tree,
    serializable_plan,
    dangerous_repo_reasons,
    ensure_safe_repo_path,
    ensure_repo,
    target_source_destination,
    build_target_plan,
    maybe_confirm_mirror,
    create_backup,
)
from .tui import (  # noqa: F401
    read_answer,
    complete_path,
    read_path_answer,
    yes,
    confirm_destructive,
    parse_selection,
    read_multiselect,
    color_text,
    print_ascii_header,
)
from .validate import (  # noqa: F401
    parse_frontmatter,
    validate_skill_dir,
    scan_file_for_secrets,
    is_placeholder_secret,
    cmd_validate,
)
from .skills import (  # noqa: F401
    skill_records,
    resolve_skill_spec,
    skill_template,
    cmd_list,
    cmd_search,
    cmd_show,
    cmd_open,
    cmd_new,
    cmd_export,
    cmd_import,
    cmd_backups_list,
    cmd_restore_backup,
)
from .commands import (  # noqa: F401
    config_metadata,
    require_saved_config_for_write,
    collect_scan_targets,
    print_scan_records,
    cmd_scan,
    cmd_push,
    cmd_pull,
    cmd_sync,
    cmd_diff,
    cmd_plan,
    cmd_status,
    cmd_init_repo,
    cmd_doctor,
    cmd_setup,
    cmd_config_show,
    cmd_config_path,
    cmd_config_set,
    cmd_target_list,
    cmd_target_add,
    cmd_target_enable,
    cmd_target_disable,
    cmd_target_remove,
    cmd_profile_list,
    cmd_profile_create,
    cmd_profile_use,
    cmd_install_shell,
)
from .gui import cmd_gui, gui_action_command  # noqa: F401


# ----- Parser -----

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
    parser.add_argument(
        "--color",
        choices=["auto", "always", "never"],
        default="auto",
        help="colorize text output: auto for terminals, always to force ANSI, never to disable",
    )
    parser.add_argument("--no-ascii", dest="ascii_art", action="store_false", help="hide decorative ASCII headers")
    parser.set_defaults(examples=True, ascii_art=True)
    if include_status_flags:
        parser.add_argument("--no-git", action="store_true", help="hide git status/remotes and show only skill target output")
        parser.add_argument("--no-scan", action="store_true", help="hide skill target output and show only git status/remotes")


def add_sync_flags(parser: argparse.ArgumentParser, include_message: bool = False) -> None:
    parser.add_argument("--dry-run", action="store_true", help="preview file copies, commit, and push without writing files or modifying git state")
    parser.add_argument("--mirror", action="store_true", help="delete destination files that are not in source")
    parser.add_argument("--force", action="store_true", help="allow overwriting files reported as conflicts")
    parser.add_argument("--strict", action="store_true", help="fail instead of skipping missing source target directories")
    parser.add_argument("--yes", action="store_true", help="skip destructive confirmation prompts")
    if include_message:
        parser.add_argument("-m", "--message", default="Sync local agent skills")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent-skills",
        description="Scan installed AI agent skills and sync them with a private Git repository.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Typical workflow:
          agent-skills setup                    # hand-holding wizard
          agent-skills doctor                   # diagnose config/repo safety
          agent-skills diff --direction push    # preview changes
          agent-skills push --dry-run           # safe local -> repo preview
          agent-skills push                     # local skills -> repo -> git push
          agent-skills pull                     # git pull -> repo skills -> local
          agent-skills validate                 # validate skill files
        """),
    )
    p.add_argument("--profile", help="use a named config profile for this invocation")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup", help="interactive setup wizard").set_defaults(func=cmd_setup)

    scan = sub.add_parser("scan", help="scan configured skills by default; use filters to include disabled/missing targets")
    add_output_filter_args(scan)
    scan.set_defaults(func=cmd_scan)

    status = sub.add_parser("status", help="show git status and configured skill counts")
    add_output_filter_args(status, include_status_flags=True)
    status.set_defaults(func=cmd_status)

    diff = sub.add_parser("diff", help="preview file changes without copying anything")
    diff.add_argument("--direction", choices=["push", "pull"], default="push")
    diff.add_argument("--mirror", action="store_true")
    diff.add_argument("--format", choices=["text", "json"], default="text")
    diff.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    diff.add_argument("--no-ascii", dest="ascii_art", action="store_false")
    diff.set_defaults(func=cmd_diff, ascii_art=True)

    plan = sub.add_parser("plan", help="alias for diff; usage: agent-skills plan push|pull")
    plan.add_argument("plan_direction", choices=["push", "pull"])
    plan.add_argument("--direction", choices=["push", "pull"], default=None, help=argparse.SUPPRESS)
    plan.add_argument("--mirror", action="store_true")
    plan.add_argument("--format", choices=["text", "json"], default="text")
    plan.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    plan.add_argument("--no-ascii", dest="ascii_art", action="store_false")
    plan.set_defaults(func=cmd_plan, ascii_art=True)

    pull = sub.add_parser(
        "pull",
        help="sync repo skills into local installed skill dirs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          agent-skills pull --dry-run          # preview repo skills -> local installed skill directories
          agent-skills pull                   # apply repo skills -> local installed skill directories with backups
          agent-skills pull --mirror --yes    # make local match repo; may delete local-only files
        """),
    )
    add_sync_flags(pull)
    pull.add_argument("--no-pull", action="store_true", help="skip git pull --ff-only")
    pull.add_argument("--no-backup", dest="backup", action="store_false", help="do not back up local skill directories before writing")
    pull.set_defaults(func=cmd_pull, backup=True)

    push = sub.add_parser(
        "push",
        help="sync local installed skills into repo, commit, and push",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          agent-skills push --dry-run              # preview local -> repo without writing
          agent-skills push -m "Sync my skills"    # copy, commit, and push local skills
          agent-skills push --mirror --yes         # make repo match local; may delete repo-only files
        """),
    )
    add_sync_flags(push, include_message=True)
    push.add_argument("--no-pull", action="store_true", help="skip git pull --ff-only")
    push.add_argument("--allow-dirty", action="store_true", help="allow starting while repo already has uncommitted changes")
    push.add_argument("--create-repo", action="store_true", help="create repo if missing")
    push.set_defaults(func=cmd_push)

    sync_cmd = sub.add_parser(
        "sync",
        help="safe two-step sync: pull then push",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          agent-skills sync --dry-run          # preview the safe two-step flow
          agent-skills sync                   # pull repo -> local, then push local -> repo
          agent-skills sync -m "Sync skills"  # use a custom commit message for the push phase
        """),
    )
    add_sync_flags(sync_cmd, include_message=True)
    sync_cmd.add_argument("--no-pull", action="store_true", help="skip git pull --ff-only before pull phase")
    sync_cmd.add_argument("--no-backup", action="store_true", help="do not back up local skill directories before pull phase")
    sync_cmd.add_argument("--allow-dirty", action="store_true")
    sync_cmd.add_argument("--create-repo", action="store_true")
    sync_cmd.set_defaults(func=cmd_sync)

    init_repo = sub.add_parser("init-repo", help="create the local private skills repo skeleton")
    init_repo.add_argument("--repo")
    init_repo.add_argument("--remote", default=None)
    init_repo.set_defaults(func=cmd_init_repo)

    doctor = sub.add_parser("doctor", help="diagnose config, git, path, and target safety")
    doctor.add_argument("--format", choices=["text", "json"], default="text")
    doctor.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    doctor.add_argument("--no-ascii", dest="ascii_art", action="store_false")
    doctor.set_defaults(func=cmd_doctor, ascii_art=True)

    validate_cmd = sub.add_parser("validate", help="validate skill structure, metadata, duplicates, and possible secrets")
    validate_cmd.add_argument("--location", choices=["local", "repo"], default="local")
    validate_cmd.add_argument("--target")
    validate_cmd.add_argument("--format", choices=["text", "json"], default="text")
    validate_cmd.set_defaults(func=cmd_validate)

    config_cmd = sub.add_parser("config", help="scriptable configuration management")
    config_sub = config_cmd.add_subparsers(dest="config_cmd", required=True)
    config_show = config_sub.add_parser("show")
    config_show.add_argument("--format", choices=["text", "json"], default="text")
    config_show.set_defaults(func=cmd_config_show)
    config_sub.add_parser("path").set_defaults(func=cmd_config_path)
    config_set = config_sub.add_parser("set")
    config_set.add_argument("key")
    config_set.add_argument("value")
    config_set.set_defaults(func=cmd_config_set)

    target = sub.add_parser("target", help="scriptable skill target management")
    target_sub = target.add_subparsers(dest="target_cmd", required=True)
    target_list = target_sub.add_parser("list")
    target_list.add_argument("--format", choices=["text", "json"], default="text")
    target_list.set_defaults(func=cmd_target_list)
    target_add = target_sub.add_parser("add")
    target_add.add_argument("name")
    target_add.add_argument("--local", required=True)
    target_add.add_argument("--repo", required=True)
    target_add.add_argument("--disabled", action="store_true")
    target_add.set_defaults(func=cmd_target_add)
    for name, func in [("enable", cmd_target_enable), ("disable", cmd_target_disable), ("remove", cmd_target_remove)]:
        sp = target_sub.add_parser(name)
        sp.add_argument("name")
        sp.set_defaults(func=func)

    profile = sub.add_parser("profile", help="manage named config profiles")
    profile_sub = profile.add_subparsers(dest="profile_cmd", required=True)
    profile_sub.add_parser("list").set_defaults(func=cmd_profile_list)
    profile_create = profile_sub.add_parser("create")
    profile_create.add_argument("name")
    profile_create.set_defaults(func=cmd_profile_create)
    profile_use = profile_sub.add_parser("use")
    profile_use.add_argument("name")
    profile_use.set_defaults(func=cmd_profile_use)

    list_cmd = sub.add_parser("list", help="list skills")
    list_cmd.add_argument("--location", choices=["local", "repo"], default="local")
    list_cmd.add_argument("--target")
    list_cmd.add_argument("--format", choices=["text", "json", "names"], default="text")
    list_cmd.set_defaults(func=cmd_list)

    search = sub.add_parser("search", help="search skill names and SKILL.md contents")
    search.add_argument("query")
    search.add_argument("--location", choices=["local", "repo"], default="local")
    search.add_argument("--target")
    search.add_argument("--format", choices=["text", "json", "names"], default="text")
    search.set_defaults(func=cmd_search)

    show = sub.add_parser("show", help="print one skill's SKILL.md")
    show.add_argument("spec", help="skill name or target:skill")
    show.add_argument("--repo", action="store_true", help="read from repository copy instead of local target")
    show.set_defaults(func=cmd_show)

    open_cmd = sub.add_parser("open", help="open or print one skill directory")
    open_cmd.add_argument("spec", help="skill name or target:skill")
    open_cmd.add_argument("--repo", action="store_true")
    open_cmd.add_argument("--print", dest="print_only", action="store_true", help="print path without launching a desktop opener")
    open_cmd.set_defaults(func=cmd_open)

    new = sub.add_parser(
        "new",
        help="create a new skill skeleton",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          agent-skills new "Docker Management" --target claude
          agent-skills new "Work Skill" --target my-agent --repo
        """),
    )
    new.add_argument("name", help="human-readable skill name; converted to a lowercase directory slug")
    new.add_argument("--target", required=True, help="configured target name such as claude, hermes, or a custom target")
    new.add_argument("--repo", action="store_true", help="create the skill under the repository target instead of the installed local agent target")
    new.add_argument("--force", action="store_true", help="overwrite an existing skill directory if it already exists")
    new.set_defaults(func=cmd_new)

    export = sub.add_parser("export", help="export a target's skills as a zip archive")
    export.add_argument("--target", required=True)
    export.add_argument("--output")
    export.add_argument("--repo", action="store_true")
    export.set_defaults(func=cmd_export)

    import_cmd = sub.add_parser("import", help="import a directory or zip into a target")
    import_cmd.add_argument("path")
    import_cmd.add_argument("--target", required=True)
    import_cmd.add_argument("--repo", action="store_true")
    add_sync_flags(import_cmd)
    import_cmd.set_defaults(func=cmd_import)

    backups = sub.add_parser("backups", help="list backups")
    backups_sub = backups.add_subparsers(dest="backups_cmd", required=True)
    backups_sub.add_parser("list").set_defaults(func=cmd_backups_list)

    restore = sub.add_parser("restore-backup", help="restore a backup directory into a local target")
    restore.add_argument("path")
    restore.add_argument("--target", required=True)
    restore.add_argument("--dry-run", action="store_true")
    restore.add_argument("--mirror", action="store_true", default=True)
    restore.add_argument("--yes", action="store_true")
    restore.set_defaults(func=cmd_restore_backup)

    sub.add_parser("gui", help="open experimental graphical settings and sync window").set_defaults(func=cmd_gui)
    install = sub.add_parser("install-shell", help="install POSIX shell wrapper commands into ~/bin (fallback for source checkouts)")
    install.add_argument("--bindir", default="~/bin")
    install.set_defaults(func=cmd_install_shell)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    previous_profile = config.ACTIVE_PROFILE
    try:
        args = build_parser().parse_args(argv)
        config.ACTIVE_PROFILE = getattr(args, "profile", None)
        args.func(args)
        return 0
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except EOFError:
        print("\nNo input received; cancelled.", file=sys.stderr)
        return 130
    finally:
        config.ACTIVE_PROFILE = previous_profile


if __name__ == "__main__":
    sys.exit(main())
