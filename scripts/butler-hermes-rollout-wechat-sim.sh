#!/usr/bin/env bash
# Hermes rollout WeChat handler sim (no iLink) — /诊断 · 记忆待审 · 技能学习待审.
#
# Usage:
#   bash scripts/butler-hermes-rollout-wechat-sim.sh
#   bash scripts/butler-hermes-rollout-wechat-sim.sh --verbose
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

VERBOSE=0
for arg in "$@"; do
  case "$arg" in
    --verbose|-v) VERBOSE=1 ;;
  esac
done

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

exec python3 - "$VERBOSE" <<'PY'
from __future__ import annotations

import json
import os
import sys
import time
from unittest.mock import patch

verbose = sys.argv[1] == "1"
owner = (os.getenv("BUTLER_OWNER_WECHAT_ID") or "").strip()
if not owner:
    print("FAIL: BUTLER_OWNER_WECHAT_ID not set")
    raise SystemExit(1)

print("=== Hermes rollout WeChat sim (handler, no iLink) ===")
print(f"  owner={owner[:24]}…")
print(f"  BUTLER_ENV_PROFILE={os.getenv('BUTLER_ENV_PROFILE', '')!r}")
print(f"  BUTLER_SKILL_WRITE_APPROVAL={os.getenv('BUTLER_SKILL_WRITE_APPROVAL', '')!r}")
print(f"  BUTLER_TOOLSET={os.getenv('BUTLER_TOOLSET', '')!r}")
print(f"  BUTLER_MEMORY_WRITE_APPROVAL={os.getenv('BUTLER_MEMORY_WRITE_APPROVAL', '')!r}")

from butler.config import reload_butler_settings

reload_butler_settings()

from butler.gateway.message_handler import ButlerMessageHandler
from butler.memory.owner_write_pending import (
    list_owner_pending,
    queue_owner_write,
    reject_all_owner_pending,
)
from butler.skills.write_approval import list_skill_pending, reject_all_skill_pending

failures: list[str] = []
sk = f"wechat:{owner}:hermes-rollout-{time.time_ns()}"
handler = ButlerMessageHandler(channel="gateway")


def send(text: str) -> str:
    return (
        handler.handle_message(
            text,
            session_key=sk,
            platform="wechat",
            external_id=owner,
        )
        or ""
    )


def step(name: str, reply: str, *needles: str, forbid: tuple[str, ...] = ()) -> None:
    preview = reply.replace("\n", " ")[:280]
    if verbose:
        print(f"\n== {name} ==\n  IN:  (see setup)\n  OUT: {preview}{'…' if len(reply) > 280 else ''}")
    for bad in forbid:
        if bad in reply:
            failures.append(name)
            print(f"  [FAIL] {name}: must not contain {bad!r}")
            return
    if needles and not any(n in reply for n in needles):
        failures.append(name)
        print(f"  [FAIL] {name}: need any of {needles}")
        print(f"         reply: {preview}")
        return
    print(f"  [ok] {name}")


# --- clean slate ---
reject_all_owner_pending()
reject_all_skill_pending()

# --- 1 /诊断 ---
step("/诊断", send("/诊断"), "简要诊断", "网关", "项目")

# --- 2 memory pending flow ---
queue_owner_write(
    scope="owner_profile",
    content="hermes-sim: Owner 偏好简短要点式回复",
)
step("/记忆待审", send("/记忆待审"), "所有者记忆待审", "owner_profile")
step("/批准记忆 1", send("/批准记忆 1"), "批准", "owner_profile")
step("/记忆待审 empty", send("/记忆待审"), "没有", "为空")

if list_owner_pending():
    failures.append("owner_pending_cleanup")
    print(f"  [FAIL] owner pending not drained: {len(list_owner_pending())}")

# --- 3 skill learn → pending (mock auxiliary LLM) ---
skill_payload = json.dumps(
    {
        "name": "hermes-sim-lint",
        "description": "合并前检查 Python 类型",
        "triggers": ["lint", "类型"],
        "content": "---\nname: hermes-sim-lint\n---\n# Hermes sim skill\n",
    },
    ensure_ascii=False,
)
with patch(
    "butler.transport.auxiliary_client.auxiliary_complete",
    return_value=skill_payload,
):
    learn_reply = send("/技能学习 帮助我在合并前检查 Python 类型注解与 import")

step(
    "/技能学习",
    learn_reply,
    "待审",
    "hermes-sim-lint",
)
step("/技能待审", send("/技能待审"), "hermes-sim-lint", "技能待审")
step("/批准技能 1", send("/批准技能 1"), "批准", "hermes-sim-lint")
step("/技能待审 empty", send("/技能待审"), "没有")

if list_skill_pending():
    failures.append("skill_pending_cleanup")
    print(f"  [FAIL] skill pending not drained: {len(list_skill_pending())}")

print(f"\nhermes-rollout-wechat-sim: {'ALL PASS' if not failures else failures}")
raise SystemExit(1 if failures else 0)
PY
