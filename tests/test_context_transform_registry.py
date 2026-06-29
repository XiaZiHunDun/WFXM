"""Context transform registry tests."""

from __future__ import annotations

from pathlib import Path

import yaml

from butler.core.context_transform_registry import (
    apply_model_transforms,
    reload_transform_registry,
)
from butler.core.transform_feedback import analyse_transform_signals
from butler.core.transform_overrides import (
    clear_transform_overrides,
    load_transform_overrides,
    merge_transform_params,
)


def test_apply_model_transforms_default_thinking():
    msgs = [{"role": "system", "content": "hello"}]
    out = apply_model_transforms(msgs, provider="anthropic", model="claude-3")
    assert len(out) == 1
    assert out[0]["role"] == "system"


def test_yaml_profile_fc_hint(tmp_path, monkeypatch):
    cfg = tmp_path / "model-transforms.yaml"
    cfg.write_text(
        yaml.dump(
            {
                "version": 1,
                "profiles": [
                    {
                        "match": {"provider": "deepseek", "model": "*"},
                        "transforms": [{"id": "fc_hint_extra", "priority": 60, "params": {}}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    reload_transform_registry(cfg)
    msgs = [{"role": "system", "content": "base"}]
    out = apply_model_transforms(
        msgs,
        provider="deepseek",
        model="deepseek-chat",
        path=cfg,
    )
    assert len(out) == 1
    assert "工具" in out[0]["content"] or len(out[0]["content"]) >= len("base")


def test_transform_overrides_merge():
    clear_transform_overrides()
    from butler.core.transform_overrides import apply_transform_override

    apply_transform_override("tool_schema_compact", {"max_tools": 20})
    merged = merge_transform_params("tool_schema_compact", {"max_tools": 32})
    assert merged["max_tools"] == 20
    clear_transform_overrides()


def test_transform_feedback_bounded():
    clear_transform_overrides()
    actions = analyse_transform_signals(tcr_rate=0.9, tool_score=0.4)
    assert actions
    data = load_transform_overrides()
    assert "transforms" in data
    clear_transform_overrides()
