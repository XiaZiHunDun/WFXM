"""Runtime job schedule sanity for 灵文 pilot jobs."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
JOBS = ROOT / "projects" / "LingWen1" / "runtime" / "jobs.yaml"


def test_consistency_weekly_has_monday_schedule():
    data = yaml.safe_load(JOBS.read_text(encoding="utf-8"))
    jobs = {j["id"]: j for j in data.get("jobs") or []}
    cw = jobs.get("consistency-weekly")
    assert cw is not None
    assert cw.get("schedule") == "0 9 * * 1"
    assert cw.get("mode") == "readonly"
    assert cw.get("enabled") is True


def test_publish_archive_mutating_gated():
    data = yaml.safe_load(JOBS.read_text(encoding="utf-8"))
    jobs = {j["id"]: j for j in data.get("jobs") or []}
    pa = jobs.get("publish-archive")
    assert pa is not None
    assert pa.get("mode") == "mutating"
    assert pa.get("enabled") is False
    assert pa.get("approval", {}).get("required") is True


def test_publish_merge_mutating_gated():
    data = yaml.safe_load(JOBS.read_text(encoding="utf-8"))
    jobs = {j["id"]: j for j in data.get("jobs") or []}
    pm = jobs.get("publish-merge")
    assert pm is not None
    assert pm.get("mode") == "mutating"
    assert pm.get("enabled") is False
    assert "merge" in (pm.get("command") or [])
    assert pm.get("approval", {}).get("required") is True
