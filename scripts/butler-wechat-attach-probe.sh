#!/usr/bin/env bash
# Handler-level WeChat md/txt attach probe — no gateway process, no LLM.
# Verifies /详细、/诊断 详细、委派完成推送 在 wechat 平台生成 exports/ 路径行。
#
# Usage: bash scripts/butler-wechat-attach-probe.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-$ROOT}:$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  # shellcheck source=scripts/lib/butler-source-env.sh
  source "$ROOT/scripts/lib/butler-source-env.sh"
  butler_source_env "$ROOT/.env" 2>/dev/null || true
fi

exec python3 - <<'PY'
from __future__ import annotations

import os
import re
import time
from unittest.mock import patch

from butler.gateway.message_handler import ButlerMessageHandler
from butler.gateway.outbound_files import is_deliverable_export_file
from butler.gateway.wechat_text_export import build_delegate_completion_message, wechat_attach_brief_chars
from butler.report import AgentReport, cache_report, clear_report_cache

os.environ.setdefault("BUTLER_EXPORT_SEND_WECHAT_FILE", "1")
os.environ.setdefault("BUTLER_WECHAT_ATTACH_DETAIL", "1")
os.environ.setdefault("BUTLER_WECHAT_ATTACH_DIAGNOSTIC", "1")
os.environ.setdefault("BUTLER_WECHAT_ATTACH_DELEGATE", "1")

ns = time.time_ns()
owner = f"attach-probe-{ns}"
sk = f"wechat:{owner}:attach-probe"
handler = ButlerMessageHandler(channel="gateway")
errors: list[str] = []


def has_export_path(text: str) -> bool:
    for line in (text or "").splitlines():
        candidate = line.strip()
        if candidate.startswith("/") and is_deliverable_export_file(candidate):
            return True
    return False


def chat_body_before_path(text: str) -> str:
    lines: list[str] = []
    for line in (text or "").splitlines():
        candidate = line.strip()
        if candidate.startswith("/") and is_deliverable_export_file(candidate):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def ends_with_brief_truncation(text: str) -> bool:
    return bool(re.search(r"\n…\s*$", (text or "").rstrip()))


def check(name: str, text: str, *, need_attach: bool, need_hint: bool = True) -> None:
    if not text or not str(text).strip():
        errors.append(f"{name}: empty reply")
        return
    if need_attach and not has_export_path(text):
        errors.append(f"{name}: missing deliverable exports/ path line")
    if need_hint and "附件" not in text:
        errors.append(f"{name}: missing 附件 hint")
    if need_attach:
        body = chat_body_before_path(text)
        cap = wechat_attach_brief_chars()
        main = body.split("（完整")[0].strip() if "（完整" in body else body
        if len(main) > cap + 5 and "…" not in body:
            errors.append(f"{name}: expected brief truncation (…)")
        if len(body) > cap + 100:
            errors.append(f"{name}: chat brief too long ({len(body)} chars)")


print("=== WeChat attach probe (handler + Owner session) ===")
print(f"session: {sk}")

with patch("butler.gateway.owner_gate.is_gateway_owner", return_value=True):
    clear_report_cache()
    cache_report(
        AgentReport(
            headline="开发代理已完成任务",
            summary="验收摘要\n" + ("详细行 " * 120),
            success=True,
            task_id="task_attach_probe",
            changes=[],
        ),
        session_key=sk,
    )

    detail = handler._handle_command(
        "/详细",
        session_key=sk,
        platform="wechat",
        external_id=owner,
    )
    print("\n--- /详细 ---")
    print((detail or "")[:280])
    check("/详细", detail or "", need_attach=True)
    if "task_attach_probe" not in (detail or ""):
        errors.append("/详细: expected cached task_attach_probe in reply")

    diag_full = handler._handle_command(
        "/诊断 详细",
        session_key=sk,
        platform="wechat",
        external_id=owner,
    )
    print("\n--- /诊断 详细 ---")
    print((diag_full or "")[:280])
    check("/诊断 详细", diag_full or "", need_attach=True)

    report = AgentReport(
        headline="开发代理已完成任务",
        summary="done " * 200,
        success=True,
        task_id="task_delegate_probe",
        changes=[],
    )
    delegate_msg = build_delegate_completion_message(report, platform="wechat")
    print("\n--- delegate completion ---")
    print(delegate_msg[:280])
    check("delegate completion", delegate_msg, need_attach=True)

    cli_diag = handler._handle_command(
        "/诊断 详细",
        session_key=sk,
        platform="cli",
        external_id=owner,
    )
    if has_export_path(cli_diag or ""):
        errors.append("cli /诊断 详细: should not embed export path")
    if ends_with_brief_truncation(cli_diag or ""):
        errors.append("cli /诊断 详细: should not truncate with …")

if errors:
    print("\nFAIL:")
    for err in errors:
        print(f"  - {err}")
    raise SystemExit(1)

print("\nOK: WeChat attach probe passed")
PY
