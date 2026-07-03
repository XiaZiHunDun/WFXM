"""Production delegate bridge best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def build_prod_playbook_blocks_safe(task: str, context: str) -> list[str]:
    def _run() -> list[str]:
        from butler.dev_engine.prod_playbook_seeds import build_prod_playbook_blocks

        blocks = build_prod_playbook_blocks(task, context)
        if not isinstance(blocks, list):
            raise ValueError("prod playbook blocks must be a list")
        return [str(b) for b in blocks if str(b or "").strip()]

    result = safe_best_effort(
        _run,
        label="prod_delegate_bridge.playbook_blocks",
        default=[],
    )
    return list(result) if isinstance(result, list) else []


def collect_lingwen_prod_sample_playbooks_safe(blob: str) -> list[str]:
    def _run() -> list[str]:
        from butler.ops.lingwen1_prod_sample import LINGWEN_PROD_SAMPLE_PLAYBOOKS

        blocks: list[str] = []
        for sample_id, playbook in LINGWEN_PROD_SAMPLE_PLAYBOOKS.items():
            if sample_id in blob and str(playbook or "").strip():
                blocks.append(str(playbook).strip())
        return blocks

    result = safe_best_effort(
        _run,
        label="prod_delegate_bridge.lingwen_samples",
        default=[],
    )
    return list(result) if isinstance(result, list) else []
