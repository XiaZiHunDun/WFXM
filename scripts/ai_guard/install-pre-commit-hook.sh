#!/usr/bin/env bash
# Idempotently sync git hooks from repo sources into .git/hooks/.
# Run from the repo root.
#
# Sources of truth (script files in scripts/ai_guard/):
#   - pre_commit_hook.sh  -> .git/hooks/pre-commit
#   - commit_msg_hook.sh  -> .git/hooks/commit-msg
#
# Both hooks share scripts/ai_guard/protected_files.sh (sourced at runtime,
# so changes to that file take effect without re-installing the hooks).
#
# Design notes:
# - Idempotent: re-running overwrites with the same content + chmod.
# - Safe in CI sandboxes: if .git/hooks/ is missing or not writable
#   (e.g., shallow clones, sandboxed runners), prints an info line and
#   exits 0 instead of breaking pnpm install / other callers.
# - Standalone: no `set -e` so a missing .git/hooks/ doesn't cascade.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Format: "<source> <target>"
HOOKS=(
    "pre_commit_hook.sh pre-commit"
    "commit_msg_hook.sh commit-msg"
)

if [ ! -d "$REPO_ROOT/.git" ]; then
    echo "[install-hooks] not a git repo (.git missing) — skip" >&2
    exit 0
fi

if [ ! -d "$REPO_ROOT/.git/hooks" ]; then
    echo "[install-hooks] .git/hooks missing — skip" >&2
    exit 0
fi

EXIT_CODE=0
for entry in "${HOOKS[@]}"; do
    source_name="${entry% *}"
    target_name="${entry#* }"
    SOURCE="$REPO_ROOT/scripts/ai_guard/$source_name"
    TARGET="$REPO_ROOT/.git/hooks/$target_name"

    if [ ! -f "$SOURCE" ]; then
        echo "[install-hooks] source missing: $SOURCE" >&2
        EXIT_CODE=1
        continue
    fi

    if ! cp "$SOURCE" "$TARGET" 2>/dev/null; then
        echo "[install-hooks] cannot write to $TARGET — skip" >&2
        EXIT_CODE=1
        continue
    fi

    chmod +x "$TARGET"
    echo "[install-hooks] installed $target_name from $source_name"
done

exit $EXIT_CODE