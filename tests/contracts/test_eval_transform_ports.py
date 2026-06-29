"""Contract tests for eval and transform ports."""

from __future__ import annotations

from butler.contracts.context_transform_ports import ContextTransformPort, TransformContext
from butler.contracts.eval_ports import EvalSuitePort, ScoreSinkPort, SuiteRunResult


class _StubSuite:
    suite_id = "stub"
    layer = "L-A"

    def run(
        self,
        *,
        warn_only: bool = False,
        sync_dataset: bool = False,
        push_langfuse: bool | None = None,
    ) -> SuiteRunResult:
        return SuiteRunResult(suite_id="stub", ok=True, layer="L-A")


class _StubSink:
    backend_id = "stub"

    def write_suite_result(self, result: SuiteRunResult, payload: dict) -> str:
        return "stub://written"

    def read_latest(self, suite_id: str) -> dict | None:
        return None


class _StubTransform:
    transform_id = "stub"
    priority = 1
    lossy = False

    def apply(self, messages: list[dict], ctx: TransformContext) -> list[dict]:
        return messages


def test_eval_suite_port_runtime_checkable():
    assert isinstance(_StubSuite(), EvalSuitePort)


def test_score_sink_port_runtime_checkable():
    assert isinstance(_StubSink(), ScoreSinkPort)


def test_context_transform_port_runtime_checkable():
    assert isinstance(_StubTransform(), ContextTransformPort)
