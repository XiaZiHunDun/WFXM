"""Tests for publish preflight review_queue reader."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "projects"
    / "LingWen1"
    / "novel-factory"
    / "tools"
    / "publish"
    / "read_workflow_review.py"
)


def test_pending_count_from_review_queue(tmp_path):
    wf = tmp_path / "workflow_state.json"
    wf.write_text(
        json.dumps(
            {
                "review_queue": {
                    "pending": [{"id": 1}],
                    "in_review": [{"id": 2}, {"id": 3}],
                }
            }
        ),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "1 2 3"
