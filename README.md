# Agent Skills Manager

一个独立的小工具，用来把本机已经安装的 AI Agent skills 自动扫描出来，并同步到你的私人 skills Git 仓库。

它替代原先分散的 `pull-agent-skills` / `push-agent-skills` 两个脚本，提供：

- 自动扫描本机已安装的 skills：
  - Claude Code: `~/.claude/skills`
  - Hermes Agent: `~/.hermes/skills`
- 手把手配置私人 skills 仓库：本地路径、远程 Git URL、分支、每类 skills 的映射目录
- 简单命令随时同步：
  - `agent-skills push`：本机 skills -> 私人仓库 -> git push
  - `agent-skills pull`：git pull -> 私人仓库 -> 本机 skills
- 图形化设置窗口：`agent-skills gui`
- 无第三方 Python 依赖，只需要 Python 3.9+ 和 git

## 快速开始

在本项目目录运行：

```bash
cd /home/Projects/agent-skills-manager
python3 -m agent_skills_manager.cli scan
python3 -m agent_skills_manager.cli setup
```

如果想安装成全局命令：

```bash
cd /home/Projects/agent-skills-manager
python3 -m pip install -e .
agent-skills setup
```

或者不使用 pip，直接生成 wrapper：

```bash
cd /home/Projects/agent-skills-manager
python3 -m agent_skills_manager.cli install-shell --bindir ~/bin
# 确保 ~/bin 在 PATH 中
agent-skills scan
```

## 推荐工作流

### 1. 第一次配置

```bash
agent-skills setup
```

向导会询问：

- 私人 skills 仓库本地路径，例如 `/home/Projects/personal-agent-skills`
- 远程 Git URL，例如 `git@github.com:你的用户名/private-agent-skills.git`
- 默认分支，例如 `main`
- Claude Code skills 本地目录和仓库内目录
- Hermes skills 本地目录和仓库内目录

配置会保存到：

```text
~/.config/agent-skills-manager/config.json
```

### 2. 查看扫描结果

```bash
agent-skills scan
agent-skills status
```

### 3. 把本机 skills 备份/推送到私人仓库

```bash
agent-skills push
agent-skills push -m "Add my new skills"
agent-skills push --dry-run
```

默认是安全的“增量更新”：只复制新增/修改的文件，不删除仓库里本来存在但本机没有的文件。

如果你明确想完全镜像本机状态，可以用：

```bash
agent-skills push --mirror
```

### 4. 从私人仓库拉取到本机

```bash
agent-skills pull
agent-skills pull --dry-run
```

默认也是安全的“增量更新”：不会删除本机 local-only skills。

如需严格镜像仓库状态：

```bash
agent-skills pull --mirror
```

拉取后建议重启对应 Agent 会话，或在 Hermes 中运行 `/reload-skills`。

### 5. 图形化配置

```bash
agent-skills gui
```

图形窗口可以设置：

- 本地 repo 路径
- Git remote URL
- 分支
- 每个 Agent 的本地 skills 目录和仓库内目录
- 一键 Scan / Pull / Push

注意：GUI 依赖系统的 Tkinter。如果最小化 VPS 没装 Tkinter，可以继续使用 CLI。

## 仓库布局建议

私人 skills 仓库建议使用这个结构：

```text
private-agent-skills/
  README.md
  agent-skills/     # Claude Code compatible skills
    some-skill/SKILL.md
  hermes-skills/    # Hermes skill library, normally category/name/SKILL.md
    software-development/some-skill/SKILL.md
```

本工具默认使用上面的布局，但你可以在 `setup` 或 `gui` 中修改。

## 命令列表

```text
agent-skills setup          交互式配置向导
agent-skills scan           扫描本机和仓库里的 skills
agent-skills status         显示 Git 状态和 skills 计数
agent-skills init-repo      初始化私人 skills 仓库骨架
agent-skills push           本机 -> 仓库，commit，push
agent-skills pull           仓库 -> 本机
agent-skills gui            打开图形化设置窗口
agent-skills install-shell  安装 agent-skills / askills wrapper 到 ~/bin
```

## 和旧脚本的关系

旧脚本：

- `pull-agent-skills`
- `push-agent-skills`

可以继续保留；这个项目相当于把它们升级成可配置、可扫描、可 GUI 设置的独立工具。

如果想逐步迁移，可以先只运行：

```bash
python3 -m agent_skills_manager.cli scan
python3 -m agent_skills_manager.cli push --dry-run
python3 -m agent_skills_manager.cli pull --dry-run
```

确认输出没问题后再正式 `push` / `pull`。
