"""Claude Code session-end 检测：今日缺班次卡则提醒；strict 模式为 hard gate。

Hook 调用方式（CC 协议 Stop hook）：

```json
{
  "hooks": {
    "Stop": [
      {
        "command": "BLACKBOARD_STRICT=1 python3 -m butler.blackboard.integrations.claude_session_end"
      }
    ]
  }
}
```

模块 __main__ 入口：
- 默认（不设 `BLACKBOARD_STRICT`）：缺卡时 stderr 写提醒并 exit 0（不阻断）。
- strict 模式（`BLACKBOARD_STRICT=1`）：
  - 缺卡 → stderr 提醒 + exit 2（阻断）。
  - 有卡 → 自动找今日最新卡，跑 `butler main blackboard validate`；
    通过则 exit 0，失败则 exit 2。

环境变量：
- `BLACKBOARD_AGENT` — 哪个 agent 在跑班次；默认 `claude-code`。
- `BLACKBOARD_STRICT` — `1` 启用 strict hard gate；其它值视为关闭。
- `BLACKBOARD_ROOT` — 黑板根目录（paths 模块自动读取）。
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date as date_cls

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


def _find_latest_today_shift(agent: str, date: str | None = None) -> str | None:
    """返回今日该 agent 的最新 shift_id（stem，按文件名排序的末位）；无则 None。"""
    today = date or date_cls.today().isoformat()
    shifts_dir = bb_paths.SHIFTS_DIR
    if not shifts_dir.is_dir():
        return None
    prefix = f"{today}-{agent}-"
    stems = sorted(
        p.stem for p in shifts_dir.iterdir()
        if p.name.startswith(prefix) and p.suffix == ".md"
    )
    return stems[-1] if stems else None


def _validate_shift(shift_id: str) -> int:
    """跑 `butler main blackboard validate --shift-id <id>`；返回其 exit code。"""
    r = subprocess.run(
        [sys.executable, "-m", "butler.main", "blackboard",
         "validate", "--shift-id", shift_id],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"[blackboard] ✗ validate 失败：{shift_id}", file=sys.stderr)
        if r.stdout:
            print(r.stdout, file=sys.stderr)
        if r.stderr:
            print(r.stderr, file=sys.stderr)
    return r.returncode


def main() -> int:
    agent = os.environ.get("BLACKBOARD_AGENT", "claude-code")
    strict = os.environ.get("BLACKBOARD_STRICT", "0") == "1"

    msg = check_today_shift(agent=agent)
    if msg:
        print(msg, file=sys.stderr)
        return 2 if strict else 0

    if strict:
        latest = _find_latest_today_shift(agent=agent)
        if latest is None:
            print(f"[blackboard] ✗ 未找到今日班次卡（agent={agent}）", file=sys.stderr)
            return 2
        rc = _validate_shift(latest)
        if rc == 0:
            print(f"[blackboard] ✓ {latest}", file=sys.stderr)
            return 0
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())