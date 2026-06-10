"""D3-6 experience mining — review, pending, ingest, gateway."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from butler.memory.experience_mining import (
    CandidateExperience,
    approve_pending,
    feeds_path,
    ingest_experiences,
    load_pending,
    mine_changelog,
    mine_feeds,
    pending_path,
    review_candidate,
    run_pipeline,
    save_pending,
)


@pytest.fixture(autouse=True)
def _isolate_butler_home(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_EXPERIENCE_MINING", "1")
    monkeypatch.setenv("BUTLER_EXPERIENCE_MINING_AUTO_INGEST", "0")
    yield


def test_review_candidate_approves_deployment():
    cand = CandidateExperience(
        source="workspace:Dockerfile",
        category="deployment",
        content="FROM python:3.12",
        confidence=0.8,
    )
    review = review_candidate(cand)
    assert review.status == "approved"
    assert review.experience is not None
    assert "T08" in review.experience.theorem_basis


def test_review_rejects_unmapped_category():
    cand = CandidateExperience(
        source="x",
        category="development_activity",
        content="edited file",
        confidence=0.4,
    )
    review = review_candidate(cand)
    assert review.status == "rejected"


def test_mine_changelog(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 1.2.0\n- Added mining\n\n## 1.1.0\n- Fix bug\n"
    )
    items = mine_changelog(tmp_path)
    assert len(items) >= 1
    assert items[0].category == "changelog"


def test_mine_feeds_jsonl(tmp_path, monkeypatch):
    feed = tmp_path / "feeds" / "experience_feeds.jsonl"
    feed.parent.mkdir(parents=True)
    feed.write_text(
        json.dumps({
            "source": "github:release",
            "content": "pytest 8.0 migration notes",
            "category": "external_feed",
            "confidence": 0.85,
            "tags": ["pytest"],
        })
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "butler.memory.experience_mining.feeds_path",
        lambda: feed,
    )
    items = mine_feeds(feed)
    assert len(items) == 1
    assert items[0].confidence == pytest.approx(0.85)


def test_pipeline_queues_pending(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM python:3.12")
    result = run_pipeline(tmp_path)
    assert result.report.candidates
    assert result.pending_saved >= 1
    assert load_pending()


def test_auto_ingest_high_confidence(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_EXPERIENCE_MINING_AUTO_INGEST", "1")
    (tmp_path / "CHANGELOG.md").write_text("## 2.0.0\n- Release mining pipeline\n")
    result = run_pipeline(tmp_path, auto_ingest=True, days=1)
    assert result.ingested >= 1
    from butler.memory.experience_mining import experience_library_path

    assert Path(experience_library_path()).is_file()


def test_approve_pending(tmp_path):
    cand = CandidateExperience(
        source="workspace:Makefile",
        category="build_system",
        content="all: echo hi",
        confidence=0.8,
    )
    review = review_candidate(cand)
    assert review.status == "approved"
    save_pending({
        cand.candidate_id(): {
            "candidate": {
                "source": cand.source,
                "category": cand.category,
                "content": cand.content,
                "confidence": cand.confidence,
                "tags": cand.tags,
                "metadata": cand.metadata,
                "timestamp": cand.timestamp,
            },
            "status": review.status,
            "reason": review.reason,
        }
    })
    counts = approve_pending([cand.candidate_id()])
    assert counts["added"] == 1
    assert not load_pending()


def test_ingest_skips_duplicate(tmp_path):
    cand = CandidateExperience(
        source="workspace:requirements.txt",
        category="dependency",
        content="flask>=3",
        confidence=0.8,
    )
    review = review_candidate(cand)
    path = str(tmp_path / "coding_experiences.json")
    first = ingest_experiences([review.experience], xlib_path=path)
    second = ingest_experiences([review.experience], xlib_path=path)
    assert first["added"] == 1
    assert second["skipped"] == 1


def test_gateway_command_registered():
    from butler.gateway.command_registry import lookup

    cmd = lookup("/经验挖掘")
    assert cmd is not None
    assert cmd.handler is not None
