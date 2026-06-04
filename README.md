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
git clone https://github.com/<your-user-or-org>/agent-skills-manager.git
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
git clone https://github.com/<your-user-or-org>/agent-skills-manager.git
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

The wizard asks for:

- Local checkout path for the private skills repository. The default is the generic `~/agent-skills-library`.
- Git remote URL, such as `git@github.com:username/private-agent-skills.git` or an HTTPS URL. This can be left empty for local-only use.
- Default branch, usually `main`.
- Terminal multi-select checklist for which agents to sync.
- Local skill directories to scan.
- Repository subdirectories where each skill target should be stored.
- Whether to clone, initialize, or create the local repository.
- Whether to do the initial sync.

Path prompts support Tab completion on terminals where Python `readline` is available. If `readline` is unavailable, setup falls back to normal text input.

Recommended first commands:

```bash
agent-skills doctor
agent-skills scan
agent-skills diff --direction push
agent-skills push --dry-run
agent-skills push
```

Configuration is stored in an OS-specific per-user config file:

```text
Windows: %APPDATA%\agent-skills-manager\config.json
macOS:   ~/Library/Application Support/agent-skills-manager/config.json
Linux:   ~/.config/agent-skills-manager/config.json
```

You can override the config path with:

```bash
AGENT_SKILLS_CONFIG=/path/to/config.json agent-skills scan
```

PowerShell:

```powershell
$env:AGENT_SKILLS_CONFIG="C:\path\to\config.json"
agent-skills scan
```

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

Default ignored files and directories include `.git/`, `.env`, virtualenvs, Python caches, `.DS_Store`, and `node_modules/`. You can add a `.agent-skills-ignore` file to a source or destination root, or configure global patterns with:

```bash
agent-skills config set excludes ".git/,.env,__pycache__/,*.pyc,node_modules/"
```

## Common commands

### Diagnose configuration

```bash
agent-skills doctor
agent-skills doctor --format json
```

`doctor` checks Git availability, config presence, repository safety, repo initialization, remotes, dirty state, and configured target directories.

### Scan local and repository skills

```bash
agent-skills scan
```

By default, `scan` prints only configured targets. A configured target is an agent skills directory selected for sync during setup. Use filters when you want more or less detail:

```bash
agent-skills scan --all
agent-skills scan --only configured
agent-skills scan --only not-configured
agent-skills scan --only missing
agent-skills scan --only existing
agent-skills scan --no-examples
agent-skills scan --limit 1
agent-skills scan --format names
agent-skills scan --format json
agent-skills scan --color always
agent-skills scan --color never
agent-skills scan --no-ascii
```

Target status labels:

```text
configured      local skill directory exists and is selected for sync
not configured  local skill directory exists but is not selected for sync
not exist       local skill directory is missing
```

For `not exist`, text output prints only the status line and skips local/repo details because there is no local skill directory to inspect.

### Show status

```bash
agent-skills status
agent-skills status --format json
agent-skills status --no-git
agent-skills status --no-scan
```

`status` shows Git status/remotes and the same skill target summary used by `scan`.

### Preview changes

```bash
agent-skills diff --direction push
agent-skills diff --direction pull
agent-skills diff --direction push --mirror
agent-skills diff --direction push --format json

agent-skills plan push
agent-skills plan pull
```

`diff` and `plan` report:

- `add`: source file does not exist in destination.
- `update`: source and destination differ.
- `delete`: destination-only file that would be removed by `--mirror`.
- `conflict`: both sides appear to have changed since the last sync state.

### Initialize a local skills repository skeleton

```bash
agent-skills init-repo
agent-skills init-repo --repo ~/agent-skills-library --remote git@github.com:username/private-agent-skills.git
```

`init-repo` creates a Git repo, target directories, README, `.gitignore`, and `.agent-skills-ignore`.

### Push local skills to the repository

```bash
agent-skills push --dry-run
agent-skills push
agent-skills push -m "Sync my skills"
agent-skills push --mirror --yes
```

Useful flags:

```text
--dry-run       preview without copying, committing, or pushing
--mirror        delete destination-only files
--force         allow overwriting files reported as conflicts
--strict        fail instead of skipping missing source targets
--yes           skip destructive mirror confirmation prompts
--no-pull       skip git pull --ff-only before pushing
--allow-dirty   allow starting while the repo already has uncommitted changes
--create-repo   create the repo if missing
```

`push --dry-run` is allowed even when the repo is dirty; it prints a warning and does not write.

### Pull repository skills into local skill directories

```bash
agent-skills pull --dry-run
agent-skills pull
agent-skills pull --mirror --yes
agent-skills pull --no-backup
```

By default, `pull` backs up each local target directory before writing if that target has planned changes.

### Sync both directions

```bash
agent-skills sync --dry-run
agent-skills sync
agent-skills sync -m "Sync skills"
```

`sync` runs a safe two-step flow:

1. repo -> local (`pull` phase)
2. local -> repo (`push` phase)

It uses the same dry-run, mirror, strict, force, backup, and dirty-repo flags as `pull` and `push`.

## Config, targets, and profiles

### Scriptable config

```bash
agent-skills config path
agent-skills config show
agent-skills config show --format json
agent-skills config set repo_dir ~/agent-skills-library
agent-skills config set remote_url git@github.com:username/private-agent-skills.git
agent-skills config set default_branch main
agent-skills config set backups_dir ~/.agent-skills-manager/backups
agent-skills config set excludes ".git/,.env,__pycache__/"
```

### Scriptable target management

```bash
agent-skills target list
agent-skills target list --format json
agent-skills target add my-agent --local ~/.my-agent/skills --repo my-agent-skills
agent-skills target add work-agent --local ~/work/skills --repo work-skills --disabled
agent-skills target enable my-agent
agent-skills target disable my-agent
agent-skills target remove my-agent
```

### Profiles

Profiles are separate config files for separate skill setups, such as personal, work, public, and experimental libraries.

```bash
agent-skills profile list
agent-skills profile create work
agent-skills profile use work
agent-skills --profile work scan
agent-skills --profile work push --dry-run
```

`profile use NAME` copies a named profile into the default active config. `--profile NAME` uses that profile only for the current invocation.

## Browsing and authoring skills

### List, search, show, and open

```bash
agent-skills list
agent-skills list --format names
agent-skills list --location repo
agent-skills search docker
agent-skills search docker --format json
agent-skills show claude:docker-management
agent-skills show hermes:software-development/test-driven-development
agent-skills open claude:docker-management --print
```

Skill specs use `target:skill-path`. If a skill name is unique, the target prefix can be omitted.

### Create a new skill skeleton

```bash
agent-skills new "Docker Management" --target claude
agent-skills new "Work Skill" --target my-agent --repo
```

This creates:

```text
skill-name/
  SKILL.md
  references/
  scripts/
  templates/
```

### Validate skills

```bash
agent-skills validate
agent-skills validate --target claude
agent-skills validate --location repo
agent-skills validate --format json
```

Validation checks:

- each skill has a non-empty `SKILL.md`;
- `SKILL.md` has frontmatter;
- frontmatter includes `name` and `description`;
- skill names are not duplicated in the selected validation scope;
- small text files do not contain obvious private keys or token-like secrets.

### Import and export

```bash
agent-skills export --target claude --output claude-skills.zip
agent-skills export --target hermes --repo --output hermes-repo-skills.zip
agent-skills import ./claude-skills.zip --target claude
agent-skills import ./some-skill-directory --target hermes
agent-skills import ./skills.zip --target claude --dry-run
```

`import` accepts either a directory or a zip file and uses the same safe additive/mirror behavior as sync operations.

## Backups and restore

List backups:

```bash
agent-skills backups list
```

Restore a backup target directory:

```bash
agent-skills restore-backup ~/.agent-skills-manager/backups/20260604-120000/claude --target claude --dry-run
agent-skills restore-backup ~/.agent-skills-manager/backups/20260604-120000/claude --target claude --yes
```

`restore-backup` mirrors the backup directory into the selected local target by default.

## Safe sync vs mirror sync

By default, sync is additive and update-only:

- New files are copied.
- Changed files are updated.
- Extra files already present in the destination are not deleted.

To make the destination exactly match the source, use `--mirror`:

```bash
agent-skills push --mirror --yes
agent-skills pull --mirror --yes
```

Use `--mirror` carefully because it can delete files from the destination. Omit `--yes` if you want an interactive confirmation prompt.

## Recommended repository layout

A private skills repository can use this layout:

```text
private-agent-skills/
  README.md
  .agent-skills-ignore
  claude-skills/
    some-skill/
      SKILL.md
  codex-skills/
    some-skill/
      SKILL.md
  hermes-skills/
    software-development/
      some-skill/
        SKILL.md
```

The names are configurable. For example, a user could map a custom agent to:

```text
custom-agent-skills/
```

## GUI

Run:

```bash
agent-skills gui
```

The GUI is experimental and intentionally secondary to the CLI. It can configure common settings and run basic scan/pull/push actions, but the CLI has the full feature set.

Tkinter is included with many Python installers, but not all minimal Linux distributions include it by default. If the GUI is unavailable, use the CLI commands instead.

## Cross-platform notes

### Windows

- Prefer PowerShell or Windows Terminal.
- Install Git for Windows first.
- SSH remotes work if GitHub SSH keys are configured.
- HTTPS remotes work with Git Credential Manager.
- Paths such as `~/.claude/skills` are expanded through Python's user home handling.

### macOS

- Install Git through Xcode Command Line Tools or Homebrew.
- The default config file lives under `~/Library/Application Support`.
- SSH and HTTPS Git remotes are both supported.

### Linux

- Install Git through your distribution package manager.
- The default config file follows `XDG_CONFIG_HOME` when set, otherwise `~/.config`.
- `install-shell` is a POSIX fallback for source checkouts, but venv/pip entry points are the recommended install path.

## Publishing a new private skills repository

Create an empty repository on GitHub, GitLab, Gitea, or another Git host. Do not add an initial README if you already initialized the local repository.

Then run:

```bash
agent-skills setup
agent-skills doctor
agent-skills push --dry-run
agent-skills push
```

Or configure manually:

```bash
agent-skills config set repo_dir ~/agent-skills-library
agent-skills config set remote_url git@github.com:username/private-agent-skills.git
agent-skills config set default_branch main
agent-skills target enable claude
agent-skills init-repo
agent-skills push --dry-run
agent-skills push
```

## Development

Run from source:

```bash
python -m agent_skills_manager.cli --help
python -m agent_skills_manager.cli doctor
python -m agent_skills_manager.cli scan
python -m agent_skills_manager.cli diff --direction push
python -m agent_skills_manager.cli push --dry-run
python -m agent_skills_manager.cli pull --dry-run
```

Run tests:

```bash
python -m py_compile agent_skills_manager/cli.py
python -m unittest discover -v
```
