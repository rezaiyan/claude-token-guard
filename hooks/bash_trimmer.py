#!/usr/bin/env python3
"""
PreToolUse hook: rewrites verbose Bash commands to token-efficient equivalents.

Some commands produce enormous output by default. This hook intercepts the
Bash tool call and rewrites the command before it runs — silently, without
blocking — so Claude gets the same information in far fewer tokens.

Rules applied (first match wins):
  git log          → git log --oneline -20
  npm list         → npm list --depth=0
  pip list         → pip list --format=columns
  pytest / python -m pytest  → appends -q --tb=short
  ./gradlew <task> → appends --quiet  (except tasks/dependencies/help/properties/projects)

Exit codes:
  0  — hook ran (rewritten command in updatedInput, or empty object if unchanged)
  1  — unexpected error (hook fails open, original command runs)
"""
import json
import re
import sys

TRIM_RULES = [
    # git log: replace entirely — always use oneline, cap at 20
    (r"^git log(?! --oneline)(?! -\d)", lambda m: "git log --oneline -20"),
    # npm list: replace entirely — depth 0 only
    (r"^npm list(?! --depth)", lambda m: "npm list --depth=0"),
    # pip list: replace entirely
    (r"^pip list$", lambda m: "pip list --format=columns"),
    # pytest: append flags — skip if -q/--quiet/--tb already set
    (r"^(pytest)(?!.*-q)(?!.*--quiet)(?!.*--tb=)(.*)", lambda m: m.group(0) + " -q --tb=short"),
    (r"^(python3? -m pytest)(?!.*-q)(?!.*--quiet)(?!.*--tb=)(.*)", lambda m: m.group(0) + " -q --tb=short"),
    # gradlew: append --quiet — skip informational tasks where output is the point
    (
        r"^\./gradlew(?!\s+(?:tasks|dependencies|help|properties|projects)\b)(?!.*--quiet)(.*)",
        lambda m: m.group(0) + " --quiet",
    ),
]


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(1)

    cmd = data.get("tool_input", {}).get("command", "")
    new_cmd = cmd.strip()

    for pattern, replacement in TRIM_RULES:
        match = re.match(pattern, new_cmd)
        if match:
            new_cmd = replacement(match)
            break

    if new_cmd != cmd.strip():
        print(json.dumps({"updatedInput": {"command": new_cmd}}))
    else:
        print(json.dumps({}))


if __name__ == "__main__":
    main()
