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

Exit codes:
  0  — hook ran (decision embedded in JSON output)
  1  — unexpected error (hook fails open, Claude proceeds)
"""
import json
import os
import re
import sys

BLOCKED_TYPES = {"Explore", "Plan"}
RESEARCH_RE = re.compile(r"^research\b", re.IGNORECASE)

MODE = os.environ.get("AGENT_GUARD_MODE", "block").lower()

BOLD = "\033[1m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"


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


def handle_match(reason: str) -> None:
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
            print(json.dumps({"decision": "block", "reason": reason}))
            return

        if answer in ("y", "yes"):
            print(json.dumps({}))
        else:
            print(json.dumps({"decision": "block", "reason": reason}))

    else:  # block (default)
        print(json.dumps({"decision": "block", "reason": reason}))


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(1)

    tool_input = data.get("tool_input", {})
    subagent_type = tool_input.get("subagent_type", "")
    description = tool_input.get("description", "")

    if subagent_type in BLOCKED_TYPES:
        handle_match(build_reason(subagent_type=subagent_type))
        return

    if RESEARCH_RE.match(description):
        handle_match(build_reason(description=description))
        return

    print(json.dumps({}))


if __name__ == "__main__":
    main()
