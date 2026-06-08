# Platforms, GUI, and publishing

Platform-specific notes, the optional GUI, and how to publish a new private
skills repository. For installation, see the [README](../README.md).

## Optional Qt GUI

Agent Skills Manager includes an optional PySide6 desktop GUI for users who prefer a visual workflow.

Install:

```bash
python -m pip install "agent-skills-manager[qt]"
agent-skills gui
```

The CLI remains the primary, dependency-free interface. The GUI is optional and uses the same configuration and sync logic as the CLI — it never reimplements business rules.

The window has eight pages in a left-hand nav:

- **Overview** — a dashboard of config, repository, and target status.
- **Targets** — edit the mapping of local skill directories to repo subdirectories. Removing a target only changes config; it never deletes files.
- **Sync** — preview push/pull safely (read-only), then apply. Dry-run is on by default; mirror and force require confirmation, and Apply stays disabled while conflicts exist.
- **Diff** — per-target, file-level view of what differs between local and repo.
- **Validate** — structure, metadata, duplicate-name, and possible-secret findings.
- **Backups** — list backups and restore them (a dry-run is required before a real restore).
- **Settings** — repository, remote, branch, backups directory, excludes, and profile.
- **Logs** — output from every apply/restore command.

If PySide6 is not installed, `agent-skills gui` prints an install hint and points you at the CLI commands instead.

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
