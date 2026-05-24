"""Load and execute WeChat utterance_catalog scenarios (data-driven gateway tests)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import yaml

_LW_REAL_DIR = Path(__file__).resolve().parents[1] / "suites" / "wechat_real" / "lw_real"
_CATALOG_PATH = _LW_REAL_DIR / "utterance_catalog.yaml"
_REFERENCE_SMOKE_PATH = _LW_REAL_DIR / "reference_utterance_catalog.yaml"
_REFERENCE_STRICT_PATH = _LW_REAL_DIR / "reference_utterance_strict.yaml"
_MULTITURN_PATH = _LW_REAL_DIR / "utterance_multiturn_catalog.yaml"
_PRODUCTION_PATH = _LW_REAL_DIR / "production_utterance_catalog.yaml"


def _load_catalog_file(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows = data.get("utterance_catalog") or []
    if not isinstance(rows, list):
        raise ValueError(f"{path.name}: utterance_catalog must be a list")
    return rows


def _load_multiturn_file(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows = data.get("multiturn_catalog") or []
    if not isinstance(rows, list):
        raise ValueError(f"{path.name}: multiturn_catalog must be a list")
    return rows


def _is_executable_row(row: dict[str, Any]) -> bool:
    if row.get("runner") in ("legacy", "reference_smoke"):
        return False
    if row.get("kind") == "multi":
        return False
    return True


def load_production_strict_catalog() -> list[dict[str, Any]]:
    return [
        r
        for r in load_production_utterance_catalog()
        if r.get("quality") == "strict"
    ]


def load_main_utterance_catalog() -> list[dict[str, Any]]:
    return _load_catalog_file(_CATALOG_PATH)


def load_reference_smoke_catalog() -> list[dict[str, Any]]:
    return _load_catalog_file(_REFERENCE_SMOKE_PATH)


def load_reference_strict_catalog() -> list[dict[str, Any]]:
    return _load_catalog_file(_REFERENCE_STRICT_PATH)


def load_production_utterance_catalog() -> list[dict[str, Any]]:
    return _load_catalog_file(_PRODUCTION_PATH)


def load_utterance_catalog(*, include_smoke_reference: bool = False) -> list[dict[str, Any]]:
    """Main + strict reference + production (default CI). Smoke is inventory-only unless opted in."""
    rows = [
        *load_main_utterance_catalog(),
        *load_reference_strict_catalog(),
        *load_production_strict_catalog(),
    ]
    if include_smoke_reference:
        rows = [*rows, *load_reference_smoke_catalog()]
    return rows


def load_reference_utterance_catalog() -> list[dict[str, Any]]:
    """All reference tiers combined (smoke + strict)."""
    return [*load_reference_smoke_catalog(), *load_reference_strict_catalog()]


def load_multiturn_catalog() -> list[dict[str, Any]]:
    return _load_multiturn_file(_MULTITURN_PATH)


def catalog_by_id() -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in load_utterance_catalog(include_smoke_reference=False)}


def variant_catalog_by_id() -> dict[str, dict[str, Any]]:
    from tests.corpus.harness.gateway_meta import variant_sample_entries

    return {row["id"]: row for row in variant_sample_entries()}


def parametrized_catalog_ids() -> list[str]:
    """IDs executed by the data-driven harness (main + strict reference)."""
    return [row["id"] for row in load_utterance_catalog() if _is_executable_row(row)]


def parametrized_multiturn_ids() -> list[str]:
    return [row["id"] for row in load_multiturn_catalog()]


def merge_catalog_into_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    """Attach external catalog for schema checks in test_gateway_scripted."""
    corpus = dict(corpus)
    main = load_main_utterance_catalog()
    strict = load_reference_strict_catalog()
    smoke = load_reference_smoke_catalog()
    corpus["utterance_catalog"] = [*main, *strict]
    corpus["reference_utterance_catalog"] = smoke
    corpus["reference_utterance_strict"] = strict
    corpus["multiturn_catalog"] = load_multiturn_catalog()
    corpus["production_utterance_catalog"] = load_production_strict_catalog()
    return corpus


def assert_expectations(
    entry: dict[str, Any],
    *,
    out: str,
    tool_names: list[str] | None = None,
    proj: Path | None = None,
    llm_called: bool | None = None,
) -> None:
    expect = entry.get("expect") or {}
    for token in expect.get("response_contains") or []:
        assert token in out, f"{entry['id']}: expected {token!r} in response"

    any_of = expect.get("response_contains_any") or []
    if any_of:
        assert any(t in out for t in any_of), (
            f"{entry['id']}: none of {any_of!r} found in response: {out[:200]!r}"
        )

    excludes = expect.get("response_excludes") or []
    for token in excludes:
        assert token not in out, f"{entry['id']}: excluded {token!r} present"

    max_lines = expect.get("response_max_lines")
    if max_lines is not None:
        lines = [ln for ln in out.splitlines() if ln.strip()]
        assert len(lines) <= int(max_lines), f"{entry['id']}: too many lines ({len(lines)})"

    if expect.get("no_llm") is True:
        assert llm_called is False, f"{entry['id']}: LLM should not run"

    if tool_names is not None:
        for name in expect.get("tools_include") or []:
            assert name in tool_names, f"{entry['id']}: expected tool {name!r}"
        for name in expect.get("tools_exclude") or []:
            assert name not in tool_names, f"{entry['id']}: forbidden tool {name!r}"
        if expect.get("uses_delegate"):
            assert "delegate_task" in tool_names, f"{entry['id']}: delegate_task missing"
        if expect.get("no_write_tools"):
            assert "write_file" not in tool_names, f"{entry['id']}: write_file called"
            assert "delegate_task" not in tool_names, f"{entry['id']}: delegate_task called"

    if proj is not None:
        for rel in expect.get("file_exists") or []:
            assert (proj / rel).is_file(), f"{entry['id']}: missing file {rel}"
        for rel in expect.get("file_missing") or []:
            assert not (proj / rel).exists(), f"{entry['id']}: file should be gone {rel}"


def apply_catalog_setup(
    entry: dict[str, Any],
    *,
    handler: Any,
    proj: Path,
    session_key: str,
    helpers: dict[str, Callable[..., Any]],
) -> None:
    setup = entry.get("setup")
    if not setup:
        return
    if setup == "cached_report_delete":
        from butler.report import AgentReport, Change, cache_report, clear_report_cache

        clear_report_cache(session_key)
        cache_report(
            AgentReport(
                headline="开发代理已完成任务",
                task_preview="删除 docs/x.txt",
                summary="已删除 docs/x.txt",
                changes=[Change("docs/x.txt", "deleted", "")],
                success=True,
            ),
            session_key=session_key,
        )
    elif setup == "cached_report_hello":
        from butler.report import AgentReport, cache_report, clear_report_cache

        clear_report_cache(session_key)
        cache_report(
            AgentReport(
                headline="开发代理已完成任务",
                task_preview=f"创建 {helpers.get('HELLO_REL', 'docs/test_hello.txt')}",
                summary="已写入 hello 文件。",
                success=True,
            ),
            session_key=session_key,
        )
    elif setup == "hello_file_on_disk":
        rel = helpers["HELLO_REL"]
        (proj / rel).parent.mkdir(parents=True, exist_ok=True)
        (proj / rel).write_text(helpers["HELLO_CONTENT"], encoding="utf-8")
    elif setup == "smoke_md_on_disk":
        rel = "docs/wechat-smoke.md"
        (proj / rel).parent.mkdir(parents=True, exist_ok=True)
        (proj / rel).write_text("微信验收\n", encoding="utf-8")
    elif setup == "prior_delegate_create_hello":
        helpers["bind_script"](helpers["delegate_create_hello_script"]())
        handler.handle_message(
            "那你在灵文一号项目下面尝试新建一个文件，然后往里面写一点代码",
            session_key=session_key,
            platform="wechat",
        )
    elif setup == "switch_to_demo":
        handler.handle_message(
            "/切换 演示试点",
            session_key=session_key,
            platform="wechat",
        )
    elif setup == "switch_to_lingwen":
        handler.handle_message(
            "/切换 灵文1号",
            session_key=session_key,
            platform="wechat",
        )
    elif setup == "workflow_state_on_disk":
        wf = proj / "novel-factory" / "workflow_state.json"
        wf.parent.mkdir(parents=True, exist_ok=True)
        wf.write_text(
            '{"phase": "draft", "step": "outline"}\n',
            encoding="utf-8",
        )
    elif setup == "cached_report_delete_fail":
        from butler.report import AgentReport, cache_report, clear_report_cache

        clear_report_cache(session_key)
        cache_report(
            AgentReport(
                headline="开发代理未能完成任务",
                task_preview="删除 docs/missing-utterance.txt",
                summary="删除未完成。",
                success=False,
                issues=["请使用 delete_file", "文件不存在"],
            ),
            session_key=session_key,
        )
    elif setup == "cached_report_smoke_write":
        from butler.report import AgentReport, Change, cache_report, clear_report_cache

        clear_report_cache(session_key)
        cache_report(
            AgentReport(
                headline="内容代理已完成任务",
                task_preview="写 docs/wechat-smoke.md",
                summary="已写入 wechat-smoke.md",
                changes=[Change("docs/wechat-smoke.md", "created", "微信验收")],
                success=True,
            ),
            session_key=session_key,
        )
    elif setup == "cached_report_multi_changes":
        from butler.report import AgentReport, Change, cache_report, clear_report_cache

        clear_report_cache(session_key)
        cache_report(
            AgentReport(
                headline="开发代理已完成任务",
                summary="完整摘要",
                changes=[
                    Change("docs/a.md", "created", ""),
                    Change("docs/b.md", "modified", ""),
                ],
                success=True,
            ),
            session_key=session_key,
        )
    elif setup == "patch_target_file":
        rel = "docs/patch-target.txt"
        (proj / rel).parent.mkdir(parents=True, exist_ok=True)
        (proj / rel).write_text("OLD\n", encoding="utf-8")
    elif setup == "scenario_temp_file":
        rel = "docs/scenario-temp.txt"
        (proj / rel).parent.mkdir(parents=True, exist_ok=True)
        (proj / rel).write_text("temp\n", encoding="utf-8")
    elif setup == "u1_report_u2_empty":
        from butler.report import AgentReport, cache_report, clear_report_cache

        clear_report_cache()
        u1_sk = handler.resolve_session_key(
            session_key="wechat:u1",
            platform="wechat",
            external_id="u1",
        )
        cache_report(
            AgentReport(headline="report-for-u1-only", summary="u1"),
            session_key=u1_sk,
        )
    elif setup == "notes_on_disk":
        (proj / "docs" / "notes.md").write_text("# notes\n", encoding="utf-8")
    elif setup == "copy_runtime_jobs":
        import shutil

        src = (
            Path(__file__).resolve().parents[3]
            / "projects"
            / "DemoPilot"
            / "runtime"
            / "jobs.yaml"
        )
        if src.is_file():
            dest = proj / "runtime"
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dest / "jobs.yaml")


def run_catalog_turn(
    entry: dict[str, Any],
    *,
    handler: Any,
    session_key: str,
    proj: Path,
    helpers: dict[str, Callable[..., Any]],
    patch_llm: tuple[Any, Any],
    platform: str = "wechat",
    external_id: str | None = None,
) -> tuple[str, list[str] | None, bool | None]:
    """Execute one catalog/multiturn turn; returns (response, tool_names, llm_called)."""
    from unittest.mock import MagicMock, patch

    from butler.core.agent_loop import LoopResult, LoopStatus
    from tests.corpus.harness.gateway_scripts import (
        final_text_from_script,
        needs_real_tools,
        pad_script,
        script_profiles,
    )
    from tests.test_gateway_dev_conversations import _bind_llm_script

    entry_id = entry.get("id", "?")
    mock_complete, mock_stream = patch_llm
    kind = entry.get("kind", "command")
    tool_names: list[str] | None = None
    llm_called: bool | None = None

    msg_kw: dict[str, Any] = {"session_key": session_key, "platform": platform}
    if external_id is not None:
        msg_kw["external_id"] = external_id

    if kind in ("command", "detail"):
        with patch.object(handler, "_get_or_create_loop") as mock_loop:
            out = handler.handle_message(entry["user"], **msg_kw)
            llm_called = mock_loop.called
        if not isinstance(out, str):
            out = str(out)
    elif kind == "llm":
        script_name = entry.get("script")
        script = script_profiles().get(script_name or "")
        assert script, f"{entry_id}: unknown script {script_name!r}"
        expect = entry.get("expect") or {}

        if needs_real_tools(expect):
            _bind_llm_script(mock_complete, mock_stream, pad_script(script))
            from butler.tools.registry import dispatch_tool

            with patch(
                "butler.gateway.message_handler.dispatch_tool",
                wraps=dispatch_tool,
            ) as spy:
                out = handler.handle_message(entry["user"], **msg_kw)
                tool_names = [c[0][0] for c in spy.call_args_list if c[0]]
            llm_called = True
        else:
            with patch.object(handler, "_get_or_create_loop") as mock_get:
                loop = MagicMock()
                loop.run.return_value = LoopResult(
                    status=LoopStatus.COMPLETED,
                    final_response=final_text_from_script(script),
                )
                mock_get.return_value = loop
                out = handler.handle_message(entry["user"], **msg_kw)
                llm_called = mock_get.called
    else:
        raise AssertionError(f"{entry_id}: unsupported kind {kind!r}")

    return out, tool_names, llm_called
