#!/usr/bin/env bash
# Idempotently sync the pre-commit hook from the repo source into
# .git/hooks/pre-commit. Run from the repo root.
#
# Source of truth: scripts/ai_guard/pre_commit_hook.sh
# Install target: .git/hooks/pre-commit
#
# Design notes:
# - Idempotent: re-running overwrites with the same content + chmod.
# - Safe in CI sandboxes: if .git/hooks/ is missing or not writable
#   (e.g., shallow clones, sandboxed runners), prints an info line and
#   exits 0 instead of breaking pnpm install / other callers.
# - Standalone: no `set -e` so a missing .git/hooks/ doesn't cascade.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE="$REPO_ROOT/scripts/ai_guard/pre_commit_hook.sh"
TARGET="$REPO_ROOT/.git/hooks/pre-commit"

if [ ! -f "$SOURCE" ]; then
    echo "[install-pre-commit-hook] source missing: $SOURCE" >&2
    exit 0
fi

if [ ! -d "$REPO_ROOT/.git" ]; then
    echo "[install-pre-commit-hook] not a git repo (.git missing) — skip" >&2
    exit 0
fi

if [ ! -d "$REPO_ROOT/.git/hooks" ]; then
    echo "[install-pre-commit-hook] .git/hooks missing — skip" >&2
    exit 0
fi

if ! cp "$SOURCE" "$TARGET" 2>/dev/null; then
    echo "[install-pre-commit-hook] cannot write to $TARGET — skip" >&2
    exit 0
fi

chmod +x "$TARGET"
echo "[install-pre-commit-hook] installed $(basename "$TARGET") from $SOURCE"