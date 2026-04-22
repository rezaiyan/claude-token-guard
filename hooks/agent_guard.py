#!/usr/bin/env python3
"""
PreToolUse hook: blocks expensive agent types.

Mode is controlled by the AGENT_GUARD_MODE environment variable:
  block  (default) — hard block, Claude cannot proceed
  warn             — prints a bold warning to stderr, Claude proceeds anyway
  ask              — interactive bold warning on the terminal, user decides

Blocked:
  - subagent_type == "Explore"  — broad codebase exploration
  - subagent_type == "Plan"     — planning agents (use EnterPlanMode instead)
  - description starts with "research" — open-ended research agents
  - any type listed in CLAUDE_TOKEN_GUARD_EXTRA_BLOCKED (comma-separated)

Exit codes:
  0  — hook ran (decision embedded in JSON output)
  1  — unexpected error (hook fails open, Claude proceeds)
"""
import datetime
import json
import os
import pathlib
import re
import sys

VALID_MODES = {"block", "warn", "ask"}

_raw_mode = os.environ.get("AGENT_GUARD_MODE", "block").lower()
if _raw_mode not in VALID_MODES:
    print(
        f"[agent-guard] Unknown AGENT_GUARD_MODE={_raw_mode!r}, defaulting to 'block'",
        file=sys.stderr,
    )
    MODE = "block"
else:
    MODE = _raw_mode

_extra = os.environ.get("CLAUDE_TOKEN_GUARD_EXTRA_BLOCKED", "")
EXTRA_BLOCKED = {t.strip() for t in _extra.split(",") if t.strip()}
BLOCKED_TYPES = {"Explore", "Plan"} | EXTRA_BLOCKED

RESEARCH_RE = re.compile(r"^research\b", re.IGNORECASE)

BOLD = "\033[1m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"


def _log_stat(action: str, detail: str) -> None:
    try:
        entry = json.dumps({
            "ts": datetime.datetime.utcnow().isoformat(),
            "hook": "agent_guard",
            "action": action,
            "detail": detail,
        })
        stats_file = pathlib.Path.home() / ".claude" / "token-guard-stats.jsonl"
        with stats_file.open("a") as f:
            f.write(entry + "\n")
    except Exception:
        pass


def build_reason(subagent_type: str = "", description: str = "") -> str:
    if subagent_type:
        return (
            f"The '{subagent_type}' agent type is blocked — it consumes 20-50K tokens "
            f"for exploration tasks that Grep, Glob, and Read handle directly. "
            f"Use targeted tool calls instead."
        )
    return (
        "Research agents consume too much context. "
        "Use WebFetch or targeted Grep/Read for information gathering."
    )


def handle_match(reason: str, detail: str) -> None:
    if MODE == "warn":
        print(f"{BOLD}{YELLOW}[agent-guard warning]{RESET} {reason}", file=sys.stderr)
        print(json.dumps({}))

    elif MODE == "ask":
        try:
            tty = open("/dev/tty", "r+")
            tty.write(f"\n{BOLD}{RED}[agent-guard]{RESET} {BOLD}{reason}{RESET}\n")
            tty.write(f"{BOLD}Proceed anyway? [y/N] {RESET}")
            tty.flush()
            answer = tty.readline().strip().lower()
            tty.close()
        except OSError:
            # No TTY available (e.g. CI) — fall back to block
            _log_stat("block", detail)
            print(json.dumps({"decision": "block", "reason": reason}))
            return

        if answer in ("y", "yes"):
            print(json.dumps({}))
        else:
            _log_stat("block", detail)
            print(json.dumps({"decision": "block", "reason": reason}))

    else:  # block (default)
        _log_stat("block", detail)
        print(json.dumps({"decision": "block", "reason": reason}))


def main():
    if "--check" in sys.argv:
        extra = os.environ.get("CLAUDE_TOKEN_GUARD_EXTRA_BLOCKED", "(none)")
        print(f"agent_guard: OK — AGENT_GUARD_MODE={MODE}, EXTRA_BLOCKED={extra}")
        sys.exit(0)

    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(1)

    tool_input = data.get("tool_input", {})
    subagent_type = tool_input.get("subagent_type", "")
    description = tool_input.get("description", "")

    if subagent_type in BLOCKED_TYPES:
        handle_match(build_reason(subagent_type=subagent_type), detail=subagent_type)
        return

    if RESEARCH_RE.match(description):
        handle_match(build_reason(description=description), detail=f"research: {description[:60]}")
        return

    print(json.dumps({}))


if __name__ == "__main__":
    main()