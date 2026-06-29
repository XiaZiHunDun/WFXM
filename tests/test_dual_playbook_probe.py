"""B1 dual-playbook static probe and scenario manifest."""

from __future__ import annotations

from pathlib import Path

import pytest

from butler.gateway.wechat_scenario_sim import load_wechat_scenario_manifest
from butler.ops.dual_playbook_probe import (
    MAINTENANCE_PROBE_TEXT,
    NEW_BOOK_PROBE_TEXT,
    SCENARIO_MANIFEST,
    run_dual_playbook_static_probe,
)


@pytest.mark.unit
def test_dual_playbook_static_probe_passes_on_repo():
    root = Path(__file__).resolve().parents[1]
    out = run_dual_playbook_static_probe(root=root)
    assert out["ok"], out.get("errors")
    assert out["details"]["lifecycle"] == "complete"
    assert "COMPLETE" in out["details"]["workflow_phase"].upper()


@pytest.mark.unit
def test_dual_playbook_doc_contains_probe_phrases():
    doc = Path("projects/LingWen1/docs/dual-playbook.md")
    text = doc.read_text(encoding="utf-8")
    assert MAINTENANCE_PROBE_TEXT in text
    assert NEW_BOOK_PROBE_TEXT in text


def _norm_probe_text(text: str) -> str:
    return "".join(text.split())


@pytest.mark.unit
def test_dual_playbook_scenario_manifest_loads():
    manifest = load_wechat_scenario_manifest(filename=SCENARIO_MANIFEST)
    assert manifest is not None
    assert manifest.tracks
    track = manifest.tracks[0]
    assert len(track.cases) >= 2
    texts = {_norm_probe_text(c.user_text) for c in track.cases}
    assert _norm_probe_text(MAINTENANCE_PROBE_TEXT) in texts
    assert _norm_probe_text(NEW_BOOK_PROBE_TEXT) in texts
