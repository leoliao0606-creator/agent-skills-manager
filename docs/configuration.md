# Configuration, targets, and profiles

How Agent Skills Manager stores settings, manages skill targets, supports
multiple profiles, and decides which files to ignore. For day-to-day commands,
see the [command reference](commands.md).

## Config file location

Configuration is stored in an OS-specific per-user config file:

```text
Windows: %APPDATA%\agent-skills-manager\config.json
macOS:   ~/Library/Application Support/agent-skills-manager/config.json
Linux:   ~/.config/agent-skills-manager/config.json
```

You can override the config path with the `AGENT_SKILLS_CONFIG` environment variable:

```bash
AGENT_SKILLS_CONFIG=/path/to/config.json agent-skills scan
```

```powershell
$env:AGENT_SKILLS_CONFIG="C:\path\to\config.json"
agent-skills scan
```

## Scriptable config

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

## Scriptable target management

```bash
agent-skills target list
agent-skills target list --format json
agent-skills target add my-agent --local ~/.my-agent/skills --repo my-agent-skills
agent-skills target add work-agent --local ~/work/skills --repo work-skills --disabled
agent-skills target enable my-agent
agent-skills target disable my-agent
agent-skills target remove my-agent
```

## Profiles

Profiles are separate config files for separate skill setups, such as personal, work, public, and experimental libraries.

```bash
agent-skills profile list
agent-skills profile create work
agent-skills profile use work
agent-skills --profile work scan
agent-skills --profile work push --dry-run
```

`profile use NAME` copies a named profile into the default active config. `--profile NAME` uses that profile only for the current invocation.

## Excludes and ignore files

Default ignored files and directories include `.git/`, `.env`, virtualenvs, Python caches, `.DS_Store`, and `node_modules/`. You can add a `.agent-skills-ignore` file to a source or destination root, or configure global patterns with:

```bash
agent-skills config set excludes ".git/,.env,__pycache__/,*.pyc,node_modules/"
```

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
