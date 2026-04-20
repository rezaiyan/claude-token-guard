# claude-token-guard

A Claude Code plugin that cuts token burn on every session via two `PreToolUse` hooks.

No Node.js. No build step. Pure Python 3 stdlib.

---

## What it does

### 1. Agent Guard

Blocks expensive agent types before they consume 20–50K tokens on tasks that `Grep`, `Glob`, and `Read` handle in under 500:

| Blocked | Reason |
|---|---|
| `subagent_type: "Explore"` | Broad codebase exploration — use `Grep`/`Glob` directly |
| `subagent_type: "Plan"` | Planning agents — use `EnterPlanMode` instead |
| `description` starts with `"research"` | Open-ended research — use `WebFetch` or targeted reads |

Claude gets a clear error message explaining what to use instead, so it self-corrects.

![Agent Guard blocking an Explore agent](docs/agent-guard-demo.png)

### 2. Bash Trimmer

Silently rewrites verbose Bash commands to token-efficient equivalents before they run:

| Original | Rewritten to |
|---|---|
| `git log` | `git log --oneline -20` |
| `npm list` | `npm list --depth=0` |
| `pip list` | `pip list --format=columns` |
| `pytest ...` | `pytest ... -q --tb=short` |
| `python -m pytest ...` | `python -m pytest ... -q --tb=short` |
| `./gradlew <task>` | `./gradlew <task> --quiet` |

Rules are skipped if the relevant flags are already present. `gradlew tasks/dependencies/help/properties/projects` are excluded (their output is the point).

---

## Installation

### Claude Code plugin (recommended)

```bash
# Add the marketplace (once)
claude plugin marketplace add rezaiyan/claude-plugins

# Install
claude plugin install claude-token-guard@rezaiyan
```

### Project scope (shared team repo)

Run once, commit `.claude/settings.json` — teammates just need the second line after cloning:

```bash
# One-time setup
claude plugin marketplace add rezaiyan/claude-plugins --scope project

# Everyone on the team
claude plugin install claude-token-guard@rezaiyan
```

### Manual

Copy `hooks/agent_guard.py` and `hooks/bash_trimmer.py` anywhere, then add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Agent",
        "hooks": [{ "type": "command", "command": "python3 /path/to/agent_guard.py" }]
      },
      {
        "matcher": "Bash",
        "hooks": [{ "type": "command", "command": "python3 /path/to/bash_trimmer.py" }]
      }
    ]
  }
}
```

---

## Customising

**Change the guard mode** — set `AGENT_GUARD_MODE` in your environment or inline in the hook command:

| Mode | Behaviour |
|---|---|
| `block` (default) | Hard block — Claude cannot proceed |
| `warn` | Prints a bold warning to stderr, Claude proceeds anyway |
| `ask` | Interactive prompt in the terminal, you decide per-invocation |

```bash
# Shell (persistent)
export AGENT_GUARD_MODE=warn   # or: ask

# Or inline in settings.json hook command:
"command": "AGENT_GUARD_MODE=ask python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/agent_guard.py\""
```

In `ask` mode the prompt appears directly in your terminal with a bold warning and a `[y/N]` confirmation. Falls back to `block` when no TTY is available (e.g. CI).

**Add more blocked agent types** — edit `BLOCKED_TYPES` in `agent_guard.py`:
```python
BLOCKED_TYPES = {"Explore", "Plan", "general-purpose"}
```

**Add more Bash trim rules** — append to `TRIM_RULES` in `bash_trimmer.py`:
```python
(r"^docker images$", lambda m: "docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}'"),
```

---

## Requirements

- Claude Code with plugin support
- Python 3.8+

---

## License

MIT
