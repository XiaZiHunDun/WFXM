"""LingWen1 production-shaped delegate samples."""

from __future__ import annotations

from butler.ops.lingwen1_prod_sample import LINGWEN1_PROD_SAMPLES


def test_lingwen1_prod_samples_count():
    assert len(LINGWEN1_PROD_SAMPLES) == 3
    ids = {s.sample_id for s in LINGWEN1_PROD_SAMPLES}
    assert "lingwen1-sample-demo-import" in ids
    assert "lingwen1-sample-validate-progress" in ids
