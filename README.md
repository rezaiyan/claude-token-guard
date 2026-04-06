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

### Option A — Private marketplace (recommended)

**Step 1.** Add to `~/.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "claude-token-guard": {
      "source": {
        "source": "github",
        "repo": "alirezaiyan/claude-token-guard"
      }
    }
  }
}
```

**Step 2.** Install:

```bash
claude plugin install claude-token-guard@claude-token-guard
```

### Option B — Manual

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
