#!/usr/bin/env python3
"""Idempotent patch: prepend Butler v5 banner to .cursorrules."""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "# === Butler v5 主线 (auto) ==="

BANNER = """# === Butler v5 主线 (auto) ===
# 产品主线：Butler v5（butler-v5/）。butler/ v4 已退役，仅只读/守卫兼容。
# 新会话前 30 秒：.blackboard/state.md → butler-v5/AGENTS.md → docs/architecture/v5-production-architecture-2026-08.md
# 改 butler-v5/ 后：cd butler-v5 && pnpm test
#
# 以下 Legacy v4 规则仍保留，直至 v4 完全只读归档。

"""


def main() -> int:
    repo = Path(__file__).resolve().parent.parent.parent
    target = repo / ".cursorrules"
    if not target.is_file():
        print(f"ERROR: missing {target}", file=sys.stderr)
        return 1

    text = target.read_text(encoding="utf-8")
    if MARKER in text:
        print("SKIP: .cursorrules already has v5 banner")
        return 0

    # Replace v4-only title if present
    text = text.replace(
        "# AI 行为规则 — WFXM / Butler v4\n",
        "# AI 行为规则 — WFXM\n",
        1,
    )
    target.write_text(BANNER + text, encoding="utf-8")
    print("OK: prepended v5 banner to .cursorrules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
