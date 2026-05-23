"""Corpus module pytest hooks."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_CORPUS_ROOT = Path(__file__).resolve().parent
_REGISTRY_PATH = _CORPUS_ROOT / "registry.yaml"


def pytest_configure(config):
    config.addinivalue_line("markers", "corpus: corpus-driven evaluation tests")
    config.addinivalue_line("markers", "corpus_mock: corpus tests using mocked LLM (CI default)")
    config.addinivalue_line("markers", "corpus_live: corpus tests calling real LLM APIs")
    config.addinivalue_line("markers", "corpus_smoke: subset of corpus_live smoke cases")


@pytest.fixture(scope="session")
def corpus_registry() -> dict:
    with _REGISTRY_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def corpus_root() -> Path:
    return _CORPUS_ROOT


# Gateway L1 fixtures (utterance / multiturn / variants runners)
pytest_plugins = ["tests.corpus.conftest_gateway"]
