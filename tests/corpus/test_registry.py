"""Registry and schema validation for all corpus suites."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.corpus.harness import load_corpus, resolve_corpus_path, validate_corpus_schema

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
