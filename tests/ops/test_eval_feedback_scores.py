"""eval_feedback LangFuse score API compatibility."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from butler.ops.eval_feedback import read_recent_scores


def test_read_recent_scores_uses_api_score_get(monkeypatch):
    monkeypatch.setenv("BUTLER_LANGFUSE_ENABLED", "1")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    score = MagicMock()
    score.name = "dev_benchmark.pass_rate"
    score.value = 0.9
    score.comment = ""
    score.trace_id = "t1"
    score.timestamp = 9999999999.0

    page = MagicMock()
    page.data = [score]

    mock_client = MagicMock()
    mock_client.api.score.get.return_value = page

    with patch("langfuse.Langfuse", return_value=mock_client):
        rows = read_recent_scores(lookback_hours=24, limit=10)

    mock_client.api.score.get.assert_called_once()
    assert len(rows) == 1
    assert rows[0].name == "dev_benchmark.pass_rate"
    mock_client.shutdown.assert_called_once()
