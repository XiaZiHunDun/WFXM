"""audit：班次↔任务追溯查询。"""

from __future__ import annotations

from butler.blackboard.audit import audit_task
from butler.blackboard.shift_io import write_shift_card
from butler.blackboard.task_io import save_claim
from butler.blackboard.schema import (
    Claim,
    ClaimStatus,
    SessionWindow,
    ShiftCard,
)


def _card(shift_id: str, claim_ref: str | None = None) -> ShiftCard:
    return ShiftCard(
        shift_id=shift_id,
        agent="claude-code",
        session_window=SessionWindow(
            start=shift_id[:10] + "T09:00:00+08:00",
            end=shift_id[:10] + "T11:00:00+08:00",
        ),
        intent="audit test",
        scope=["tests/"],
        read_at_start=[".blackboard/README.md"],
        claim_ref=claim_ref,
        schema_version=1,
    )


def test_audit_task_with_claim_refs(tmp_blackboard):
    write_shift_card(_card("2026-07-13-claude-code-001", "tasks/claims/P1-%234.yaml"), body="")
    write_shift_card(_card("2026-07-13-claude-code-002", "tasks/claims/P1-%234.yaml"), body="")
    write_shift_card(_card("2026-07-13-claude-code-003", "tasks/claims/P2-%2310.yaml"), body="")
    save_claim(Claim(task_id="P1-#4", claimed_by="claude-code",
                     claimed_at="2026-07-13T09:00:00+08:00",
                     status=ClaimStatus.DONE,
                     shift_refs=["2026-07-13-claude-code-001", "2026-07-13-claude-code-002"]))
    result = audit_task("P1-#4")
    assert "2026-07-13-claude-code-001" in result
    assert "2026-07-13-claude-code-002" in result
    assert "2026-07-13-claude-code-003" not in result