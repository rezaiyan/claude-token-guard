#!/usr/bin/env python3
"""
PreToolUse hook: blocks expensive agent types.

Explore and Plan agents consume 20-50K tokens for tasks that targeted
Grep, Glob, and Read handle in under 500 tokens. This hook intercepts
Agent tool calls and blocks the wasteful ones before they run.

Blocked:
  - subagent_type == "Explore"  — broad codebase exploration
  - subagent_type == "Plan"     — planning agents (use EnterPlanMode instead)
  - description starts with "research" — open-ended research agents

Exit codes:
  0  — hook ran (decision embedded in JSON output)
  1  — unexpected error (hook fails open, Claude proceeds)
"""
import json
import re
import sys

BLOCKED_TYPES = {"Explore", "Plan"}
RESEARCH_RE = re.compile(r"^research\b", re.IGNORECASE)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(1)

    tool_input = data.get("tool_input", {})
    subagent_type = tool_input.get("subagent_type", "")
    description = tool_input.get("description", "")

    if subagent_type in BLOCKED_TYPES:
        print(json.dumps({
            "decision": "block",
            "reason": (
                f"The '{subagent_type}' agent type is blocked — it consumes 20-50K tokens "
                f"for exploration tasks that Grep, Glob, and Read handle directly. "
                f"Use targeted tool calls instead."
            )
        }))
        return

    if RESEARCH_RE.match(description):
        print(json.dumps({
            "decision": "block",
            "reason": (
                "Research agents are blocked — they consume too much context. "
                "Use WebFetch or targeted Grep/Read for information gathering."
            )
        }))
        return

    print(json.dumps({}))


if __name__ == "__main__":
    main()
