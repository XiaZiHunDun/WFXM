# Shared list of protected files enforced by pre-commit + commit-msg hooks.
#
# Why split out: Both hooks (pre-commit, commit-msg) need the same list. Keeping
# it in one source prevents drift between them. Edit here ONCE; both hooks
# source this file.
#
# Why some files are protected:
# - .claude/settings.json, scripts/ai_guard/{pre,post}_tool_use_hook.py:
#   AI guard infrastructure itself.
# - {apps/api,packages/{persistence,runtime}}/src/...:
#   Production load-bearing files.
#
# Override: Add [MANUAL-OVERRIDE] tag to commit message (enforced by commit-msg hook).
# Escape hatch: --no-verify bypasses both hooks (use sparingly).

PROTECTED_FILES=(
    ".claude/settings.json"
    "scripts/ai_guard/pre_tool_use_hook.py"
    "scripts/ai_guard/post_tool_use_hook.py"
    "packages/persistence/src/migrations/0001_initial.sql"
    "apps/api/src/wechat-inbound-butler.ts"
    "packages/runtime/src/agent-kernel.ts"
    "packages/runtime/src/run-engine.ts"
    "packages/persistence/src/event-bridge.ts"
    "packages/runtime/src/capability-boundary.ts"
    "apps/api/src/tool-boundary.ts"
    "apps/api/src/capability-guard.ts"
    "apps/api/src/workspace-tools.ts"
)