"""Gateway 语料模块健康检查：meta 目标、分层文件存在、registry 一致。"""

from __future__ import annotations

import pytest

from tests.corpus.harness.gateway_catalog import _LW_REAL_DIR
from tests.corpus.harness.gateway_golden import validate_golden_index
from tests.corpus.harness.gateway_ops import validate_production_ops
from tests.corpus.harness.gateway_live import load_live_smoke_ids, validate_live_smoke_ids
from tests.corpus.harness.gateway_meta import (
    actual_tier_counts,
    load_gateway_meta,
    long_multiturn_chain_count,
    validate_coverage_matrix,
    validate_meta_targets,
    variant_sample_ids,
)
from tests.corpus.harness.registry import get_suite, load_suite_corpus


@pytest.mark.corpus
@pytest.mark.corpus_mock
class TestGatewayModuleHealth:
    def test_meta_targets_met(self):
        errors = validate_meta_targets()
        assert not errors, errors

    def test_catalog_tier_files_exist(self):
        meta = load_gateway_meta()
        tiers = meta.get("catalog_tiers") or {}
        for name, spec in tiers.items():
            if name == "l3_live":
                continue
            if "file" in spec:
                assert (_LW_REAL_DIR / spec["file"]).is_file(), f"missing {name}"
            for rel in spec.get("files") or []:
                assert (_LW_REAL_DIR / rel).is_file(), f"missing {name}/{rel}"

    def test_registry_lists_gateway_runners(self):
        entry = get_suite("wechat_real.lw_real")
        modules = entry.get("runner_modules") or []
        assert "runners/test_gateway_utterance_catalog.py" in modules
        assert "runners/test_gateway_multiturn_catalog.py" in modules
        assert "runners/test_gateway_golden.py" in modules
        assert "runners/test_gateway_live_corpus.py" in modules

    def test_actual_counts_snapshot(self):
        """规模由 validate_meta_targets 统一门禁；此处仅防回归为 0。"""
        counts = actual_tier_counts()
        assert counts["l1_strict_single"] > 0
        assert counts["l1_multiturn_chains"] > 0

    def test_coverage_matrix_keys_documented(self):
        meta = load_gateway_meta()
        matrix = meta.get("coverage_matrix") or {}
        assert len(matrix) >= 15

    def test_coverage_matrix_gates(self):
        errors = validate_coverage_matrix()
        assert not errors, errors

    def test_long_multiturn_chains(self):
        meta = load_gateway_meta()
        minimum = int((meta.get("targets") or {}).get("l1_multiturn_long_chains", 4))
        count = long_multiturn_chain_count(min_turns=5)
        assert count >= minimum, f"need >={minimum} chains with >=5 turns, got {count}"

    def test_variant_sample_inventory(self):
        meta = load_gateway_meta()
        minimum = int((meta.get("targets") or {}).get("variants_sample_max", 40))
        samples = variant_sample_ids()
        assert len(samples) >= min(30, minimum)

    def test_golden_corpus_index(self):
        corpus, _ = load_suite_corpus(get_suite("wechat_real.lw_real"))
        assert not validate_golden_index(corpus)

    def test_live_smoke_ids_wired(self):
        assert len(load_live_smoke_ids()) >= 5
        assert not validate_live_smoke_ids()

    def test_production_ops_wired(self):
        assert not validate_production_ops()
