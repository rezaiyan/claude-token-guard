---
name: release
description: Full release workflow for this plugin — preflight checks, commit pending changes, bump version, tag, push, verify GitHub release. Use instead of /deploy when the working tree may have uncommitted changes.
version: 1.0.0
---

# Release — Full Plugin Release Workflow

Handles everything from a dirty working tree to a published GitHub release.

## Usage

```
/release          # patch bump (default)
/release minor    # minor bump
/release major    # major bump
/release v1.2.3   # explicit version
```

## Steps

### 1. Preflight checks

Run in parallel:

```bash
git status --porcelain            # note modified/untracked files
git log --oneline origin/main..HEAD   # local-only commits
git log --oneline HEAD..origin/main   # detect divergence
grep -n "## \[Unreleased\]" CHANGELOG.md  # confirm section exists
```

**If diverged** (remote has commits not in local):
```bash
git pull --rebase origin main
```

**If no `## [Unreleased]`** → stop. Tell user to add one before releasing.

### 2. Commit pending changes

`bump-version.sh` requires a clean tree. If there are modified tracked files:

1. `git add -u` — stage only tracked modifications
2. If untracked files are noise → check whether they belong in `.gitignore`. If so, add to `.gitignore` and commit that.
3. Commit with a short message describing the actual changes (not "pre-release commit").

Verify `git status --porcelain` is effectively clean before continuing.
Skip this step if the tree is already clean.

### 3. Show release plan

Read current version from `.claude-plugin/plugin.json`.
Calculate the new version from the bump type.
If no argument given, ask: `"Bump type? [patch / minor / major / vX.Y.Z]"` and wait.

Show the plan and ask `"Proceed? [Y/n]"`:

```
Release plan for vNEW:
  • .claude-plugin/plugin.json  version: OLD → NEW
  • CHANGELOG.md  [Unreleased] → [NEW] - YYYY-MM-DD
  • git commit "chore: release vNEW"
  • git tag vNEW
  • git push origin main --tags
```

Wait for explicit `Y` before continuing.

### 4. Bump version

```bash
./scripts/bump-version.sh <bump-type>
```

Updates `plugin.json`, `CHANGELOG.md`, commits, tags, pushes.

### 5. Verify GitHub release

```bash
gh release view --repo rezaiyan/$(basename "$PWD")
```

If no release exists (workflow not set up or CI hasn't run yet), wait ~30s then check again.
If still missing, create manually:

```bash
gh release create vNEW --title "vNEW" --generate-notes
```

### 6. Report

```
Released vNEW
  commit  <sha>
  tag     vNEW
  pushed  origin/main

Users update with:
  claude plugin update <name>@rezaiyan
```

## Error Handling

| Failure | Action |
|---------|--------|
| No `[Unreleased]` in CHANGELOG | Stop — ask user to add entries first |
| User says N at plan confirmation | Stop — nothing written |
| `bump-version.sh` fails "not clean" | Re-run step 2, verify `git status` |
| `git push` fails | Report — commit + tag exist locally, user can push manually |
| `gh release` not found after 60s | Create manually via `gh release create` |
