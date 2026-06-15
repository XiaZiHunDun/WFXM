"""Builtin tool orthogonality lint."""

from __future__ import annotations

import pytest

from butler.tools.orthogonality_lint import lint_builtin_tool_orthogonality


@pytest.mark.unit
def test_orthogonality_lint_runs():
    issues = lint_builtin_tool_orthogonality(threshold=0.99)
    assert isinstance(issues, list)


@pytest.mark.unit
def test_converged_tool_pairs_below_threshold():
    """已收敛工具对的 description cosine 应低于阈值。"""
    from butler.memory.embedding import cosine_similarity, get_embedder
    from butler.tools.registry import get_tool_definitions

    embedder = get_embedder()
    if embedder.model_id.startswith("hashing"):
        pytest.skip("hashing embedder — orthogonality not meaningful")

    by_name: dict[str, list[float]] = {}
    for defn in get_tool_definitions():
        fn = defn.get("function") if isinstance(defn.get("function"), dict) else {}
        name = str(fn.get("name") or "").strip()
        if not name:
            continue
        text = str(fn.get("description") or "").strip().lower()
        by_name[name] = embedder.embed(text)

    pairs_strict = (
        ("habit_checkin", "habit_stats"),
        ("list_reminders", "reminder_list_active"),
        ("git_add", "git_commit"),
        ("memo_search", "memo_update"),
        ("session_todos_write", "project_todos_write"),
        ("expense_search", "expense_delete"),
        ("git_status", "git_log"),
        ("git_diff", "git_log"),
        ("git_status", "git_diff"),
        ("registry_search_skills", "registry_install_skill"),
        ("registry_search_skills", "registry_propose_skill_install"),
        ("registry_propose_skill_install", "registry_install_skill"),
        ("contact_add", "contact_find"),
        ("habit_stats", "habit_list"),
    )
    mcp_pairs = (("mcp_catalog_search", "mcp_list_installed"),)
    pairs_domain = (
        ("expense_summary", "expense_list"),
    )
    threshold = 0.82
    domain_threshold = 0.88
    for a, b in pairs_strict:
        assert a in by_name and b in by_name, f"missing tool {a} or {b}"
        sim = cosine_similarity(by_name[a], by_name[b])
        assert sim < threshold, f"{a}↔{b} cosine={sim:.3f} still ≥ {threshold}"
    for a, b in mcp_pairs:
        if a not in by_name or b not in by_name:
            pytest.skip("MCP self-service tools not registered (BUTLER_MCP_ENABLED=0)")
        sim = cosine_similarity(by_name[a], by_name[b])
        assert sim < threshold, f"{a}↔{b} cosine={sim:.3f} still ≥ {threshold}"
    for a, b in pairs_domain:
        assert a in by_name and b in by_name, f"missing tool {a} or {b}"
        sim = cosine_similarity(by_name[a], by_name[b])
        assert sim < domain_threshold, f"{a}↔{b} cosine={sim:.3f} still ≥ {domain_threshold}"
