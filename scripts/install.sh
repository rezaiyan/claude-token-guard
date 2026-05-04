#!/usr/bin/env bash
# claude-token-guard — self-contained installer
# No GitHub access required after you have this file.
#
# Usage:
#   bash install.sh              # installs to ~/.claude (user scope)
#   bash install.sh --project    # installs to ./.claude (project scope)
#   bash install.sh --uninstall  # removes hooks from settings.json
#   bash install.sh --check      # verifies hooks are reachable
#
# Requirements: Python 3.8+, bash

set -euo pipefail

# ── config ──────────────────────────────────────────────────────────────────
PLUGIN_NAME="claude-token-guard"
SCOPE="user"
ACTION="install"

for arg in "$@"; do
  case "$arg" in
    --project)   SCOPE="project" ;;
    --uninstall) ACTION="uninstall" ;;
    --check)     ACTION="check" ;;
    --help|-h)
      grep '^#' "$0" | head -10 | sed 's/^# \{0,1\}//'
      exit 0
      ;;
  esac
done

if [[ "$SCOPE" == "project" ]]; then
  SETTINGS_DIR=".claude"
else
  SETTINGS_DIR="$HOME/.claude"
fi

HOOKS_DIR="$SETTINGS_DIR/plugins/$PLUGIN_NAME/hooks"
SETTINGS_FILE="$SETTINGS_DIR/settings.json"
AGENT_GUARD="$HOOKS_DIR/agent_guard.py"
BASH_TRIMMER="$HOOKS_DIR/bash_trimmer.py"

# ── helpers ──────────────────────────────────────────────────────────────────
info()    { echo "[token-guard] $*"; }
success() { echo "[token-guard] ✓ $*"; }
warn()    { echo "[token-guard] ⚠ $*" >&2; }
die()     { echo "[token-guard] ✗ $*" >&2; exit 1; }

require_python() {
  command -v python3 >/dev/null 2>&1 || die "python3 not found. Install Python 3.8+ and retry."
  local ver
  ver=$(python3 -c "import sys; print(sys.version_info >= (3,8))")
  [[ "$ver" == "True" ]] || die "Python 3.8+ required."
}

# ── check ────────────────────────────────────────────────────────────────────
if [[ "$ACTION" == "check" ]]; then
  require_python
  [[ -f "$AGENT_GUARD" ]]   || die "agent_guard.py not found at $AGENT_GUARD — run install first."
  [[ -f "$BASH_TRIMMER" ]]  || die "bash_trimmer.py not found at $BASH_TRIMMER — run install first."
  python3 "$AGENT_GUARD" --check
  python3 "$BASH_TRIMMER" --check
  success "All hooks reachable."
  exit 0
fi

# ── uninstall ─────────────────────────────────────────────────────────────────
if [[ "$ACTION" == "uninstall" ]]; then
  info "Removing hooks from $SETTINGS_FILE …"
  python3 - "$SETTINGS_FILE" "$AGENT_GUARD" "$BASH_TRIMMER" <<'PYEOF'
import json, sys, pathlib

settings_path = pathlib.Path(sys.argv[1])
agent_path    = sys.argv[2]
trimmer_path  = sys.argv[3]

if not settings_path.exists():
    print("[token-guard] settings.json not found — nothing to remove.")
    sys.exit(0)

cfg = json.loads(settings_path.read_text())
hooks = cfg.get("hooks", {})
pre   = hooks.get("PreToolUse", [])

def drops(entry):
    for h in entry.get("hooks", []):
        cmd = h.get("command", "")
        if agent_path in cmd or trimmer_path in cmd:
            return True
    return False

before = len(pre)
pre    = [e for e in pre if not drops(e)]
after  = len(pre)

if pre:
    hooks["PreToolUse"] = pre
elif "PreToolUse" in hooks:
    del hooks["PreToolUse"]

if hooks:
    cfg["hooks"] = hooks
elif "hooks" in cfg:
    del cfg["hooks"]

settings_path.write_text(json.dumps(cfg, indent=2) + "\n")
removed = before - after
print(f"[token-guard] Removed {removed} hook(s) from {settings_path}")
PYEOF
  rm -rf "$HOOKS_DIR"
  success "Uninstalled."
  exit 0
fi

# ── install ───────────────────────────────────────────────────────────────────
require_python

info "Installing $PLUGIN_NAME …"
mkdir -p "$HOOKS_DIR"

# ── agent_guard.py ────────────────────────────────────────────────────────────
cat > "$AGENT_GUARD" <<'PYEOF'
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
PYEOF

# ── bash_trimmer.py ───────────────────────────────────────────────────────────
cat > "$BASH_TRIMMER" <<'PYEOF'
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
PYEOF

chmod +x "$AGENT_GUARD" "$BASH_TRIMMER"

# ── patch settings.json ───────────────────────────────────────────────────────
info "Patching $SETTINGS_FILE …"
mkdir -p "$SETTINGS_DIR"

python3 - "$SETTINGS_FILE" "$AGENT_GUARD" "$BASH_TRIMMER" <<'PYEOF'
import json, sys, pathlib

settings_path = pathlib.Path(sys.argv[1])
agent_path    = sys.argv[2]
trimmer_path  = sys.argv[3]

cfg = json.loads(settings_path.read_text()) if settings_path.exists() else {}
hooks = cfg.setdefault("hooks", {})
pre   = hooks.setdefault("PreToolUse", [])

def already_has(cmd_path):
    for entry in pre:
        for h in entry.get("hooks", []):
            if cmd_path in h.get("command", ""):
                return True
    return False

added = 0
if not already_has(agent_path):
    pre.append({
        "matcher": "Agent",
        "hooks": [{"type": "command", "command": f"python3 {agent_path}"}]
    })
    added += 1

if not already_has(trimmer_path):
    pre.append({
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": f"python3 {trimmer_path}"}]
    })
    added += 1

settings_path.write_text(json.dumps(cfg, indent=2) + "\n")
print(f"[token-guard] Added {added} hook(s) to {settings_path}")
PYEOF

success "Installed to $SETTINGS_DIR"
info ""
info "Verify:    bash $0 --check"
info "Uninstall: bash $0 --uninstall"
info ""
info "Tip: set AGENT_GUARD_MODE=warn to soften blocking to a warning."
