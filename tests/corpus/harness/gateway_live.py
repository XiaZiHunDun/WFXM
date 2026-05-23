"""L3 live corpus — resolve meta.live_smoke_ids to catalog entries."""

from __future__ import annotations

from typing import Any

from tests.corpus.harness.gateway_catalog import apply_catalog_setup, catalog_by_id
from tests.corpus.harness.gateway_meta import category_to_dimension, load_gateway_meta

# Setups that only work with mocked LLM scripts (skip in live smoke)
_LIVE_INCOMPATIBLE_SETUPS = frozenset(
    {
        "prior_chat_turn",
        "prior_chat_then_new",
        "prior_delegate_create_hello",
        "u1_report_u2_empty",
    }
)


def load_live_smoke_ids() -> list[str]:
    meta = load_gateway_meta()
    l3 = (meta.get("catalog_tiers") or {}).get("l3_live") or {}
    return [str(x) for x in (l3.get("live_smoke_ids") or [])]


def validate_live_smoke_ids() -> list[str]:
    errors: list[str] = []
    by_id = catalog_by_id()
    for cid in load_live_smoke_ids():
        if cid not in by_id:
            errors.append(f"live_smoke_ids: unknown catalog id {cid}")
            continue
        entry = by_id[cid]
        setup = entry.get("setup")
        if setup in _LIVE_INCOMPATIBLE_SETUPS:
            errors.append(f"live_smoke_ids: {cid} uses mock-only setup {setup!r}")
    return errors


def live_smoke_entries() -> list[dict[str, Any]]:
    by_id = catalog_by_id()
    return [by_id[cid] for cid in load_live_smoke_ids() if cid in by_id]


def assert_live_response(entry: dict[str, Any], *, out: str) -> None:
    """Relaxed assertions for real LLM (subset of catalog expect)."""
    expect = entry.get("expect") or {}
    assert out and out.strip(), f"{entry['id']}: empty response"

    for token in expect.get("response_contains") or []:
        assert token in out, f"{entry['id']}: expected {token!r} in response"

    any_of = expect.get("response_contains_any") or []
    if any_of:
        assert any(t in out for t in any_of), (
            f"{entry['id']}: none of {any_of!r} in {out[:300]!r}"
        )

    for token in expect.get("response_excludes") or []:
        assert token not in out, f"{entry['id']}: excluded {token!r} present"

    max_lines = expect.get("response_max_lines")
    if max_lines is not None:
        lines = [ln for ln in out.splitlines() if ln.strip()]
        assert len(lines) <= int(max_lines), f"{entry['id']}: too many lines"


def live_dimension(entry: dict[str, Any]) -> str:
    return category_to_dimension(str(entry.get("category") or "")) or ""
