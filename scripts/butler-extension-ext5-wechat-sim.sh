#!/usr/bin/env bash
# EXT-5 WeChat handler sim (no iLink) — MarkItDown MCP verify phrases.
#
# Usage:
#   bash scripts/butler-extension-ext5-wechat-sim.sh
#   bash scripts/butler-extension-ext5-wechat-sim.sh --quick   # /诊断 only
#
# Skip (exit 0): BUTLER_EXTENSION_WECHAT_SIM=0, MCP off, or no LLM key.
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

# firecrawl + todoist + github + markitdown → need ≥4 slots (default env is 3).
export BUTLER_MCP_MAX_SERVERS="${BUTLER_MCP_MAX_SERVERS:-4}"

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
  echo "skip: no LLM API key in env"
  exit 0
fi

QUICK=0
for arg in "$@"; do
  case "$arg" in
    --quick) QUICK=1 ;;
  esac
done

FIXTURE="$ROOT/tests/fixtures/ext5/sample.txt"
if [[ ! -f "$FIXTURE" ]]; then
  echo "FAIL: missing fixture $FIXTURE"
  exit 1
fi

echo "EXT-5 wechat sim fixture: $FIXTURE"
echo "BUTLER_MCP_MAX_SERVERS=${BUTLER_MCP_MAX_SERVERS}"
bash "$ROOT/scripts/butler-extension-ext5-preflight.sh" || true

PROJECT_WS="$ROOT/projects/LingWen1"
SIM_FIXTURE_REL="docs/ext5-fixture-sample.txt"
SIM_FIXTURE="$PROJECT_WS/$SIM_FIXTURE_REL"
mkdir -p "$(dirname "$SIM_FIXTURE")"
cp -f "$FIXTURE" "$SIM_FIXTURE"
rm -f "$PROJECT_WS/docs/ext5-fixture-sample.md"
export EXT5_SIM_FIXTURE_REL="$SIM_FIXTURE_REL"
export EXT5_SIM_FIXTURE_PATH="$SIM_FIXTURE"

echo "EXT-5: prewarm markitdown MCP (uvx cold start may take ~60s)..."
PYTHONPATH="$ROOT" BUTLER_MCP_MAX_SERVERS="${BUTLER_MCP_MAX_SERVERS}" python3 - <<'PY' || true
from butler.mcp.registry_hook import mcp_status_lines
for line in mcp_status_lines("ext5-prewarm"):
    if "markitdown" in line.lower():
        print(line)
PY

exec python3 - "$QUICK" "$SIM_FIXTURE" "$SIM_FIXTURE_REL" <<'PY'
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(os.getcwd())
sys.path.insert(0, str(ROOT))

from butler.gateway.message_handler import ButlerMessageHandler
from butler.gateway.outbound_files import expand_reply_with_wechat_attachments
from butler.gateway.wechat_scenario_sim import evaluation_reply_text

QUICK = sys.argv[1] == "1"
FIXTURE = Path(sys.argv[2]).resolve()
FIXTURE_REL = sys.argv[3]
OWNER = os.getenv("BUTLER_OWNER_WECHAT_ID", "owner-wechat-sim")
failures: list[str] = []
SESSION_SK = f"wechat:{OWNER}:ext5-sim-{time.time_ns()}"


def run_case(
    name: str,
    msg: str,
    *,
    expect_any: tuple[str, ...] = (),
    reject_any: tuple[str, ...] = (),
    session_key: str | None = None,
    verify_files: tuple[tuple[Path, tuple[str, ...]], ...] = (),
) -> str:
    sk = session_key or f"wechat:{OWNER}:ext5-sim-{time.time_ns()}"
    handler = ButlerMessageHandler(channel="gateway")
    print(f"\n== {name} ==")
    print(f"IN:  {msg}")
    t0 = time.time()
    raw = handler.handle_message(msg, session_key=sk, platform="wechat", external_id=OWNER) or ""
    out = expand_reply_with_wechat_attachments(raw)
    out = evaluation_reply_text(
        handler,
        owner_id=OWNER,
        session_key=sk,
        reply=out,
        tools=[],
    )
    elapsed = time.time() - t0
    preview = raw.replace("\n", " ")[:400]
    print(f"OUT ({elapsed:.1f}s): {preview}{'…' if len(raw) > 400 else ''}")
    ok = True
    for needle in expect_any:
        if needle not in out:
            print(f"  FAIL: missing {needle!r}")
            ok = False
    for bad in reject_any:
        if bad in out or bad in raw:
            print(f"  FAIL: unwanted {bad!r}")
            ok = False
    for fpath, needles in verify_files:
        if not fpath.is_file():
            print(f"  FAIL: missing file {fpath}")
            ok = False
            continue
        body = fpath.read_text(encoding="utf-8", errors="replace")
        for needle in needles:
            if needle not in body:
                print(f"  FAIL: {fpath.name} missing {needle!r}")
                ok = False
    if ok:
        print("  PASS")
    else:
        failures.append(name)
    return raw


if QUICK:
    run_case(
        "/诊断 EXT-5",
        "/诊断 详细",
        expect_any=("Extension Verify", "markitdown"),
    )
    print(f"\next5-wechat-sim: {'ALL PASS' if not failures else failures}")
    raise SystemExit(1 if failures else 0)

file_uri = FIXTURE.as_uri()
handler = ButlerMessageHandler(channel="gateway")
run_case("/切换 灵文1号", "/切换 灵文1号", session_key=SESSION_SK)
run_case(
    "/诊断 Extension + markitdown",
    "/诊断 详细",
    expect_any=("Extension Verify", "markitdown"),
    session_key=SESSION_SK,
)
run_case(
    "EXT-5 manifest 话术",
    f"请 read_file 读取 {FIXTURE}，用 MarkItDown 或等价方式转成 Markdown 并写入 docs/ext5-fixture-sample.md",
    verify_files=((FIXTURE.parent / "ext5-fixture-sample.md", ("EXT-5 fixture",)),),
    reject_any=("japanese-learning",),
    session_key=SESSION_SK,
)
run_case(
    "EXT-5 file URI 提示",
    f"请用 MarkItDown MCP 转换这个文件并摘要第一句：{file_uri}",
    expect_any=("EXT-5", "fixture", "MarkItDown"),
    session_key=SESSION_SK,
)

print(f"\next5-wechat-sim: {'ALL PASS' if not failures else failures}")
raise SystemExit(1 if failures else 0)
PY
