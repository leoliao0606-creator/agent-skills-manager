# Agent Skills Manager

Agent Skills Manager is a cross-platform CLI and optional GUI for managing private AI agent skill libraries.

It scans locally installed skills, maps them to a Git repository, and gives users simple commands to back up, restore, and sync their skills across machines.

Supported platforms:

- Windows
- macOS
- Linux

Runtime requirements:

- Python 3.9+
- Git
- pipx is recommended for installing the command-line app on Linux/macOS
- Tkinter only if you want to use the optional GUI

No third-party Python package is required by the application itself.

## What it does

- Scans installed AI agent skill directories.
- Provides an interactive setup wizard for a private skills repository.
- Supports multiple skill targets, enabled or disabled independently.
- Syncs local skills to a Git repository with `push`.
- Syncs repository skills back to the local machine with `pull`.
- Supports safe additive sync by default.
- Supports exact mirror sync with `--mirror` when users explicitly want deletion.
- Provides a graphical settings window with `agent-skills gui`.

Default skill targets:

```text
Claude Code:  ~/.claude/skills  ->  agent-skills/
Hermes Agent: ~/.hermes/skills   ->  hermes-skills/
```

The setup wizard lets users change all paths, so the tool can work with other agents or custom skill layouts too.

## Install

### macOS / Linux

```bash
git clone https://github.com/<your-user-or-org>/agent-skills-manager.git
cd agent-skills-manager
pipx install -e .
agent-skills --help
```

If `agent-skills` is installed but not found, add pipx's app directory to your PATH:

```bash
pipx ensurepath
```

Then restart your shell, or run the app directly from the user bin directory:

```bash
~/.local/bin/agent-skills --help
```

On Debian/Ubuntu systems that enforce PEP 668, `python3 -m pip install -e .` may fail with `externally-managed-environment`. That is expected. Prefer `pipx install -e .` for CLI usage, or use a virtual environment for development:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
agent-skills --help
```

### Windows PowerShell

```powershell
git clone https://github.com/<your-user-or-org>/agent-skills-manager.git
cd agent-skills-manager
py -m pip install -e .
agent-skills --help
```

For an isolated app-style install on Windows, pipx is also a good option:

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
pipx install -e .
agent-skills --help
```

If the `agent-skills` command is not found after installation, use the module form:

```bash
python -m agent_skills_manager.cli --help
```

On Windows:

```powershell
py -m agent_skills_manager.cli --help
```

## Quick start

Run the setup wizard:

```bash
agent-skills setup
```

The wizard asks for:

- Local checkout path for the private skills repository.
- Git remote URL, such as `git@github.com:username/private-agent-skills.git` or an HTTPS URL.
- Default branch, usually `main`.
- Local skill directories to scan.
- Repository subdirectories where each skill target should be stored.
- Whether to clone, initialize, or create the local repository.
- Whether to do the initial sync.

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

## Common commands

Scan local and repository skills:

```bash
agent-skills scan
```

Show Git status and skill counts:

```bash
agent-skills status
```

Initialize a local skills repository skeleton:

```bash
agent-skills init-repo
```

Sync local installed skills into the repository, commit, and push:

```bash
agent-skills push
agent-skills push -m "Sync my skills"
agent-skills push --dry-run
```

Sync repository skills into local installed skill directories:

```bash
agent-skills pull
agent-skills pull --dry-run
```

Open the GUI:

```bash
agent-skills gui
```

## Safe sync vs mirror sync

By default, sync is additive and update-only:

- New files are copied.
- Changed files are updated.
- Extra files already present in the destination are not deleted.

This is the safest default for users with local-only skills or multiple machines.

To make the destination exactly match the source, use `--mirror`:

```bash
agent-skills push --mirror
agent-skills pull --mirror
```

Use `--mirror` carefully because it can delete files from the destination.

## Recommended repository layout

A private skills repository can use this layout:

```text
private-agent-skills/
  README.md
  agent-skills/
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

The GUI lets users configure:

- Local repository path
- Git remote URL
- Branch
- Enabled skill targets
- Local skill directories
- Repository subdirectories
- Scan / Pull / Push actions

Tkinter is included with many Python installers, but not all minimal Linux distributions include it by default. If the GUI is unavailable, the CLI provides the same core functionality.

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
- The optional `install-shell` command can create POSIX wrapper commands in a directory such as `~/bin`.

## Publishing a new private skills repository

Create an empty repository on GitHub, GitLab, Gitea, or another Git host. Do not add an initial README if you already initialized the local repository.

Then run:

```bash
agent-skills setup
agent-skills push
```

Or configure manually:

```bash
agent-skills init-repo --repo ~/agent-skills-library --remote git@github.com:username/private-agent-skills.git
agent-skills push
```

## Development

Run from source:

```bash
python -m agent_skills_manager.cli --help
python -m agent_skills_manager.cli scan
python -m agent_skills_manager.cli push --dry-run
python -m agent_skills_manager.cli pull --dry-run
```

Run a syntax check:

```bash
python -m py_compile agent_skills_manager/cli.py
```
