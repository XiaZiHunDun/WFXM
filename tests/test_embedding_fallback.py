"""R2-3: Surface embedding_degraded + exc_info on HashingEmbedder fallback.

Per audit R2-3 in docs/reviews/project-deep-audit-2026-06-r1to8.md:
- 5 fallback log sites in embedding.py (lines 247, 252, 335, 346, 352) swallowed
  embedding provider failures (fastembed init / openai key missing / API probe
  timeout) silently with logger.warning. The HashingEmbedder (64-bit local
  hashing) is used as the fallback. The entire memory subsystem's recall
  quality collapses but the user only sees a single .warning line — no signal
  in /诊断, no exc_info.

Fix:
  1. logger.warning → logger.error(..., exc_info=...) at fallback sites
  2. Add Embedder.degraded: bool attribute (default False)
  3. Mark fallback HashingEmbedder instances with degraded=True and tag with
     requested_provider/requested_model so /诊断 can show what was wanted vs
     what is actually used.
  4. Surface degraded state through diagnostics → /诊断 via
     `embedding_degraded`, `embedding_requested_provider`,
     `embedding_requested_model`, `embedding_used_model` fields.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest


# ── 1. HashingEmbedder.degraded contract ──────────────────────────────────


@pytest.mark.module_test
class TestHashingEmbedderDegradedAttribute:
    def test_default_degraded_is_false(self):
        from butler.memory.embedding import HashingEmbedder

        emb = HashingEmbedder()
        assert emb.degraded is False

    def test_degraded_kwarg_sets_true(self):
        from butler.memory.embedding import HashingEmbedder

        emb = HashingEmbedder(degraded=True)
        assert emb.degraded is True

    def test_existing_dimension_kwarg_still_works(self):
        """R2-3 fix must not break existing callers."""
        from butler.memory.embedding import HashingEmbedder

        emb = HashingEmbedder(dimension=64)
        assert emb.dimension == 64
        assert emb.degraded is False  # default

    def test_existing_model_id_kwarg_still_works(self):
        from butler.memory.embedding import HashingEmbedder

        emb = HashingEmbedder(model_id="custom-x")
        assert emb.model_id == "custom-x"
        assert emb.degraded is False

    def test_requested_provider_and_model_default_empty(self):
        """Non-degraded HashingEmbedder has no 'requested' info."""
        from butler.memory.embedding import HashingEmbedder

        emb = HashingEmbedder()
        assert emb.requested_provider == ""
        assert emb.requested_model == ""

    def test_requested_provider_and_model_round_trip(self):
        from butler.memory.embedding import HashingEmbedder

        emb = HashingEmbedder(
            degraded=True,
            requested_provider="openai",
            requested_model="text-embedding-3-small",
        )
        assert emb.degraded is True
        assert emb.requested_provider == "openai"
        assert emb.requested_model == "text-embedding-3-small"


# ── 2. Other Embedder classes expose .degraded (default False) ─────────────


@pytest.mark.module_test
class TestOtherEmbeddersExposeDegraded:
    def test_openai_embedder_degraded_false(self):
        from butler.memory.embedding import OpenAIEmbedder

        emb = OpenAIEmbedder(api_key="k", model="m")
        assert emb.degraded is False

    def test_minimax_embedder_degraded_false(self):
        from butler.memory.embedding import MinimaxEmbedder

        emb = MinimaxEmbedder(api_key="k", model="m")
        assert emb.degraded is False

    def test_fastembed_embedder_degraded_false(self):
        from butler.memory.embedding import FastEmbedEmbedder

        emb = FastEmbedEmbedder(model_name="m")
        assert emb.degraded is False


# ── 3. _CachedEmbedder proxies .degraded ──────────────────────────────────


@pytest.mark.module_test
class TestCachedEmbedderProxiesDegraded:
    def test_cached_wrapper_proxies_degraded_false(self):
        from butler.memory.embedding import _CachedEmbedder

        class _FakeEmb:
            model_id = "fake-v1"
            dimension = 4
            degraded = False

            def embed(self, text):
                return [0.0] * 4

        cached = _CachedEmbedder(_FakeEmb(), max_size=8)
        assert cached.degraded is False

    def test_cached_wrapper_proxies_degraded_true(self):
        from butler.memory.embedding import _CachedEmbedder

        class _FakeEmb:
            model_id = "fake-v1"
            dimension = 4
            degraded = True

            def embed(self, text):
                return [0.0] * 4

        cached = _CachedEmbedder(_FakeEmb(), max_size=8)
        assert cached.degraded is True


# ── 4. fastembed fallback path → degraded + ERROR log ─────────────────────


@pytest.mark.module_test
class TestFastembedFallbackPath:
    def test_fastembed_unavailable_returns_degraded_embedder(self):
        from butler.memory import embedding as emb_mod
        from butler.memory.embedding import HashingEmbedder, _build_raw_embedder

        with patch.object(emb_mod, "_resolve_fastembed", return_value=None):
            result = _build_raw_embedder("fastembed", "BAAI/bge-small-en-v1.5")
        assert isinstance(result, HashingEmbedder)
        assert result.degraded is True
        assert result.requested_provider == "fastembed"
        assert result.requested_model == "BAAI/bge-small-en-v1.5"

    def test_fastembed_unavailable_logs_error(self, caplog):
        from butler.memory import embedding as emb_mod
        from butler.memory.embedding import _build_raw_embedder

        caplog.set_level(logging.DEBUG, logger="butler.memory.embedding")
        with patch.object(emb_mod, "_resolve_fastembed", return_value=None):
            _build_raw_embedder("fastembed", "BAAI/bge-small-en-v1.5")

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, "fastembed fallback must escalate to ERROR for audibility"
        msg_text = " ".join(r.getMessage() for r in error_records)
        assert "fastembed" in msg_text.lower() or "hashing" in msg_text.lower()

        # Critical audit contract: warning level is no longer the only signal.
        warning_only = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "HashingEmbedder" in r.getMessage()
        ]
        assert not warning_only, "warning is too quiet for recall-quality collapse"

    def test_resolve_fastembed_init_exc_logs_with_exc_info(self, caplog):
        """When fastembed import succeeds but probe fails, log error with exc_info."""
        from butler.memory import embedding as emb_mod

        caplog.set_level(logging.DEBUG, logger="butler.memory.embedding")

        class _BoomEmbedder:
            def __init__(self, *, model_name: str = "") -> None:
                self._model_name = model_name

            def embed(self, text):
                raise RuntimeError("probe timeout")

        with patch.object(emb_mod, "FastEmbedEmbedder", _BoomEmbedder):
            result = emb_mod._resolve_fastembed("test-model")
        assert result is None

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, "init-time fastembed failure must log ERROR"
        rec = next(
            r for r in error_records if "fastembed" in r.getMessage().lower()
        )
        assert rec.exc_info is not None, "exc_info must capture the traceback"

    def test_resolve_fastembed_import_error_logs_error(self, caplog):
        """ImportError path: fastembed not installed → logger.error."""
        from butler.memory import embedding as emb_mod

        caplog.set_level(logging.DEBUG, logger="butler.memory.embedding")

        class _NoImportEmbedder:
            def __init__(self, *, model_name: str = "") -> None:
                raise ImportError("fastembed is not installed")

        with patch.object(emb_mod, "FastEmbedEmbedder", _NoImportEmbedder):
            result = emb_mod._resolve_fastembed("test-model")
        assert result is None

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, "missing install must escalate to ERROR per R2-3"


# ── 5. API key missing path → degraded + ERROR log ───────────────────────


@pytest.mark.module_test
class TestApiKeyMissingPath:
    def test_openai_no_key_returns_degraded(self, monkeypatch):
        from butler.memory.embedding import HashingEmbedder, _build_raw_embedder

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = _build_raw_embedder("openai", "text-embedding-3-small")
        assert isinstance(result, HashingEmbedder)
        assert result.degraded is True
        assert result.requested_provider == "openai"
        assert result.requested_model == "text-embedding-3-small"

    def test_openai_no_key_logs_error(self, monkeypatch, caplog):
        from butler.memory.embedding import _build_raw_embedder

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        caplog.set_level(logging.DEBUG, logger="butler.memory.embedding")

        _build_raw_embedder("openai", "text-embedding-3-small")

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, "missing API key must escalate to ERROR per R2-3"


# ── 6. API probe failure path → degraded + ERROR + exc_info ──────────────


@pytest.mark.module_test
class TestApiProbeFailurePath:
    def test_probe_failure_returns_degraded(self, monkeypatch):
        from butler.memory import embedding as emb_mod
        from butler.memory.embedding import HashingEmbedder, _build_raw_embedder

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

        class _BoomApi:
            model_id = "openai/test-embedding-3-small"
            dimension = 1536
            degraded = False

            def embed(self, text):
                raise RuntimeError("auth failed")

        with patch.object(
            emb_mod, "_resolve_api_embedder", return_value=_BoomApi()
        ):
            result = _build_raw_embedder("openai", "text-embedding-3-small")
        assert isinstance(result, HashingEmbedder)
        assert result.degraded is True
        assert result.requested_provider == "openai"
        assert result.requested_model == "text-embedding-3-small"

    def test_probe_failure_logs_error_with_exc_info(self, monkeypatch, caplog):
        from butler.memory import embedding as emb_mod
        from butler.memory.embedding import _build_raw_embedder

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

        class _BoomApi:
            model_id = "openai/x"
            dimension = 1536
            degraded = False

            def embed(self, text):
                raise RuntimeError("auth failed")

        caplog.set_level(logging.DEBUG, logger="butler.memory.embedding")
        with patch.object(
            emb_mod, "_resolve_api_embedder", return_value=_BoomApi()
        ):
            _build_raw_embedder("openai", "text-embedding-3-small")

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, "probe failure must escalate to ERROR"
        rec = next(
            r for r in error_records if "probe failed" in r.getMessage().lower()
        )
        assert rec.exc_info is not None, "exc_info must capture the traceback"

        # Audit contract: warning is no longer the only signal for hard failure.
        warning_only = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING
            and "probe failed" in r.getMessage().lower()
        ]
        assert not warning_only, "warning is too quiet for recall-quality collapse"


# ── 7. Success path → degraded=False ──────────────────────────────────────


@pytest.mark.module_test
class TestSuccessPathNotDegraded:
    def test_local_hashing_provider_not_degraded(self):
        """Explicit local hashing provider is not a fallback — degraded=False."""
        from butler.memory.embedding import HashingEmbedder, _build_raw_embedder

        result = _build_raw_embedder("local", "hashing-v1")
        assert isinstance(result, HashingEmbedder)
        assert result.degraded is False

    def test_api_probe_success_not_degraded(self, monkeypatch):
        from butler.memory import embedding as emb_mod
        from butler.memory.embedding import _build_raw_embedder

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")

        class _OkApi:
            model_id = "openai/text-embedding-3-small"
            dimension = 1536
            degraded = False

            def embed(self, text):
                return [0.1] * 1536

        with patch.object(
            emb_mod, "_resolve_api_embedder", return_value=_OkApi()
        ):
            result = _build_raw_embedder("openai", "text-embedding-3-small")
        assert result.degraded is False


# ── 8. /诊断 surface — collect_memory_layer_stats exposes embedding_degraded ──


@pytest.mark.module_test
class TestDiagnosticsSurfacesDegraded:
    def test_collect_stats_reads_degraded_from_embedder(self):
        from butler.memory.diagnostics import collect_memory_layer_stats
        from butler.memory.embedding import HashingEmbedder

        fake_embedder = HashingEmbedder(
            degraded=True,
            requested_provider="openai",
            requested_model="text-embedding-3-small",
        )

        # Build orchestrator with a semantic index exposing fake_embedder.
        sem = MagicMock()
        sem.count_rows.return_value = 0
        sem.model_id = "hashing-v1"
        sem.count_by_source.return_value = 0
        sem.embedder = fake_embedder

        bm = MagicMock()
        bm.profile = None
        bm.semantic = sem
        bm.triplet_index.return_value = None
        bm.experience = None

        orch = MagicMock()
        orch.butler_memory = bm
        orch._project_memory = None
        orch.project_manager.get_current.return_value = None

        stats = collect_memory_layer_stats(orch, session_key="s-r2-3")

        assert stats["embedding_degraded"] is True
        assert stats["embedding_requested_provider"] == "openai"
        assert stats["embedding_requested_model"] == "text-embedding-3-small"
        assert stats["embedding_used_model"] == "hashing-v1"

    def test_collect_stats_degraded_false_when_embedder_ok(self):
        from butler.memory.diagnostics import collect_memory_layer_stats
        from butler.memory.embedding import HashingEmbedder

        fake_embedder = HashingEmbedder()  # default: degraded=False

        sem = MagicMock()
        sem.count_rows.return_value = 0
        sem.model_id = "hashing-v1"
        sem.count_by_source.return_value = 0
        sem.embedder = fake_embedder

        bm = MagicMock()
        bm.profile = None
        bm.semantic = sem
        bm.triplet_index.return_value = None
        bm.experience = None

        orch = MagicMock()
        orch.butler_memory = bm
        orch._project_memory = None
        orch.project_manager.get_current.return_value = None

        stats = collect_memory_layer_stats(orch, session_key="s-r2-3-ok")

        assert stats["embedding_degraded"] is False


# ── 9. /诊断 display — format_rag_diagnostic_lines shows degraded ─────────


@pytest.mark.module_test
class TestFormatRagDiagnosticShowsEmbeddingDegraded:
    def test_format_shows_embedding_degraded_line(self):
        from butler.ops.rag_diagnostics import format_rag_diagnostic_lines

        lines = format_rag_diagnostic_lines(
            {
                "semantic_enabled": True,
                "vector_rows": 0,
                "embedding_degraded": True,
                "embedding_requested_provider": "openai",
                "embedding_requested_model": "text-embedding-3-small",
                "embedding_used_model": "hashing-v1",
            }
        )

        degraded = [ln for ln in lines if "嵌入" in ln and "降级" in ln]
        assert degraded, (
            "audit R2-3 requires a visible '嵌入质量降级' line in /诊断"
        )
        text = "\n".join(degraded)
        assert "openai" in text
        assert "text-embedding-3-small" in text
        assert "hashing-v1" in text

    def test_format_omits_degraded_line_when_false(self):
        from butler.ops.rag_diagnostics import format_rag_diagnostic_lines

        lines = format_rag_diagnostic_lines(
            {
                "semantic_enabled": True,
                "vector_rows": 12,
                "embedding_degraded": False,
            }
        )
        degraded = [ln for ln in lines if "嵌入" in ln and "降级" in ln]
        assert not degraded


# ── 10. Embedder Protocol declares .degraded ──────────────────────────────


@pytest.mark.module_test
class TestEmbedderProtocolDegraded:
    def test_all_concrete_embedders_expose_degraded(self):
        """All Embedder implementations must expose `.degraded` per the Protocol."""
        from butler.memory.embedding import (
            FastEmbedEmbedder,
            HashingEmbedder,
            MinimaxEmbedder,
            OpenAIEmbedder,
        )

        # All four concrete embedders must define .degraded
        assert hasattr(HashingEmbedder(), "degraded")
        assert hasattr(OpenAIEmbedder(api_key="k", model="m"), "degraded")
        assert hasattr(MinimaxEmbedder(api_key="k", model="m"), "degraded")
        assert hasattr(FastEmbedEmbedder(model_name="m"), "degraded")
