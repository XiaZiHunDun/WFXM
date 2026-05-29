"""Tests for butler.core.transcript_search."""

import os

from butler.core.transcript_search import search_max_hits, search_max_sessions


class TestTranscriptSearchConfig:
    def test_default_max_sessions(self, monkeypatch):
        monkeypatch.delenv("BUTLER_TRANSCRIPT_SEARCH_MAX_SESSIONS", raising=False)
        assert search_max_sessions() == 5

    def test_custom_max_sessions(self, monkeypatch):
        monkeypatch.setenv("BUTLER_TRANSCRIPT_SEARCH_MAX_SESSIONS", "10")
        assert search_max_sessions() == 10

    def test_max_sessions_clamped(self, monkeypatch):
        monkeypatch.setenv("BUTLER_TRANSCRIPT_SEARCH_MAX_SESSIONS", "100")
        assert search_max_sessions() == 20

    def test_max_sessions_invalid(self, monkeypatch):
        monkeypatch.setenv("BUTLER_TRANSCRIPT_SEARCH_MAX_SESSIONS", "abc")
        assert search_max_sessions() == 5

    def test_default_max_hits(self, monkeypatch):
        monkeypatch.delenv("BUTLER_TRANSCRIPT_SEARCH_MAX_HITS", raising=False)
        assert search_max_hits() == 15

    def test_custom_max_hits(self, monkeypatch):
        monkeypatch.setenv("BUTLER_TRANSCRIPT_SEARCH_MAX_HITS", "30")
        assert search_max_hits() == 30

    def test_max_hits_clamped(self, monkeypatch):
        monkeypatch.setenv("BUTLER_TRANSCRIPT_SEARCH_MAX_HITS", "999")
        assert search_max_hits() == 50
