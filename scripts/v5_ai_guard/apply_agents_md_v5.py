#!/usr/bin/env python3
"""Idempotent patch: insert production vs archive section in butler-v5/AGENTS.md."""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "## 0. 三层事实（生产 vs 脚手架）"

SECTION = """
## 0. 三层事实（生产 vs 脚手架）

| 层 | 文档/代码 | Agent 怎么用 |
| --- | --- | --- |
| **生产** | `docs/architecture/v5-production-architecture-2026-08.md` + `apps/api` + `packages/runtime` + `packages/persistence` | 改功能、查调用链 |
| **脚手架（未接线）** | `packages/application/_archive/`、`packages/infrastructure/_archive/` | 不要当已实现；不要用其单测声称能力已交付 |
| **目标架构** | `DESIGN.md`、Policy/ScopedGrant/Sandbox | 规划用，不等于生产已有 |

**修改 butler-v5/ 后必跑：** `cd butler-v5 && pnpm test`

> §一 以下 Effect-TS 包表描述的是**目标架构**；生产 delivery shell 为 async/await + RunEngine，见生产架构文档。

---
"""


def main() -> int:
    repo = Path(__file__).resolve().parent.parent.parent
    target = repo / "butler-v5" / "AGENTS.md"
    if not target.is_file():
        print(f"ERROR: missing {target}", file=sys.stderr)
        return 1

    text = target.read_text(encoding="utf-8")
    if MARKER in text:
        print("SKIP: butler-v5/AGENTS.md already has section 0")
        return 0

    anchor = "> 设计参考：[`DESIGN.md`](DESIGN.md)\n\n---\n"
    if anchor not in text:
        print("ERROR: insert anchor not found in AGENTS.md", file=sys.stderr)
        return 1

    text = text.replace(anchor, anchor + SECTION.strip() + "\n\n", 1)
    target.write_text(text, encoding="utf-8")
    print("OK: inserted section 0 into butler-v5/AGENTS.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
