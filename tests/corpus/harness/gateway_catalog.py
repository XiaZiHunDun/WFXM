"""Load and execute WeChat utterance_catalog scenarios (data-driven gateway tests)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import yaml

_CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "suites"
    / "wechat_real"
    / "lw_real"
    / "utterance_catalog.yaml"
)


def load_utterance_catalog() -> list[dict[str, Any]]:
    data = yaml.safe_load(_CATALOG_PATH.read_text(encoding="utf-8"))
    rows = data.get("utterance_catalog") or []
    if not isinstance(rows, list):
        raise ValueError("utterance_catalog must be a list")
    return rows


def catalog_by_id() -> dict[str, dict[str, Any]]:
    return {row["id"]: row for row in load_utterance_catalog()}


def parametrized_catalog_ids() -> list[str]:
    """IDs executed by the data-driven harness (excludes legacy hand-written tests)."""
    return [
        row["id"]
        for row in load_utterance_catalog()
        if row.get("runner") != "legacy" and row.get("kind") != "multi"
    ]


def merge_catalog_into_corpus(corpus: dict[str, Any]) -> dict[str, Any]:
    """Attach external catalog for schema checks in test_gateway_scripted."""
    corpus = dict(corpus)
    corpus["utterance_catalog"] = load_utterance_catalog()
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

    for token in expect.get("response_contains_any") or []:
        assert any(t in out for t in token), f"{entry['id']}: none of {token!r} in response"

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
            session_key="wechat:u1",
            platform="wechat",
        )
    elif setup == "switch_to_demo":
        handler.handle_message(
            "/切换 演示试点",
            session_key="wechat:u1",
            platform="wechat",
        )
    elif setup == "switch_to_lingwen":
        handler.handle_message(
            "/切换 灵文1号",
            session_key="wechat:u1",
            platform="wechat",
        )
