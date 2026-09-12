# Shared list of protected files enforced by pre-commit + commit-msg hooks.
#
# Why split out: Both hooks (pre-commit, commit-msg) need the same list. Keeping
# it in one source prevents drift between them. Edit here ONCE; both hooks
# source this file.
#
# Why some files are protected:
# - butler/core/agent_loop/loop.py, butler/contracts/__init__.py, pyproject.toml:
#   load-bearing layers; mistakes cascade.
# - .claude/settings.json, scripts/ai_guard/{pre,post}_tool_use_hook.py:
#   AI guard infrastructure itself.
# - butler-v5/{apps/api,packages/{persistence,runtime}}/src/...:
#   Production load-bearing files (see docs/plans/active/v5-ai-guard-migration-checklist-2026-08.md).
#
# Override: Add [MANUAL-OVERRIDE] tag to commit message (enforced by commit-msg hook).
# Escape hatch: --no-verify bypasses both hooks (use sparingly).

PROTECTED_FILES=(
    "butler/core/agent_loop/loop.py"
    "butler/contracts/__init__.py"
    "pyproject.toml"
    ".claude/settings.json"
    "scripts/ai_guard/pre_tool_use_hook.py"
    "scripts/ai_guard/post_tool_use_hook.py"
    "butler-v5/packages/persistence/src/migrations/0001_initial.sql"
    "butler-v5/apps/api/src/wechat-inbound-butler.ts"
    "butler-v5/packages/runtime/src/agent-kernel.ts"
    "butler-v5/packages/runtime/src/run-engine.ts"
    "butler-v5/packages/persistence/src/event-bridge.ts"
    "butler-v5/packages/runtime/src/capability-boundary.ts"
    "butler-v5/apps/api/src/tool-boundary.ts"
    "butler-v5/apps/api/src/capability-guard.ts"
    "butler-v5/apps/api/src/workspace-tools.ts"
)