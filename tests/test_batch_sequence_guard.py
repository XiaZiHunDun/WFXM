"""PR3b: skip stale reads after destructive tools in the same batch."""

from __future__ import annotations

import json

import pytest

from butler.core.batch_sequence_guard import (
    STALE_SKIP_CODE,
    BatchSequenceGuard,
    batch_has_destructive_and_reads,
    destructive_tool_succeeded,
    reorder_reads_before_destructive,
)
from butler.core.parallel_tools import should_parallelize_tool_batch
from butler.core.loop_types import LoopCallbacks, LoopConfig
from butler.core.tool_batch import process_tool_calls
from butler.transport.types import NormalizedResponse, Usage, build_tool_call


@pytest.mark.module_test
def test_destructive_success_detection():
    ok_patch = json.dumps({"ok": True, "path": "/tmp/a.py"})
    assert destructive_tool_succeeded("patch", ok_patch)
    bad = json.dumps({"ok": False, "error": "fail"})
    assert not destructive_tool_succeeded("patch", bad)


@pytest.mark.module_test
def test_batch_has_destructive_and_reads():
    calls = [
        build_tool_call("c1", "read_file", {"path": "/tmp/a.py"}),
        build_tool_call("c2", "patch", {"path": "/tmp/a.py"}),
    ]
    assert batch_has_destructive_and_reads(calls)


def test_reorder_reads_before_patch_same_path():
    calls = [
        build_tool_call("c1", "patch", {"path": "/tmp/a.py"}),
        build_tool_call("c2", "read_file", {"path": "/tmp/a.py"}),
        build_tool_call("c3", "terminal", {"command": "pytest -q"}),
    ]
    ordered = reorder_reads_before_destructive(calls)
    names = [getattr(tc, "name", "") for tc in ordered]
    assert names == ["read_file", "patch", "terminal"]


@pytest.mark.module_test
def test_reorder_skips_unrelated_paths():
    calls = [
        build_tool_call("c1", "read_file", {"path": "/tmp/test_b9.py"}),
        build_tool_call("c2", "patch", {"path": "/tmp/calc.py"}),
    ]
    ordered = reorder_reads_before_destructive(calls)
    names = [getattr(tc, "name", "") for tc in ordered]
    assert names == ["read_file", "patch"]


@pytest.mark.module_test
def test_parallel_disabled_when_write_and_read(monkeypatch):
    monkeypatch.setenv("BUTLER_BATCH_STALE_GUARD", "1")
    calls = [
        build_tool_call("c1", "write_file", {"path": "/tmp/a.py", "content": "x"}),
        build_tool_call("c2", "read_file", {"path": "/tmp/a.py"}),
    ]
    assert should_parallelize_tool_batch(calls) is False


@pytest.mark.module_test
def test_sequential_skips_read_after_patch(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_BATCH_STALE_GUARD", "1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    path = "seq_guard_a.py"
    (tmp_path / path).write_text("old", encoding="utf-8")
    dispatched: list[str] = []

    def dispatch(name: str, args: dict) -> str:
        dispatched.append(name)
        if name == "patch":
            return json.dumps({"ok": True, "path": args.get("path")})
        return json.dumps({"content": "old", "ok": True})

    tool_calls = [
        build_tool_call("c1", "read_file", {"path": path}),
        build_tool_call("c2", "patch", {"path": path, "old_string": "old", "new_string": "new"}),
        build_tool_call("c3", "read_file", {"path": path}),
    ]
    messages: list[dict] = []
    process_tool_calls(
        response=NormalizedResponse(tool_calls=tool_calls, usage=Usage(1, 1, 3)),
        messages=messages,
        config=LoopConfig(enable_parallel_tools=False),
        callbacks=LoopCallbacks(),
        guardrails=None,
        dispatch_tool=dispatch,
        interrupt_check=lambda: False,
    )

    assert dispatched == ["read_file", "patch"]
    tool_payloads = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
    assert len(tool_payloads) == 3
    assert tool_payloads[2]["code"] == STALE_SKIP_CODE


@pytest.mark.module_test
def test_skips_prefetched_read_after_write(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_BATCH_STALE_GUARD", "1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    path = "prefetch_b.py"
    prefetched = {
        "c_read": json.dumps({"content": "prefetched", "ok": True}),
        "c_write": json.dumps({"ok": True, "path": path}),
    }

    def dispatch(name: str, args: dict) -> str:
        raise AssertionError(f"should not dispatch {name}")

    tool_calls = [
        build_tool_call("c_write", "write_file", {"path": path, "content": "n"}),
        build_tool_call("c_read", "read_file", {"path": path}),
    ]
    messages: list[dict] = []
    process_tool_calls(
        response=NormalizedResponse(tool_calls=tool_calls, usage=Usage(1, 1, 2)),
        messages=messages,
        config=LoopConfig(enable_parallel_tools=False),
        callbacks=LoopCallbacks(),
        guardrails=None,
        dispatch_tool=dispatch,
        interrupt_check=lambda: False,
        prefetched=prefetched,
    )

    stale = json.loads(messages[-1]["content"])
    assert stale["code"] in (STALE_SKIP_CODE, "BATCH_STALE_PREFETCH")


@pytest.mark.module_test
def test_guard_should_skip_overlap():
    guard = BatchSequenceGuard()
    guard.invalidated_paths.append("/tmp/foo.py")
    guard.last_writer = "patch"
    assert guard.should_skip_stale_read("read_file", {"path": "/tmp/foo.py"})
    assert not guard.should_skip_stale_read("read_file", {"path": "/tmp/other.py"})
