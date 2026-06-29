"""ENG-10: scattered model literals should live in butler.defaults.model_defaults."""

from __future__ import annotations

import pathlib

# High-churn chat/embedding ids — allow only in defaults + workflows + tests.
_SCATTERED_LITERALS: tuple[str, ...] = (
    "MiniMax-M2.7",
    "text-embedding-3-small",
    "embo-01",
    "gpt-4o",
    "deepseek-chat",
    "qwen-max",
)

_ALLOWLIST_PREFIXES: tuple[str, ...] = (
    "butler/defaults/",
    "butler/workflows/",
    "butler/ops/",  # token cost tables
    "butler/transport/",  # capability/thinking heuristics
    "tests/",
    "docs/",
)


def _is_allowlisted(rel: str) -> bool:
    return rel.startswith(_ALLOWLIST_PREFIXES)


def test_no_scattered_provider_model_literals_in_business_code():
    root = pathlib.Path("butler")
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.as_posix()
        if _is_allowlisted(rel):
            continue
        text = path.read_text(encoding="utf-8")
        for literal in _SCATTERED_LITERALS:
            if literal in text:
                offenders.append(f"{rel}: {literal!r}")
    assert not offenders, "Move literals to butler/defaults/model_defaults.py:\n" + "\n".join(
        offenders[:20]
    )


def test_model_defaults_exports_embedding_and_provider_helpers():
    from butler.defaults import model_defaults as md

    assert md.provider_default_model("minimax") == md.PROVIDER_ENV_DEFAULT_MODEL["minimax"]
    assert md.OPENAI_EMBEDDING_MODEL
    assert md.OPENAI_VISION_DEFAULT_MODEL == md.provider_default_model("openai")
    assert md.DEFAULT_EMBEDDING_MODEL == "hashing-v1"
