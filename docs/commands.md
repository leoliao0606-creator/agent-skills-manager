# Command reference

Full reference for the Agent Skills Manager subcommands. For first-run
onboarding, the "Which command should I use?" table, and the safety model, see
the [README](../README.md).

## Diagnose configuration

```bash
agent-skills doctor
agent-skills doctor --format json
```

`doctor` checks Git availability, config presence, repository safety, repo initialization, remotes, dirty state, and configured target directories.

## Scan local and repository skills

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

## Show status

```bash
agent-skills status
agent-skills status --format json
agent-skills status --no-git
agent-skills status --no-scan
```

`status` shows Git status/remotes and the same skill target summary used by `scan`.

## Preview changes

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

## Initialize a local skills repository skeleton

```bash
agent-skills init-repo
agent-skills init-repo --repo ~/agent-skills-library --remote git@github.com:username/private-agent-skills.git
```

`init-repo` creates a Git repo, target directories, README, `.gitignore`, and `.agent-skills-ignore`.

## Push local skills to the repository

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

## Pull repository skills into local skill directories

```bash
agent-skills pull --dry-run
agent-skills pull
agent-skills pull --mirror --yes
agent-skills pull --no-backup
```

By default, `pull` backs up each local target directory before writing if that target has planned changes.

## Sync both directions

```bash
agent-skills sync --dry-run
agent-skills sync
agent-skills sync -m "Sync skills"
```

`sync` runs a safe two-step flow:

1. repo -> local (`pull` phase)
2. local -> repo (`push` phase)

It uses the same dry-run, mirror, strict, force, backup, and dirty-repo flags as `pull` and `push`.

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

### Preview, compare, and copy skills across agents

```bash
agent-skills preview claude                       # name / version / description per skill
agent-skills preview claude --location repo
agent-skills preview claude --format json

agent-skills compare claude hermes                # only-A / only-B / same / differing
agent-skills compare claude claude --a-location local --b-location repo
agent-skills compare claude hermes --format json

agent-skills copy-skill claude:demo --to-target hermes            # apply one skill A -> B
agent-skills copy-skill claude:demo --to-target hermes --dry-run
agent-skills copy-skill claude:demo --to-target hermes --to-location repo
```

`preview` and `compare` read either the installed (`local`) or repository (`repo`)
copy of each side independently, so you can also compare a single target's local
vs repo. `compare` classifies every skill by name and directory content:

- `only_a` / `only_b`: the skill exists on only one side.
- `same`: present on both sides with identical files.
- `different`: present on both sides but the files differ.

`copy-skill` copies one skill directory from the source spec into `--to-target`,
reusing the same copy engine as `push`/`pull`. It backs up the destination target
before overwriting an existing local skill, refuses conflicting overwrites without
`--force`, and honours `--dry-run`, `--mirror`, and `--yes`.

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
- skill names are not duplicated **within a single target** (the same name across different targets is allowed);
- small text files do not contain obvious private keys or token-like secrets.

Secret scanning reports `path:line` for each likely secret. To silence a reviewed
false positive, add an inline `# pragma: allowlist secret` marker to that line.
Obvious documentation placeholders (for example values containing `your`,
`example`, `xxxx`, `changeme`, or `placeholder`) are not reported.

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
