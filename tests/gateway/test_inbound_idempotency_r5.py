"""R5-9: inbound idempotency reset wired to /new boundary."""

from __future__ import annotations

import pytest

from butler.gateway import inbound_idempotency as ii


@pytest.fixture(autouse=True)
def _reset_seen():
    ii.reset_session()
    yield
    ii.reset_session()


@pytest.mark.unit
def test_reset_session_clears_seen_bucket():
    sk = "sess-r5"
    first = ii.check_and_reserve_inbound(sk, "ext-1")
    assert first.accept is True
    ii.reset_session(sk)
    again = ii.check_and_reserve_inbound(sk, "ext-1")
    assert again.accept is True


@pytest.mark.unit
def test_new_session_boundary_resets_idempotency():
    from types import SimpleNamespace

    from butler.session.new_session import clear_session_boundary_memory

    sk = "boundary-r5"
    assert ii.check_and_reserve_inbound(sk, "eid-99").accept is True
    ii.complete_inbound(sk, "eid-99")
    blocked = ii.check_and_reserve_inbound(sk, "eid-99")
    assert blocked.accept is False
    orch = SimpleNamespace(_post_session_pairs_extracted={})
    clear_session_boundary_memory(orch, sk)
    assert ii.check_and_reserve_inbound(sk, "eid-99").accept is True
