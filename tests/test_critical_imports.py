"""Validate all lazy / conditional import paths are reachable.

Catches module-rename or deletion regressions *before* deployment.
No API keys, fixtures, or network needed — pure importability check.
"""

from __future__ import annotations

import importlib

import pytest

# --- Core loop & pipeline ---
CORE_MODULES = [
    "butler.core.agent_loop",
    "butler.core.tool_batch",
    "butler.core.context_pipeline",
    "butler.core.llm_retry",
    "butler.core.io_guardrail",
    "butler.core.message_ir",
    "butler.core.two_phase_confirm",
    "butler.core.session_transcript",
    "butler.core.context_budget",
    "butler.core.compaction_status",
    "butler.core.schema_optimizer",
    "butler.core.pipeline_steps",
]

# --- Gateway & commands ---
GATEWAY_MODULES = [
    "butler.gateway.message_handler",
    "butler.gateway.session_registry",
    "butler.gateway.command_registry",
    "butler.gateway.commands",
    "butler.gateway.message_queue",
    "butler.gateway.queue_settings",
    "butler.gateway.outbound_bridge",
    "butler.gateway.owner_gate",
    "butler.gateway.commands.dev_handlers",
    "butler.gateway.bot_loop_guard",
    "butler.gateway.completion_notify",
    "butler.gateway.error_cards",
    "butler.gateway.inbound_media",
    "butler.gateway.platform_policy",
]

# --- Project management ---
PROJECT_MODULES = [
    "butler.project.lead",
    "butler.project.manager",
    "butler.project.preflight",
    "butler.project.meta",
]

# --- Memory & security ---
MEMORY_MODULES = [
    "butler.memory.embedding",
    "butler.memory.vector_store",
    "butler.memory.injection_guard",
    "butler.memory.injection_llm_score",
    "butler.memory.prefetch_cache",
    "butler.memory.diagnostics",
]

# --- Transport ---
TRANSPORT_MODULES = [
    "butler.transport.llm_client",
    "butler.transport.auxiliary_client",
]

# --- Other critical modules ---
OTHER_MODULES = [
    "butler.human_gate",
    "butler.config",
    "butler.config_service",
    "butler.tools.registry",
    "butler.tools.config_tools",
    "butler.tools.web_search",
    "butler.tools.multimodal_tools",
    "butler.ops.health_report",
    "butler.ops.runtime_metrics",
    "butler.model_resolve",
]

ALL_MODULES = (
    CORE_MODULES
    + GATEWAY_MODULES
    + PROJECT_MODULES
    + MEMORY_MODULES
    + TRANSPORT_MODULES
    + OTHER_MODULES
)


@pytest.mark.parametrize("module_path", ALL_MODULES)
def test_lazy_import_reachable(module_path: str) -> None:
    """Each module that is lazily imported in handler / loop must be importable."""
    importlib.import_module(module_path)
