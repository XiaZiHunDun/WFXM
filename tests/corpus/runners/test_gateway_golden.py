"""L2 golden paths — ``corpus.yaml`` index + registry entry for L2.

Implementation tests remain in ``tests/test_gateway_dev_conversations.py`` (fixtures).
CI one-shot runs both via ``./scripts/corpus-test.sh gateway``.

Run index only:
  PYTHONPATH=. pytest tests/corpus/runners/test_gateway_golden.py -q
"""

from __future__ import annotations

import pytest

from tests.corpus.harness.gateway_golden import golden_entry_ids, validate_golden_index
from tests.corpus.harness.registry import get_suite, load_suite_corpus

pytestmark = [pytest.mark.integration, pytest.mark.corpus, pytest.mark.corpus_mock]


class TestGatewayGoldenCorpusIndex:
    def test_golden_pytest_paths_resolve(self):
        corpus, _ = load_suite_corpus(get_suite("wechat_real.lw_real"))
        errors = validate_golden_index(corpus)
        assert not errors, errors

    def test_golden_entry_count(self):
        corpus, _ = load_suite_corpus(get_suite("wechat_real.lw_real"))
        ids = golden_entry_ids(corpus)
        assert len(ids) >= 10, f"expected >=10 golden ids, got {len(ids)}"
