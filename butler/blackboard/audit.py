"""Audit 查询：班次↔任务追溯。"""

from __future__ import annotations

from butler.blackboard.shift_io import list_shift_cards
from butler.blackboard.task_io import load_claim


def audit_task(task_id: str) -> str:
    """输出 task_id 相关的所有班次卡（按时间序）。"""
    safe = task_id.replace("#", "%23").replace("/", "_")
    relevant_cards = [
        c for c in list_shift_cards()
        if c.claim_ref and safe in c.claim_ref
    ]
    relevant_cards.sort(key=lambda c: c.shift_id)

    claim_note = ""
    try:
        c = load_claim(task_id)
        claim_note = f"claim.status={c.status.value}, shift_refs={c.shift_refs}"
    except FileNotFoundError:
        claim_note = "(no claim file)"

    lines = [f"# Audit: {task_id}", "", f"## Claim: {claim_note}", "", "## Shifts:"]
    for card in relevant_cards:
        lines.append(f"- {card.shift_id} ({card.agent.value}): {card.intent}")
        for p in card.produced:
            lines.append(f"  - produced: {p.type} {p.ref} {p.summary or ''}")
        if card.next_shift_recommendation:
            lines.append(
                f"\n## Next shift recommendation: agent={card.next_shift_recommendation.agent} "
                f"reason={card.next_shift_recommendation.reason}"
            )
    return "\n".join(lines) + "\n"