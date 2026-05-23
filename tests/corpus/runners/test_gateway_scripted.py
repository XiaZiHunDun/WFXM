"""Gateway scripted corpus (LW-REAL) — schema + registry wiring.

Implementation tests live in ``tests/test_gateway_dev_conversations.py`` (mock LLM scripts).
Run gateway scenarios:
  PYTHONPATH=. pytest tests/test_gateway_dev_conversations.py -q
"""

from __future__ import annotations

import pytest

from tests.corpus.harness.gateway_catalog import load_utterance_catalog, merge_catalog_into_corpus
from tests.corpus.harness.loader import validate_corpus_schema
from tests.corpus.harness.registry import get_suite, load_suite_corpus


@pytest.mark.corpus
@pytest.mark.corpus_mock
class TestGatewayScriptedCorpus:
    def test_lw_real_schema(self):
        entry = get_suite("wechat_real.lw_real")
        corpus, path = load_suite_corpus(entry)
        assert path.is_file()
        merged = merge_catalog_into_corpus(corpus)
        errors = validate_corpus_schema(merged, channel="gateway_wechat")
        assert not errors, errors
        block = merged.get("lingwen_real_dialogue") or []
        catalog = load_utterance_catalog()
        assert len(block) >= 1
        assert len(catalog) >= 50
        executable = [
            r for r in catalog if r.get("runner") != "legacy" and r.get("kind") != "multi"
        ]
        assert len(executable) >= 45
