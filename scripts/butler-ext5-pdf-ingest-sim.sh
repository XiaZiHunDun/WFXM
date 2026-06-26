#!/usr/bin/env bash
# EXT-5 phrase card #3a — PDF attachment + ingest (handler sim, no iLink).
#
# Simulates:
#   1) WeChat PDF attachment → inbound_media text
#   2) 「把这份 PDF 转成 Markdown 放进记忆」
#
# Usage:
#   bash scripts/butler-ext5-pdf-ingest-sim.sh
#
# Skip (exit 0): BUTLER_EXTENSION_WECHAT_SIM=0 or no LLM key.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

export BUTLER_MCP_MAX_SERVERS="${BUTLER_MCP_MAX_SERVERS:-4}"

if [[ "${BUTLER_EXTENSION_WECHAT_SIM:-1}" == "0" ]]; then
  echo "skip: BUTLER_EXTENSION_WECHAT_SIM=0"
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

PDF="$ROOT/tests/fixtures/ext5/sample.pdf"
if [[ ! -f "$PDF" ]]; then
  echo "FAIL: missing $PDF"
  exit 1
fi

exec python3 - "$PDF" <<'PY'
import os
import sys
import time
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))

from butler.gateway.inbound_media import build_inbound_user_text
from butler.gateway.message_handler import ButlerMessageHandler
from butler.gateway.outbound_files import expand_reply_with_wechat_attachments
from butler.gateway.platforms.types import MessageEvent, MessageType, SessionSource
from butler.gateway.wechat_scenario_sim import evaluation_reply_text

PDF = Path(sys.argv[1]).resolve()
OWNER = os.getenv("BUTLER_OWNER_WECHAT_ID", "owner-wechat-sim")
SESSION = f"wechat:{OWNER}:ext5-pdf-{time.time_ns()}"
WS = ROOT / "projects/LingWen1"
handler = ButlerMessageHandler(channel="gateway")
failures: list[str] = []


def run(name: str, msg: str, *, expect_any=(), reject_any=()) -> str:
    print(f"\n== {name} ==")
    preview_in = msg.replace("\n", " ")[:180]
    print(f"IN:  {preview_in}{'…' if len(msg) > 180 else ''}")
    t0 = time.time()
    raw = handler.handle_message(msg, session_key=SESSION, platform="wechat", external_id=OWNER) or ""
    out = evaluation_reply_text(
        handler,
        owner_id=OWNER,
        session_key=SESSION,
        reply=expand_reply_with_wechat_attachments(raw),
        tools=[],
    )
    elapsed = time.time() - t0
    print(f"OUT ({elapsed:.1f}s): {out.replace(chr(10), ' ')[:420]}…")
    ok = True
    if expect_any and not any(n in out or n in raw for n in expect_any):
        print(f"  FAIL: need any of {expect_any!r}")
        ok = False
    for bad in reject_any:
        if bad in out or bad in raw:
            print(f"  FAIL: unwanted {bad!r}")
            ok = False
    if ok:
        print("  PASS")
    else:
        failures.append(name)
    return out


def ingest_has_pdf_marker() -> bool:
    for p in WS.glob(".butler/ingest/**/*.md"):
        try:
            body = p.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        if "ext-5 fixture" in body or "ingest sim" in body or "pdf" in body:
            return True
    return False


run("/切换 灵文1号", "/切换 灵文1号", expect_any=("灵文1号",))

ev = MessageEvent(
    text="",
    message_type=MessageType.DOCUMENT,
    source=SessionSource(platform="wechat", chat_id=OWNER),
    media_urls=[str(PDF)],
    media_types=["application/pdf"],
)
pdf_inbound = build_inbound_user_text(ev).strip()
if not pdf_inbound or "EXT-5 fixture" not in pdf_inbound:
    print("FAIL: build_inbound_user_text did not extract PDF text")
    raise SystemExit(1)
print("  OK: inbound_media extracted PDF text")

run(
    "EXT-5 #3a PDF 附件入站",
    pdf_inbound,
    expect_any=("已完成", "ingest", "验收", "代理"),
    reject_any=("DEV_VERIFY_GATE", "未通过验证"),
)

run(
    "EXT-5 #3a 放进记忆",
    "把这份 PDF 转成 Markdown 放进记忆",
    expect_any=("ingest", "已完成", "记忆", "Markdown"),
    reject_any=("DEV_VERIFY_GATE", "未通过验证", "butler_remember", "长期记忆太短"),
)

if not ingest_has_pdf_marker():
    print("FAIL: no .butler/ingest/*.md with PDF/fixture content")
    failures.append("ingest_file_check")
else:
    print("\n  OK: .butler/ingest/ has markdown from PDF path")

print(f"\next5-pdf-ingest-sim: {'ALL PASS' if not failures else failures}")
raise SystemExit(1 if failures else 0)
PY
