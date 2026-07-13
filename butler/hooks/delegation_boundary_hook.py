"""P1 #4 — content vs dev 委派边界 hook。

读 stdin JSON（tool_name + tool_input）+ os.environ["BUTLER_AGENT_ROLE"]，
按 projects/<slug>/.butler/permissions.yaml delegation.<role>.write_allow/deny
判定；deny 优先于 allow；越界 exit(2) + stderr + audit log。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_LOG = REPO_ROOT / "butler" / "audit" / "delegation-violations.log"


def main() -> int:
    """hook 入口：读 stdin，判定，返回 exit code。"""
    # 占位实现：先总是放行，让 TDD 跑通；Task 3 实现真实逻辑。
    try:
        json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0  # stdin 不是 JSON 时放行（让 Claude Code 不被破坏）
    return 0


if __name__ == "__main__":
    sys.exit(main())
