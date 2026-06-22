"""WeChat owner scenario sim — manifest load + evaluation (no live LLM)."""

from __future__ import annotations

import pytest

from butler.gateway.wechat_scenario_sim import (
    ScenarioCase,
    evaluate_scenario_case,
    load_wechat_scenario_manifest,
)


@pytest.mark.unit
def test_load_owner_scenario_manifest():
    manifest = load_wechat_scenario_manifest()
    assert manifest is not None
    ids = {t.id for t in manifest.tracks}
    assert "core" in ids
    assert "memory" in ids
    assert "search" in ids


@pytest.mark.unit
def test_evaluate_scenario_reply_and_tools():
    case = ScenarioCase(
        name="read",
        user_text="读文件",
        expect_reply_any=("灵文",),
        reject_reply_any=("/nonexistent/",),
        prefer_tools_any=("read_file",),
    )
    errors, warnings = evaluate_scenario_case(
        [], "无法读取 /nonexistent/", case,
    )
    assert errors
    errors2, _ = evaluate_scenario_case(
        ["read_file"], "灵文1号项目摘要", case,
    )
    assert not errors2


@pytest.mark.unit
def test_expect_reply_any_is_or_not_and():
    case = ScenarioCase(
        name="x",
        user_text="?",
        expect_reply_any=("foo", "bar"),
    )
    errors, _ = evaluate_scenario_case([], "has foo only", case)
    assert not errors
    errors2, _ = evaluate_scenario_case([], "neither", case)
    assert errors2


@pytest.mark.unit
def test_evaluate_scenario_strict_requires_preferred():
    case = ScenarioCase(
        name="search",
        user_text="搜竞品",
        prefer_tools_any=("web_search",),
        expect_reply_any=("AI",),
    )
    errors, warnings = evaluate_scenario_case([], "无工具", case, strict=True)
    assert errors
    errors2, _ = evaluate_scenario_case(
        [], "AI 写作助手列表", case, strict=True,
    )
    assert not errors2


@pytest.mark.unit
def test_verify_files_on_disk(tmp_path, monkeypatch):
    from butler.gateway import wechat_scenario_sim as mod
    from butler.gateway.wechat_scenario_sim import ScenarioCase

    ws = tmp_path / "proj"
    (ws / "docs").mkdir(parents=True)
    (ws / "docs" / "owner-sim-smoke.md").write_text("ok", encoding="utf-8")
    monkeypatch.setattr(mod, "_project_workspace", lambda _sk: ws)

    case = ScenarioCase(
        name="f",
        user_text="x",
        verify_files_exist=("docs/owner-sim-smoke.md",),
    )
    assert not mod._verify_files_on_disk(case, "any")
    case2 = ScenarioCase(name="f", user_text="x", verify_files_exist=("docs/missing.md",))
    assert mod._verify_files_on_disk(case2, "any")


@pytest.mark.unit
def test_sim_render_context_templates():
    from datetime import date

    from butler.gateway.wechat_scenario_sim import (
        ScenarioCase,
        make_sim_render_context,
        render_scenario_case,
    )

    ctx = make_sim_render_context(today=date(2026, 6, 22), run_ns=12345)
    assert ctx.sim_smoke_file == "owner-sim-smoke-2026-06-22.md"
    case = ScenarioCase(
        name="w",
        user_text="写 {sim_smoke_file} 日期 {sim_date}",
        verify_files_exist=("docs/{sim_smoke_file}",),
    )
    live = render_scenario_case(case, ctx)
    assert "owner-sim-smoke-2026-06-22.md" in live.user_text
    assert live.verify_files_exist == ("docs/owner-sim-smoke-2026-06-22.md",)


@pytest.mark.unit
def test_cleanup_track_artifacts(tmp_path, monkeypatch):
    from butler.gateway import wechat_scenario_sim as mod
    from butler.gateway.wechat_scenario_sim import (
        ScenarioTrack,
        SimRenderContext,
        make_sim_render_context,
    )

    ws = tmp_path / "proj"
    docs = ws / "docs"
    docs.mkdir(parents=True)
    old = docs / "owner-sim-smoke-2026-06-20.md"
    old.write_text("old", encoding="utf-8")
    monkeypatch.setattr(mod, "_project_workspace", lambda _sk: ws)

    track = ScenarioTrack(
        id="delegate",
        title="t",
        cleanup_globs=("docs/owner-sim-smoke*.md",),
        cases=(),
    )
    ctx = make_sim_render_context(today=__import__("datetime").date(2026, 6, 22))
    removed = mod._cleanup_track_artifacts(track, "sk", ctx)
    assert "docs/owner-sim-smoke-2026-06-20.md" in removed
    assert not old.exists()


@pytest.mark.unit
def test_forbid_tools_hard_fail():
    case = ScenarioCase(
        name="github",
        user_text="列仓库",
        forbid_tools=("web_fetch",),
    )
    errors, _ = evaluate_scenario_case(["web_fetch"], "ok", case)
    assert errors
