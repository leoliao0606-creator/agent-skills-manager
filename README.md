# Agent Skills Manager

Agent Skills Manager is a cross-platform CLI, with an optional experimental GUI, for managing private AI agent skill libraries.

It scans locally installed skills, maps them to a Git repository, and gives users safe commands to back up, validate, preview, restore, and sync skills across machines.

Supported platforms:

- Windows
- macOS
- Linux

Runtime requirements:

- Python 3.9+
- Git
- Tkinter only if you want to use the optional experimental GUI

No third-party Python package is required by the application itself.

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
- Provides an experimental Tkinter settings window with `agent-skills gui`.

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

### macOS / Linux

Use a virtual environment. This works consistently across machines and avoids modifying the system Python installation.

```bash
git clone https://github.com/leoliao0606-creator/agent-skills-manager.git
cd agent-skills-manager
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
agent-skills --help
```

If the `agent-skills` command is not found after installation, use the module form:

```bash
python -m agent_skills_manager.cli --help
```

On Debian/Ubuntu systems that enforce PEP 668, avoid installing directly into the system Python. Use the virtual environment commands above.

### Windows PowerShell

Use a virtual environment. This avoids modifying the system Python installation.

```powershell
git clone https://github.com/leoliao0606-creator/agent-skills-manager.git
cd agent-skills-manager
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
agent-skills --help
```

If the `agent-skills` command is not found after installation, use the module form:

```powershell
py -m agent_skills_manager.cli --help
```

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

## Documentation

- [Command reference](docs/commands.md) — every subcommand, flags, and output formats (scan, status, diff, push, pull, sync, list/search/show, new, validate, import/export, backups).
- [Configuration, targets, and profiles](docs/configuration.md) — config file, scriptable config/target commands, profiles, excludes, and the recommended repository layout.
- [Platforms, GUI, and publishing](docs/platforms.md) — Windows/macOS/Linux notes, the experimental GUI, and publishing a new private skills repository.

## Development

Run from source after activating the virtual environment from the install section:

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
