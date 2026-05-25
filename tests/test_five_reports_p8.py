"""Five-reports P8: provider preset apply, corpus prompt-eval live bridge."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_apply_provider_preset_dry_run():
    from butler.provider_presets import apply_provider_preset

    ok, msg = apply_provider_preset("minimax-default", dry_run=True)
    assert ok
    assert "dry-run" in msg
    assert "butler://minimax-default" in msg


@pytest.mark.unit
def test_apply_provider_preset_to_project_yaml(tmp_path):
    from butler.provider_presets import apply_provider_preset
    from butler.project import Project

    cfg = tmp_path / "project.yaml"
    cfg.write_text(
        yaml.safe_dump(
            {"name": "demo", "type": "software", "models": {}},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    ok, msg = apply_provider_preset(
        "deepseek-chat",
        role="dev_agent",
        workspace=tmp_path,
        persist=True,
    )
    assert ok, msg
    proj = Project.from_yaml(cfg)
    assert proj.models["dev_agent"].provider == "deepseek"
    assert proj.models["dev_agent"].model == "deepseek-chat"


@pytest.mark.unit
def test_try_handle_preset_model_command():
    from butler.provider_presets import try_handle_preset_model_command

    out = try_handle_preset_model_command("preset minimax-default", project=None)
    assert out is not None
    reply, reset = out
    assert "minimax" in reply.lower() or "未找到" in reply or "项目" in reply
    assert isinstance(reset, bool)


@pytest.mark.unit
def test_corpus_live_skipped_without_env():
    from butler.prompt_eval.corpus_bridge import run_corpus_prompt_live_subset

    ok, errors = run_corpus_prompt_live_subset(
        overlay_path=ROOT / "tests/fixtures/prompt_eval/corpus_cases.yaml",
    )
    assert not ok
    assert errors and "BUTLER_RUN_REAL_API_SMOKE" in errors[0]


@pytest.mark.unit
def test_provider_apply_cli_dry_run(capsys):
    from butler.cli.provider_presets_cli import _cmd_apply
    import argparse

    ns = argparse.Namespace(
        preset_id="minimax-default",
        role="dev_agent",
        workspace="",
        runtime=False,
        dry_run=True,
    )
    code = _cmd_apply(ns)
    assert code == 0
    assert "dry-run" in capsys.readouterr().out
