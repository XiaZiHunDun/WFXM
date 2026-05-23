"""Production 语料运营门禁 — meta 脚本路径、升格一致性、规模。"""

from __future__ import annotations

import pytest

from tests.corpus.harness.gateway_ops import production_inventory, validate_production_ops


@pytest.mark.corpus
@pytest.mark.corpus_mock
class TestGatewayProductionOps:
    def test_production_ops_meta_wired(self):
        errors = validate_production_ops()
        assert not errors, errors

    def test_production_pool_size(self):
        inv = production_inventory()
        assert inv["production_count"] >= 30
        assert inv["production_strict_count"] >= 30
