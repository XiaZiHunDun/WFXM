"""task_io：backlog.yaml + claims/ 读写。"""

from __future__ import annotations

import pytest

from butler.blackboard.task_io import (
    load_backlog,
    save_backlog,
    load_claim,
    save_claim,
    list_claims,
)
from butler.blackboard.schema import (
    BacklogFile,
    BacklogTask,
    Claim,
    ClaimStatus,
    Priority,
    TaskStatus,
)


def test_backlog_roundtrip(tmp_blackboard):
    bf = BacklogFile(
        last_updated="2026-07-13T10:00:00+08:00",
        tasks=[
            BacklogTask(id="P1-#4", title="x", priority=Priority.P1, status=TaskStatus.OPEN),
        ],
    )
    save_backlog(bf)
    loaded = load_backlog()
    assert loaded.tasks[0].id == "P1-#4"
    assert loaded.last_updated == "2026-07-13T10:00:00+08:00"


def test_claim_roundtrip(tmp_blackboard):
    c = Claim(
        task_id="P1-#4",
        claimed_by="claude-code",
        claimed_at="2026-07-13T09:00:00+08:00",
        status=ClaimStatus.CLAIMED,
    )
    save_claim(c)
    loaded = load_claim("P1-#4")
    assert loaded.claimed_by == "claude-code"


def test_list_claims(tmp_blackboard):
    save_claim(Claim(task_id="P1-#4", claimed_by="claude-code",
                     claimed_at="2026-07-13T09:00:00+08:00",
                     status=ClaimStatus.CLAIMED))
    save_claim(Claim(task_id="P2-#10", claimed_by="cursor",
                     claimed_at="2026-07-13T10:00:00+08:00",
                     status=ClaimStatus.IN_PROGRESS))
    claims = list_claims()
    assert {c.task_id for c in claims} == {"P1-#4", "P2-#10"}


def test_load_claim_missing(tmp_blackboard):
    with pytest.raises(FileNotFoundError):
        load_claim("nope")