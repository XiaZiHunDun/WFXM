#!/usr/bin/env bash
# G1-11: WeChat core scenario via ButlerMessageHandler (no iLink).
# Subset of docs/guides/wechat-core-scenario.md steps 1–3 + /诊断.
#
# Usage:
#   bash scripts/butler-wechat-core-sim.sh
#   bash scripts/butler-wechat-core-sim.sh --quick   # /状态 + /诊断 only
#
# Skip (exit 0): BUTLER_WECHAT_CORE_SIM=0 or no LLM API key.
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

if [[ "${BUTLER_WECHAT_CORE_SIM:-1}" == "0" ]]; then
  echo "skip: BUTLER_WECHAT_CORE_SIM=0"
  exit 0
fi

_has_llm=0
for key in MINIMAX_API_KEY MINIMAX_CN_API_KEY DEEPSEEK_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY; do
  if [[ -n "${!key:-}" ]]; then
    _has_llm=1
    break
  fi
done
if [[ "$_has_llm" -eq 0 ]]; then
  echo "skip: no LLM API key in env"
  exit 0
fi

QUICK=0
for arg in "$@"; do
  case "$arg" in
    --quick) QUICK=1 ;;
  esac
done

exec python3 - "$QUICK" <<'PY'
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from butler.gateway.message_handler import ButlerMessageHandler

QUICK = sys.argv[1] == "1"
OWNER = os.getenv("BUTLER_OWNER_WECHAT_ID", "owner-wechat-core-sim")
PROJECT = os.getenv("BUTLER_WECHAT_CORE_SIM_PROJECT", "灵文1号")
failures: list[str] = []


def run_step(
    handler: ButlerMessageHandler,
    session_key: str,
    name: str,
    msg: str,
    *,
    expect_any: tuple[str, ...] = (),
    reject_any: tuple[str, ...] = (),
) -> str:
    print(f"\n== {name} ==")
    print(f"IN:  {msg}")
    t0 = time.time()
    out = handler.handle_message(
        msg,
        session_key=session_key,
        platform="wechat",
        external_id=OWNER,
    ) or ""
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
            print(f"  FAIL: unexpected {bad!r}")
            ok = False
    if ok:
        print("  PASS")
    else:
        failures.append(name)
    return out


sk = f"wechat:{OWNER}:core-sim-{time.time_ns()}"
handler = ButlerMessageHandler(channel="gateway")

run_step(
    handler,
    sk,
    "步骤1 /状态",
    "/状态",
    expect_any=("项目", "管家", "Butler", "Provider", "当前"),
)

if QUICK:
    run_step(handler, sk, "/诊断", "/诊断", expect_any=("诊断", "Butler"))
    print(f"\nwechat-core-sim: {'ALL PASS' if not failures else failures}")
    raise SystemExit(1 if failures else 0)

run_step(
    handler,
    sk,
    f"步骤2 /切换 {PROJECT}",
    f"/切换 {PROJECT}",
    expect_any=(PROJECT, "切换", "项目"),
)

run_step(
    handler,
    sk,
    "步骤2b /状态 确认项目",
    "/状态",
    expect_any=(PROJECT,),
)

run_step(
    handler,
    sk,
    "步骤3 读 project.yaml",
    "请读取当前项目 project.yaml 的前 15 行，用纯文字摘要，必须包含 name 字段的值",
    expect_any=(PROJECT, "灵文"),
    reject_any=("/nonexistent/", "无法访问"),
)

run_step(
    handler,
    sk,
    "步骤6 /诊断",
    "/诊断",
    expect_any=("诊断", "Butler", "记忆"),
)

print(f"\nwechat-core-sim: {'ALL PASS' if not failures else failures}")
raise SystemExit(1 if failures else 0)
PY
