#!/usr/bin/env python3
"""Phase 4 live probe — real handler + 灵文1号 + owner session (no iLink)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Load .env
env_path = ROOT / ".env"
if env_path.is_file():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

from butler.gateway.message_handler import ButlerMessageHandler  # noqa: E402

OWNER = os.getenv("BUTLER_OWNER_WECHAT_ID", "owner-live-probe")
SK = f"wechat:{OWNER}:phase4-probe-{int(time.time())}"


def run_case(name: str, msg: str, *, expect_sub: str | None = None, reject_sub: str | None = None) -> bool:
    handler = ButlerMessageHandler(channel="gateway")
    print(f"\n=== {name} ===")
    print(f"IN: {msg[:120]}")
    out = handler.handle_message(msg, session_key=SK, platform="wechat", external_id=OWNER) or ""
    preview = out.replace("\n", " ")[:280]
    print(f"OUT: {preview}{'…' if len(out) > 280 else ''}")
    ok = True
    if expect_sub and expect_sub not in out:
        print(f"FAIL: expected substring {expect_sub!r}")
        ok = False
    if reject_sub and reject_sub in out:
        print(f"FAIL: rejected substring present {reject_sub!r}")
        ok = False
    print("PASS" if ok else "FAIL")
    return ok


def main() -> int:
    cases = [
        ("B0 /状态", "/状态", "灵文", None),
        ("A5 /成本", "/成本", "会话成本", None),
        ("M1 /诊断", "/诊断", "诊断", None),
        ("D3-6 /经验挖掘", "/经验挖掘", "经验挖掘", None),
        ("RT /定时", "/定时", "factory-status", None),
        ("A3 mutating拒", "/运行 publish-archive", None, "已执行"),
        ("B1 维护态", "当前灵文1号是什么阶段？请读 workflow_state 后摘要，并建议今天适合跑哪个只读巡检。", "COMPLETE", None),
    ]
    passed = 0
    for name, msg, expect_sub, reject_sub in cases:
        if run_case(name, msg, expect_sub=expect_sub, reject_sub=reject_sub):
            passed += 1
    print(f"\n=== Summary: {passed}/{len(cases)} passed ===")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
