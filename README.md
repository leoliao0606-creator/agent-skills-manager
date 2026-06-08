# Agent Skills Manager

Agent Skills Manager is a cross-platform CLI, with an optional Qt desktop GUI, for managing private AI agent skill libraries.

It scans locally installed skills, maps them to a Git repository, and gives users safe commands to back up, validate, preview, restore, and sync skills across machines.

Supported platforms:

- Windows
- macOS
- Linux

Runtime requirements:

- Python 3.9+
- Git
- PySide6 only if you want to use the optional Qt desktop GUI (`pip install "agent-skills-manager[qt]"`)

No third-party Python package is required by the CLI itself.

## What it does

- Scans installed AI agent skill directories.
- Provides an interactive setup wizard for a private skills repository.
- Supports multiple configurable skill targets.
- Safely previews sync changes before copying files.
- Syncs local skills to a Git repository with `push`.
- Syncs repository skills back to the local machine with `pull`.
- Supports two-step pull-then-push sync with `sync`.
- Uses additive sync by default; mirror deletion requires explicit `--mirror`.
- Detects likely conflicts using a local sync-state file.
- Backs up local skill directories before `pull` writes by default.
- Validates skill structure, metadata, duplicate names, and possible secrets.
- Provides scriptable config, target, and profile commands.
- Lists, searches, shows, creates, imports, and exports skills.
- Provides an optional Qt desktop GUI with `agent-skills gui`.

The setup wizard presents a terminal multi-select checklist of common agent skill locations:

```text
Claude Code:  ~/.claude/skills              ->  claude-skills/
Codex:        ~/.codex/skills               ->  codex-skills/
Gemini:       ~/.gemini/skills              ->  gemini-skills/
Cursor:       ~/.cursor/skills              ->  cursor-skills/
Windsurf:     ~/.windsurf/skills            ->  windsurf-skills/
OpenCode:     ~/.config/opencode/skills     ->  opencode-skills/
Goose:        ~/.config/goose/skills        ->  goose-skills/
Aider:        ~/.aider/skills               ->  aider-skills/
Continue:     ~/.continue/skills            ->  continue-skills/
Hermes Agent: ~/.hermes/skills              ->  hermes-skills/
```

Detected skill directories are pre-selected. Users can enable or disable any target and change every path during setup, so the tool also works with custom agents or custom skill layouts.

## Install

The application has **no third-party Python dependencies**, so it runs anywhere Python 3.9+ and Git are available. Pick whichever method fits how you like to install tools — they all give you the same `agent-skills` CLI.

All methods start from a clone:

```bash
git clone https://github.com/leoliao0606-creator/agent-skills-manager.git
cd agent-skills-manager
```

| Method | Best when | Notes |
|---|---|---|
| [Run from source, no install](#option-a-run-from-source-no-install) | You want zero setup or to try it once | No `pip` at all; you type `python3 -m agent_skills_manager.cli` |
| [pipx](#option-b-pipx) | You want a global `agent-skills` command, isolated | pipx manages the virtual environment for you |
| [pip --user](#option-c-pip-install---user) | You want it on your `PATH` without a venv | Installs into your per-user site directory |
| [Virtual environment](#option-d-virtual-environment) | You want full isolation and control | The most portable, reproducible option |
| [System pip](#option-e-system-pip) | You knowingly manage your own environment | May be blocked by PEP 668; not recommended |

> **Optional Qt GUI:** the CLI needs no third-party packages, but the desktop GUI does. To install it, add the `[qt]` extra to any pip-based method above — for example `pip install -e ".[qt]"` or `pipx install ".[qt]"`. See [Optional Qt GUI](#optional-qt-gui) below.

### Option A: Run from source, no install

Because the runtime is standard-library only, you don't have to install anything. From the cloned directory:

```bash
python3 -m agent_skills_manager.cli --help
```

On Windows use `py` instead of `python3`. Every command in this README that starts with `agent-skills` also works as `python3 -m agent_skills_manager.cli`. To make it shorter, add an alias:

```bash
alias agent-skills='python3 -m agent_skills_manager.cli'
```

### Option B: pipx

[pipx](https://pipx.pypa.io/) installs the CLI into its own isolated environment and puts `agent-skills` on your `PATH`, without you managing a venv:

```bash
pipx install .
agent-skills --help
```

To update after pulling new commits: `pipx install --force .`

### Option C: pip install --user

Installs into your per-user site directory, so it lands on your `PATH` without a venv and without touching system files:

```bash
python3 -m pip install --user .
agent-skills --help
```

If `agent-skills` is not found afterward, your user scripts directory is not on `PATH`. Use the module form `python3 -m agent_skills_manager.cli`, or add the directory printed by `python3 -m site --user-base` (its `bin` on macOS/Linux, `Scripts` on Windows) to your `PATH`.

On Debian/Ubuntu systems that enforce PEP 668, `--user` may be blocked; use pipx or a virtual environment instead.

### Option D: Virtual environment

The most portable and reproducible option. It works consistently across machines and never modifies the system Python.

macOS / Linux:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
agent-skills --help
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
agent-skills --help
```

The `-e` (editable) install means changes you pull or make to the source take effect without reinstalling.

### Option E: System pip

If you knowingly manage your own Python environment, you can install into it directly:

```bash
python3 -m pip install .
```

This is not recommended: many systems (Debian/Ubuntu, Homebrew Python) enforce PEP 668 and will reject it to protect the system Python. Prefer pipx, `--user`, or a virtual environment. If you understand the risk, `--break-system-packages` overrides the block.

### If the `agent-skills` command is not found

This only means the install location isn't on your `PATH`. The module form always works from the cloned directory, regardless of install method:

```bash
python3 -m agent_skills_manager.cli --help
```

On Windows, use `py -m agent_skills_manager.cli --help`.

## Quick start

Run the setup wizard:

```bash
agent-skills setup
```

If no config file exists yet, read-only commands such as `doctor`, `scan`, and `diff` can show implicit defaults so you can preview the tool. Real `push`, `pull`, and `sync` operations require a saved config; run `agent-skills setup` first.

## 3-minute local-only demo

This demo uses only temporary directories. It does not touch your real `~/.claude/skills`, `~/.hermes/skills`, or any remote Git repository.

macOS / Linux:

```bash
DEMO_DIR="${TMPDIR:-/tmp}/agent-skills-demo"
mkdir -p "$DEMO_DIR/local/demo-skill"
cat > "$DEMO_DIR/local/demo-skill/SKILL.md" <<'EOF'
---
name: demo-skill
description: Demo skill for Agent Skills Manager.
---

# Demo Skill

A tiny skill used to test the local-only workflow.
EOF

AGENT_SKILLS_CONFIG="$DEMO_DIR/config.json" agent-skills config set repo_dir "$DEMO_DIR/repo"
AGENT_SKILLS_CONFIG="$DEMO_DIR/config.json" agent-skills target disable claude
AGENT_SKILLS_CONFIG="$DEMO_DIR/config.json" agent-skills target disable hermes
AGENT_SKILLS_CONFIG="$DEMO_DIR/config.json" agent-skills target add demo --local "$DEMO_DIR/local" --repo demo-skills
AGENT_SKILLS_CONFIG="$DEMO_DIR/config.json" agent-skills init-repo
AGENT_SKILLS_CONFIG="$DEMO_DIR/config.json" agent-skills scan
AGENT_SKILLS_CONFIG="$DEMO_DIR/config.json" agent-skills diff --direction push
AGENT_SKILLS_CONFIG="$DEMO_DIR/config.json" agent-skills push --dry-run
```

PowerShell:

```powershell
$demo = Join-Path $env:TEMP "agent-skills-demo"
New-Item -ItemType Directory -Force -Path "$demo\local\demo-skill" | Out-Null
@"
---
name: demo-skill
description: Demo skill for Agent Skills Manager.
---

# Demo Skill

A tiny skill used to test the local-only workflow.
"@ | Set-Content -Encoding UTF8 "$demo\local\demo-skill\SKILL.md"

$env:AGENT_SKILLS_CONFIG = "$demo\config.json"
agent-skills config set repo_dir "$demo\repo"
agent-skills target disable claude
agent-skills target disable hermes
agent-skills target add demo --local "$demo\local" --repo demo-skills
agent-skills init-repo
agent-skills scan
agent-skills diff --direction push
agent-skills push --dry-run
```

## Which command should I use?

| I want to... | Run |
|---|---|
| First-time setup | `agent-skills setup` |
| Check whether config and paths are safe | `agent-skills doctor` |
| See detected configured skills | `agent-skills scan` |
| Preview local skills -> repository | `agent-skills diff --direction push` |
| Back up local skills to the repository | `agent-skills push --dry-run`, then `agent-skills push` |
| Restore repository skills to this machine | `agent-skills pull --dry-run`, then `agent-skills pull` |
| Keep both sides updated | `agent-skills sync --dry-run`, then `agent-skills sync` |
| Create a new skill skeleton | `agent-skills new "Name" --target claude` |
| Validate skill files | `agent-skills validate` |

The setup wizard asks for the local checkout path (default `~/agent-skills-library`), a Git remote URL (optional; empty for local-only use), the default branch, which agents to sync, and the local/repository directories for each target. Path prompts support Tab completion where Python `readline` is available.

Configuration is stored in an OS-specific per-user config file and can be overridden with the `AGENT_SKILLS_CONFIG` environment variable. See [docs/configuration.md](docs/configuration.md) for details.

## Safety model

Agent Skills Manager is conservative by default:

- `push` and `pull` are additive/update-only by default.
- Extra files in the destination are not deleted unless you pass `--mirror`.
- `pull` writes into real local agent skill directories, so it creates a backup before writing by default.
- `push --dry-run` and `pull --dry-run` preview changes without writing files.
- `diff` and `plan` show add/update/delete/conflict actions without writing files.
- `--mirror` can delete files; destructive runs prompt unless `--yes` is passed.
- Dangerous repository paths such as `/`, `~`, or an existing non-empty non-git directory are rejected.
- Missing target source directories are skipped by default and fail with `--strict`.
- Likely conflicts are detected using a local sync-state file and require `--force` after review.

Default ignored patterns and `.agent-skills-ignore` support are documented in [docs/configuration.md](docs/configuration.md#excludes-and-ignore-files).

## Optional Qt GUI

Agent Skills Manager includes an optional PySide6 desktop GUI for people who prefer a visual workflow. The CLI stays the primary, dependency-free interface; the GUI is optional and reuses the exact same configuration and sync logic — it never reimplements business rules.

Install the `[qt]` extra and launch it:

```bash
python3 -m pip install "agent-skills-manager[qt]"   # or, from a clone: pip install -e ".[qt]"
agent-skills gui
```

The window has eight pages in a left-hand nav — Overview, Targets, Sync, Diff, Validate, Backups, Settings, and Logs. It keeps the CLI's safety model: previews are read-only, dry-run is on by default, deleting a target never deletes files, and mirror/force/restore require confirmation. If PySide6 is not installed, `agent-skills gui` prints an install hint and points you back to the CLI commands instead.

See [docs/platforms.md](docs/platforms.md#optional-qt-gui) for a per-page tour.

## Documentation

- [Command reference](docs/commands.md) — every subcommand, flags, and output formats (scan, status, diff, push, pull, sync, list/search/show, new, validate, import/export, backups).
- [Configuration, targets, and profiles](docs/configuration.md) — config file, scriptable config/target commands, profiles, excludes, and the recommended repository layout.
- [Platforms, GUI, and publishing](docs/platforms.md) — Windows/macOS/Linux notes, the optional Qt GUI, and publishing a new private skills repository.

## Development

Run from source after activating the virtual environment from [Option D](#option-d-virtual-environment):

```bash
python -m agent_skills_manager.cli --help
python -m agent_skills_manager.cli doctor
python -m agent_skills_manager.cli scan
```

If you have not activated a virtual environment, use the platform launcher directly:

```bash
python3 -m agent_skills_manager.cli --help
python3 -m agent_skills_manager.cli doctor
```

Install the contributor tooling (test runner and linter) and run the checks:

```bash
python3 -m pip install -e ".[dev]"
pytest
ruff check .
```

The test suite also runs with the standard library alone:

```bash
python3 -m unittest discover -v
```
