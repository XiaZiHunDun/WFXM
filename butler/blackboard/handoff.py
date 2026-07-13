"""交接包：给下一班 Agent 的一屏快照。"""

from __future__ import annotations

from butler.blackboard import paths as bb_paths
from butler.blackboard.shift_io import list_shift_cards


def build_handoff(last_n: int = 3) -> str:
    """返回交接包 markdown：state.md 全文 + 最近 N 张班次卡的 (intent, unresolved)。"""
    cards = list_shift_cards()
    recent = cards[-last_n:] if cards else []

    lines: list[str] = []
    lines.append("# 交接包（Handoff Package）")
    lines.append("")
    lines.append("## 第一步：读以下文件")
    lines.append("")
    lines.append("- `.blackboard/README.md`（规约契约）")
    lines.append("- `.blackboard/state.md`（当前快照，附后）")
    for c in reversed(recent):
        lines.append(f"- `.blackboard/shifts/{c.shift_id}.md`（上一班次详情）")
    lines.append("")
    lines.append("## state.md 当前快照")
    lines.append("")
    lines.append("```markdown")
    lines.append(bb_paths.STATE_PATH.read_text(encoding="utf-8"))
    lines.append("```")
    lines.append("")
    lines.append("## 最近班次关键字段")
    lines.append("")
    for c in reversed(recent):
        lines.append(f"### {c.shift_id} ({c.agent.value})")
        lines.append(f"- intent: {c.intent}")
        if c.unresolved:
            lines.append("- unresolved:")
            for u in c.unresolved:
                lines.append(f"  - {u}")
        if c.next_shift_recommendation:
            nsr = c.next_shift_recommendation
            lines.append(f"- next_shift_recommendation: agent={nsr.agent}, reason={nsr.reason}")
        lines.append("")
    return "\n".join(lines)