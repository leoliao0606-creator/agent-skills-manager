# Platforms, GUI, and publishing

Platform-specific notes, the optional GUI, and how to publish a new private
skills repository. For installation, see the [README](../README.md).

## GUI

```bash
agent-skills gui
```

The GUI is experimental and intentionally secondary to the CLI. It edits the same config (including adding and removing targets) and runs `scan`, `status`, `diff`, `validate`, `pull`, and `push` as background actions, streaming their output into a log pane so the window stays responsive. A dry-run toggle previews `push`/`pull`, and a mirror toggle (with a delete confirmation) enables mirror sync. The CLI still has the full feature set.

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
