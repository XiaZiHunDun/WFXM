"""Claude Code session-end 检测：今日缺班次卡则提醒。

Hook 调用方式（CC 协议 Stop hook）：

```json
{
  "hooks": {
    "Stop": [
      {
        "command": "python3 -m butler.blackboard.integrations.claude_session_end"
      }
    ]
  }
}
```

模块 __main__ 入口：检查今天的班次卡；无则 stderr 写提醒并 exit 0（不阻断）。
"""

from __future__ import annotations

import os
import sys
from datetime import date as date_cls
from pathlib import Path

from butler.blackboard import paths as bb_paths


def check_today_shift(agent: str, date: str | None = None) -> str | None:
    """若今日该 agent 无班次卡，返回提醒字符串；否则 None。"""
    today = date or date_cls.today().isoformat()
    shifts_dir = bb_paths.SHIFTS_DIR
    if not shifts_dir.is_dir():
        return "[blackboard] 黑板未初始化；先跑 `butler blackboard init`"
    prefix = f"{today}-{agent}-"
    for p in shifts_dir.iterdir():
        if p.name.startswith(prefix) and p.suffix == ".md":
            return None
    return (
        f"[blackboard] ⚠ 今日缺班次卡（agent={agent}, date={today}）。\n"
        f"  请写 shifts/{today}-{agent}-NNN.md 后再退出；"
        f"详见 .blackboard/README.md。\n"
        f"  若会话无实质变更，可发 'human: no-op' 占位卡。"
    )


def main() -> int:
    agent = os.environ.get("BLACKBOARD_AGENT", "claude-code")
    msg = check_today_shift(agent=agent)
    if msg:
        print(msg, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())