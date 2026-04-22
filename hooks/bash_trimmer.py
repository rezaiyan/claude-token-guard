#!/usr/bin/env python3
"""
PreToolUse hook: rewrites verbose Bash commands to token-efficient equivalents.

Some commands produce enormous output by default. This hook intercepts the
Bash tool call and rewrites the command before it runs — silently, without
blocking — so Claude gets the same information in far fewer tokens.

Rules applied (first match wins):
  git log (bare)             → git log --oneline -N  (N via CLAUDE_TOKEN_GUARD_GIT_LOG_LIMIT, default 20)
  npm list                   → npm list [flags] --depth=0  (existing flags preserved)
  yarn list                  → yarn list [flags] --depth=0  (existing flags preserved)
  pip list                   → pip list --format=columns
  docker images (bare)       → columnar format
  docker ps (bare)           → columnar format
  mvn test/verify/install    → appends -q
  go test ... -v ...         → pipes to tail -100
  pytest / python -m pytest  → appends -q --tb=short
  ./gradlew <task>           → appends --quiet  (except tasks/dependencies/help/properties/projects)

Environment:
  CLAUDE_TOKEN_GUARD_BYPASS=1         — skip all rewrites for this invocation
  CLAUDE_TOKEN_GUARD_GIT_LOG_LIMIT=N  — git log line limit (default 20)

Exit codes:
  0  — hook ran (rewritten command in updatedInput, or empty object if unchanged)
  1  — unexpected error (hook fails open, original command runs)
"""
import datetime
import json
import os
import pathlib
import re
import sys

GIT_LOG_LIMIT = int(os.environ.get("CLAUDE_TOKEN_GUARD_GIT_LOG_LIMIT", "20"))

TRIM_RULES = [
    # git log: bare call only — configurable limit
    (r"^git log$", lambda m: f"git log --oneline -{GIT_LOG_LIMIT}"),
    # npm list: preserve existing flags, append --depth=0
    (r"^npm list(?!.*--depth)(.*)", lambda m: f"npm list{m.group(1)} --depth=0"),
    # yarn list: same pattern
    (r"^yarn list(?!.*--depth)(.*)", lambda m: f"yarn list{m.group(1)} --depth=0"),
    # pip list: replace entirely
    (r"^pip list$", lambda m: "pip list --format=columns"),
    # docker images: columnar format
    (r"^docker images$", lambda m: "docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}'"),
    # docker ps: columnar format
    (r"^docker ps$", lambda m: "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"),
    # mvn test/verify/install: append -q if not already quiet
    (r"^mvn (test|verify|install)(?!.*-q)(.*)", lambda m: f"mvn {m.group(1)}{m.group(2)} -q"),
    # go test with -v: pipe to tail to cap output
    (r"^go test(.*)-v(.*)", lambda m: f"go test{m.group(1)}{m.group(2)} 2>&1 | tail -100"),
    # pytest: append flags — skip if -q/--quiet/--tb already set
    (r"^(pytest)(?!.*-q)(?!.*--quiet)(?!.*--tb=)(.*)", lambda m: m.group(0) + " -q --tb=short"),
    (r"^(python3? -m pytest)(?!.*-q)(?!.*--quiet)(?!.*--tb=)(.*)", lambda m: m.group(0) + " -q --tb=short"),
    # gradlew: append --quiet — skip informational tasks where output is the point
    (
        r"^\./gradlew(?!\s+(?:tasks|dependencies|help|properties|projects)\b)(?!.*--quiet)(.*)",
        lambda m: m.group(0) + " --quiet",
    ),
]


def _log_stat(action: str, detail: str) -> None:
    try:
        entry = json.dumps({
            "ts": datetime.datetime.utcnow().isoformat(),
            "hook": "bash_trimmer",
            "action": action,
            "detail": detail,
        })
        stats_file = pathlib.Path.home() / ".claude" / "token-guard-stats.jsonl"
        with stats_file.open("a") as f:
            f.write(entry + "\n")
    except Exception:
        pass


def main():
    if "--check" in sys.argv:
        bypass = os.environ.get("CLAUDE_TOKEN_GUARD_BYPASS", "0")
        git_limit = os.environ.get("CLAUDE_TOKEN_GUARD_GIT_LOG_LIMIT", "20")
        print(f"bash_trimmer: OK — BYPASS={bypass}, GIT_LOG_LIMIT={git_limit}")
        sys.exit(0)

    if os.environ.get("CLAUDE_TOKEN_GUARD_BYPASS") == "1":
        print(json.dumps({}))
        return

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
        _log_stat("rewrite", f"{cmd.strip()!r} → {new_cmd!r}")
        print(json.dumps({"updatedInput": {"command": new_cmd}}))
    else:
        print(json.dumps({}))


if __name__ == "__main__":
    main()