#!/usr/bin/env bash
# Simulate WeChat inbound via ButlerMessageHandler (no iLink) — Extension verify phrases.
#
# Usage:
#   bash scripts/butler-extension-wechat-sim.sh
#   bash scripts/butler-extension-wechat-sim.sh --quick   # /诊断 only
#
# Skip (exit 0): BUTLER_EXTENSION_WECHAT_SIM=0, MCP off, or no LLM API key in env.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

if [[ "${BUTLER_EXTENSION_WECHAT_SIM:-1}" == "0" ]]; then
  echo "skip: BUTLER_EXTENSION_WECHAT_SIM=0"
  exit 0
fi

if [[ "${BUTLER_MCP_ENABLED:-0}" != "1" ]]; then
  echo "skip: BUTLER_MCP_ENABLED not 1"
  exit 0
fi

_has_llm=0
for key in MINIMAX_API_KEY DEEPSEEK_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY; do
  if [[ -n "${!key:-}" ]]; then
    _has_llm=1
    break
  fi
done
if [[ "$_has_llm" -eq 0 ]]; then
  echo "skip: no LLM API key in env (MINIMAX/DEEPSEEK/OPENAI/ANTHROPIC)"
  exit 0
fi

QUICK=0
for arg in "$@"; do
  case "$arg" in
    --quick) QUICK=1 ;;
  esac
done

exec python3 - "$QUICK" <<'PY'
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from butler.gateway.message_handler import ButlerMessageHandler

QUICK = sys.argv[1] == "1"
OWNER = os.getenv("BUTLER_OWNER_WECHAT_ID", "owner-wechat-sim")
failures: list[str] = []


def run_case(
    name: str,
    msg: str,
    *,
    expect_any: tuple[str, ...] = (),
    reject_any: tuple[str, ...] = (),
) -> str:
    sk = f"wechat:{OWNER}:ext-sim-{time.time_ns()}"
    handler = ButlerMessageHandler(channel="gateway")
    print(f"\n== {name} ==")
    print(f"IN:  {msg}")
    t0 = time.time()
    out = handler.handle_message(msg, session_key=sk, platform="wechat", external_id=OWNER) or ""
    elapsed = time.time() - t0
    preview = out.replace("\n", " ")[:320]
    print(f"OUT ({elapsed:.1f}s): {preview}{'…' if len(out) > 320 else ''}")
    ok = True
    for needle in expect_any:
        if needle not in out:
            print(f"  FAIL: missing {needle!r}")
            ok = False
    for bad in reject_any:
        if bad in out:
            print(f"  FAIL: hallucination {bad!r}")
            ok = False
    if ok:
        print("  PASS")
    else:
        failures.append(name)
    return out


if QUICK:
    run_case("/诊断 MCP", "/诊断", expect_any=("MCP",))
    print(f"\next-wechat-sim: {'ALL PASS' if not failures else failures}")
    raise SystemExit(1 if failures else 0)

run_case(
    "EXT-4 GitHub 仓库列表",
    "列出我的 GitHub 仓库",
    expect_any=("WFXM", "仓库"),
    reject_any=("japanese-learning", "fake-repo"),
)
run_case(
    "EXT-4 GitHub issues",
    "列出 WFXM 的 issues",
    expect_any=("WFXM", "issue"),
    reject_any=("japanese-learning",),
)
run_case(
    "EXT-2 Todoist 项目",
    "用 Todoist 列出所有项目",
    expect_any=("Todoist", "项目"),
    reject_any=("japanese-learning", "示例项目A"),
)
run_case(
    "/诊断 Extension Verify",
    "/诊断",
    expect_any=("Extension Verify", "github-readonly"),
)

print(f"\next-wechat-sim: {'ALL PASS' if not failures else failures}")
raise SystemExit(1 if failures else 0)
PY
