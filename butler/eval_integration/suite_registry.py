"""Eval suite registry (MOD-3)."""

from __future__ import annotations

from typing import Callable

from butler.contracts.eval_ports import EvalSuitePort

_SUITE_FACTORIES: dict[str, Callable[[], EvalSuitePort]] = {}


def register_suite_factory(suite_id: str, factory: Callable[[], EvalSuitePort]) -> None:
    _SUITE_FACTORIES[suite_id] = factory


def list_suite_ids() -> list[str]:
    return sorted(_SUITE_FACTORIES.keys())


def get_suite(suite_id: str) -> EvalSuitePort:
    factory = _SUITE_FACTORIES.get(suite_id)
    if factory is None:
        raise KeyError(f"Unknown eval suite: {suite_id}")
    return factory()


def _register_builtins() -> None:
    from butler.eval_integration.suites.agent_weekly_suite import AgentWeeklySuite
    from butler.eval_integration.suites.capability_suite import CapabilitySuite
    from butler.eval_integration.suites.deepeval_suite import DeepEvalAgentSuite
    from butler.eval_integration.suites.ragas_suite import RagasMemorySuite
    from butler.eval_integration.suites.tcr_suite import TcrSuite

    register_suite_factory("tcr", TcrSuite)
    register_suite_factory("agent_weekly", AgentWeeklySuite)
    register_suite_factory("capability", CapabilitySuite)
    register_suite_factory("deepeval_agent", DeepEvalAgentSuite)
    register_suite_factory("ragas_memory", RagasMemorySuite)


_register_builtins()
