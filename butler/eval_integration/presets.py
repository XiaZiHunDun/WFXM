"""Eval suite presets for CLI and release scripts."""

from __future__ import annotations

PRESETS: dict[str, list[str]] = {
    "release": ["tcr", "regression", "wechat_corpus"],
    "weekly": ["tcr", "agent_weekly", "capability"],
    "memory": ["memory_mb", "ragas_memory"],
    "dev": ["tcr", "b9_oracle", "memory_mb"],
}


def resolve_suites(*, suite: str | None = None, preset: str | None = None) -> list[str]:
    if preset:
        key = preset.strip().lower()
        if key not in PRESETS:
            raise KeyError(f"Unknown eval preset: {preset}")
        return list(PRESETS[key])
    if not suite:
        return []
    return [s.strip() for s in suite.split(",") if s.strip()]
