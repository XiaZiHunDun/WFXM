"""ENG-15: package-prefix → engineering layer and forbidden import rules.

SSOT aligned with docs/architecture/v4-layer-model.md §3–§4.
"""

from __future__ import annotations

# Longest-prefix wins when resolving a file path to a layer.
PREFIX_LAYER: tuple[tuple[str, str], ...] = (
    ("butler/gateway/", "L1"),
    ("butler/cli/", "L1"),
    ("butler/core/", "L3"),
    ("butler/orchestrator/", "L2"),
    ("butler/workflows/", "L2"),
    ("butler/runtime/", "L2"),
    ("butler/session/", "L5"),
    ("butler/project/", "L2"),
    ("butler/plan/", "L2"),
    ("butler/hooks/", "L4"),
    ("butler/registry/", "L4"),
    ("butler/execpolicy/", "L7"),
    ("butler/experiments/", "L7"),
    ("butler/prompt_eval/", "L9"),
    ("butler/dev_engine/", "L4"),
    ("butler/tools/", "L4"),
    ("butler/mcp/", "L4"),
    ("butler/skills/", "L4"),
    ("butler/extensions/", "L4"),
    ("butler/delegate/", "L4"),
    ("butler/memory/", "L5"),
    ("butler/transport/", "L6"),
    ("butler/permissions/", "L7"),
    ("butler/ops/", "L9"),
    ("butler/eval_integration/", "L9"),
    ("butler/report/", "L9"),
    ("butler/defaults/", "L1"),
    ("butler/tests_policies/", "L9"),
)

FILE_LAYER_OVERRIDE: dict[str, str] = {
    "butler/execution_context.py": "L3",
    "butler/human_gate.py": "L7",
    "butler/gate_reply_templates.py": "L7",
    "butler/orchestrator.py": "L2",
    "butler/task_orchestrator.py": "L2",
    "butler/dag_scheduler.py": "L2",
    "butler/workflow_step_runner.py": "L2",
    "butler/tenant.py": "L4",
    "butler/agent_profiles.py": "L2",
    "butler/model_resolve.py": "L6",
    "butler/model_resolve_ops.py": "L6",
    "butler/main.py": "L1",
    "butler/tool_guardrails.py": "L4",
    "butler/human_gate_ops.py": "L7",
    "butler/memory_plugin.py": "L5",
    "butler/gateway_settings.py": "L1",
    "butler/gateway_settings_ops.py": "L1",
    "butler/io/": "L5",
    "butler/__init__.py": "L1",
    "butler/agent_profiles_ops.py": "L2",
    "butler/agents_md.py": "L4",
    "butler/agents_md_ops.py": "L4",
    "butler/butler_init_ops.py": "L1",
    "butler/config.py": "L1",
    "butler/config_ops.py": "L1",
    "butler/config_secrets.py": "L1",
    "butler/config_secrets_crypto.py": "L1",
    "butler/config_secrets_crypto_ops.py": "L1",
    "butler/config_secrets_ops.py": "L1",
    "butler/config_service.py": "L1",
    "butler/context_settings.py": "L3",
    "butler/context_settings_ops.py": "L3",
    "butler/dag_scheduler_ops.py": "L2",
    "butler/defaults/model_defaults.py": "L6",
    "butler/env_parse.py": "L1",
    "butler/logging_config.py": "L1",
    "butler/memory_settings.py": "L5",
    "butler/memory_settings_ops.py": "L5",
    "butler/provider_presets.py": "L6",
    "butler/provider_presets_ops.py": "L6",
    "butler/repo_paths.py": "L1",
    "butler/task_orchestrator_ops.py": "L2",
    "butler/tool_guardrails_ops.py": "L4",
    "butler/workflow_step_runner_ops.py": "L2",
}

# Per-file exemptions (documented seams; see decoupling-assessment-2026-07.md).
FILE_GATEWAY_IMPORT_ALLOWLIST: frozenset[str] = frozenset({
    "butler/execution_context.py",
})

# L3 may import these L9 modules for best-effort telemetry (matrix: L3 → L9 read).
L3_OPS_IMPORT_ALLOWLIST: frozenset[str] = frozenset({
    "butler.ops.runtime_metrics",
    "butler.ops.retry_buckets",
    "butler.ops.cost_tracker",
    "butler.ops.usage_ledger",
    "butler.ops.eval_actions",
    "butler.ops.eval_feedback",
})

# L5 memory layer: best-effort ops reads (matrix L5 → L9 read).
L5_OPS_IMPORT_ALLOWLIST: frozenset[str] = frozenset({
    "butler.ops.langfuse_tracer",
    "butler.ops.runtime_metrics",
    "butler.ops.embedding_diagnostics",
    "butler.ops.transcript_diagnostics",
    "butler.ops.degradation_registry",
    "butler.ops.eval_config_overrides",
})

# Caller layer → list of (forbidden_module_prefix, remediation_hint)
FORBIDDEN_IMPORTS: dict[str, list[tuple[str, str]]] = {
    "L3": [
        ("butler.gateway", "Use butler.execution_context or butler.contracts.*"),
        ("butler.ops", "Use allowlisted ops telemetry only; heavy L9 via contracts"),
    ],
    "L4": [
        ("butler.gateway", "Use butler.delegate.* or butler.contracts.*"),
    ],
    "L5": [
        ("butler.gateway", "Use butler.contracts.memory_ports or L5 handlers"),
        ("butler.ops", "Use allowlisted ops (langfuse tracer in lazy helpers only)"),
    ],
    "L6": [
        ("butler.gateway", "Transport must not depend on gateway types"),
    ],
    "L7": [
        ("butler.gateway", "Use butler.contracts.owner_gate / approval ports"),
    ],
}


def resolve_layer(rel_path: str) -> str | None:
    if rel_path in FILE_LAYER_OVERRIDE:
        return FILE_LAYER_OVERRIDE[rel_path]
    for prefix, layer in PREFIX_LAYER:
        if prefix.endswith("/") and rel_path.startswith(prefix):
            return layer
    for prefix, layer in FILE_LAYER_OVERRIDE.items():
        if prefix.endswith("/") and rel_path.startswith(prefix):
            return layer
    return None


def is_forbidden_import(
    caller_layer: str,
    imported_module: str,
    rel_path: str,
) -> tuple[bool, str]:
    rules = FORBIDDEN_IMPORTS.get(caller_layer, [])
    for prefix, hint in rules:
        if imported_module == prefix or imported_module.startswith(prefix + "."):
            if prefix == "butler.gateway" and rel_path in FILE_GATEWAY_IMPORT_ALLOWLIST:
                return False, ""
            if prefix == "butler.ops" and caller_layer == "L3":
                if imported_module in L3_OPS_IMPORT_ALLOWLIST or any(
                    imported_module.startswith(a + ".") for a in L3_OPS_IMPORT_ALLOWLIST
                ):
                    return False, ""
                return True, f"{hint}; allowlist: {sorted(L3_OPS_IMPORT_ALLOWLIST)}"
            if prefix == "butler.ops" and caller_layer == "L5":
                if imported_module in L5_OPS_IMPORT_ALLOWLIST or any(
                    imported_module.startswith(a + ".") for a in L5_OPS_IMPORT_ALLOWLIST
                ):
                    return False, ""
                return True, f"{hint}; allowlist: {sorted(L5_OPS_IMPORT_ALLOWLIST)}"
            return True, hint
    return False, ""
