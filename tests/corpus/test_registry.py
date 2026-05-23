"""Registry and schema validation for all corpus suites."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.corpus.harness import load_corpus, resolve_corpus_path, validate_corpus_schema
from tests.corpus.harness.corpus_intent import load_crosswalk, validate_crosswalk
from tests.corpus.harness.gateway_meta import load_gateway_meta, validate_meta_targets
from tests.corpus.harness.registry import (
    gateway_runner_modules,
    get_suite,
    resolve_runner_module_path,
)

_CORPUS_ROOT = Path(__file__).resolve().parent


@pytest.mark.corpus
@pytest.mark.corpus_mock
class TestCorpusRegistry:
    @pytest.fixture(scope="class")
    def registry(self):
        with (_CORPUS_ROOT / "registry.yaml").open(encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_all_legacy_corpora_load_and_validate(self, registry):
        for entry in registry.get("suites") or []:
            path = resolve_corpus_path(entry, _CORPUS_ROOT)
            assert path.is_file(), f"missing corpus: {entry['suite_id']} -> {path}"
            corpus = load_corpus(path)
            errors = validate_corpus_schema(
                corpus, channel=entry.get("channel", "agent_loop")
            )
            assert not errors, f"{entry['suite_id']}: {errors}"

    def test_wechat_real_gateway_suite_wiring(self, registry):
        entry = next(
            e for e in (registry.get("suites") or []) if e["suite_id"] == "wechat_real.lw_real"
        )
        assert entry.get("channel") == "gateway_wechat"
        assert entry.get("meta_path")
        assert entry.get("schema", "").endswith("gateway-utterance-v1.md")
        modules = gateway_runner_modules(entry)
        assert len(modules) >= 5
        for mod in modules:
            path = resolve_runner_module_path(mod, corpus_root_path=_CORPUS_ROOT)
            assert path.is_file(), f"missing runner module: {mod} -> {path}"
        meta = load_gateway_meta()
        assert meta.get("suite_id") == "wechat_real.lw_real"
        assert not validate_meta_targets()

    def test_cross_channel_crosswalk(self, registry):
        cross = registry.get("cross_channel") or {}
        assert cross.get("crosswalk")
        assert (_CORPUS_ROOT / cross["crosswalk"]).is_file()
        assert not validate_crosswalk(load_crosswalk())
