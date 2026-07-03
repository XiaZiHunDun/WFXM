"""Agent profile prompt appendix best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort


def load_dev_engine_appendix_body_safe() -> str:
    def _run() -> str:
        from butler.dev_engine.dev_tools import dev_engine_enabled

        if not dev_engine_enabled():
            return ""
        md_path = Path(__file__).resolve().parent / "prompts" / "dev_engine_system.md"
        if not md_path.is_file():
            return ""
        return "\n\n" + md_path.read_text(encoding="utf-8").strip()

    result = safe_best_effort(
        _run,
        label="agent_profiles.dev_engine_appendix",
        default="",
    )
    return str(result) if result else ""
