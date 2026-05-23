"""Gateway scripted corpus (LW-REAL) — schema + registry wiring.

Implementation tests live in ``tests/test_gateway_dev_conversations.py`` (mock LLM scripts).
Run gateway scenarios:
  PYTHONPATH=. pytest tests/test_gateway_dev_conversations.py -q
"""

from __future__ import annotations

import pytest

from tests.corpus.harness.gateway_catalog import (
    load_main_utterance_catalog,
    load_multiturn_catalog,
    load_production_strict_catalog,
    load_reference_smoke_catalog,
    load_reference_strict_catalog,
    merge_catalog_into_corpus,
    parametrized_catalog_ids,
)
from tests.corpus.harness.gateway_meta import load_gateway_meta, validate_meta_targets
from tests.corpus.harness.loader import validate_corpus_schema
from tests.corpus.harness.registry import (
    get_suite,
    gateway_runner_modules,
    load_suite_corpus,
    resolve_runner_module_path,
)


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
        main = load_main_utterance_catalog()
        strict = load_reference_strict_catalog()
        smoke = load_reference_smoke_catalog()
        multiturn = load_multiturn_catalog()
        assert len(block) >= 1
        assert len(main) >= 50
        assert len(strict) >= 95
        assert len(smoke) >= 400
        assert len(multiturn) >= 12
        assert len(parametrized_catalog_ids()) >= 200
        assert len(load_production_strict_catalog()) >= 30

    def test_gateway_meta_valid(self):
        assert load_gateway_meta().get("suite_id") == "wechat_real.lw_real"
        assert not validate_meta_targets()

    def test_registry_runner_modules(self):
        modules = gateway_runner_modules()
        assert len(modules) >= 5
        for mod in modules:
            assert resolve_runner_module_path(mod).is_file(), mod
