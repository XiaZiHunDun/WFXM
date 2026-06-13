"""LingWen1 production-shaped delegate samples."""

from __future__ import annotations

from butler.ops.lingwen1_prod_sample import LINGWEN1_PROD_SAMPLES, build_lingwen_prod_sample_context


def test_lingwen1_prod_samples_count():
    assert len(LINGWEN1_PROD_SAMPLES) == 3
    ids = {s.sample_id for s in LINGWEN1_PROD_SAMPLES}
    assert "lingwen1-sample-demo-import" in ids
    assert "lingwen1-sample-validate-progress" in ids


def test_build_lingwen_prod_sample_context_includes_playbook(tmp_path):
    sample = LINGWEN1_PROD_SAMPLES[1]
    ctx = build_lingwen_prod_sample_context(sample=sample, workspace=tmp_path)
    assert "PLAYBOOK constants (idempotent)" in ctx
    assert "novel-factory/scripts/validate_progress.py" not in ctx


def test_lingwen_prod_sample_category_denies_write_file():
    from butler.delegate.category_resolver import resolve_category

    preset = resolve_category("lingwen-prod-sample")
    assert preset is not None
    assert "write_file" in (preset.get("deny_tools") or [])
