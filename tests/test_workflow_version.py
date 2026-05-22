"""Runtime command {workflow_version} substitution."""

from pathlib import Path

from butler.runtime.workflow_version import read_workflow_version, resolve_job_command


def test_read_workflow_version_from_state(tmp_path):
    nf = tmp_path / "novel-factory"
    nf.mkdir()
    (nf / "workflow_state.json").write_text('{"version": "v9.9"}', encoding="utf-8")
    assert read_workflow_version(tmp_path) == "v9.9"


def test_resolve_job_command_placeholder(tmp_path):
    cmd = ["bash", "run_publish.sh", "merge", "{workflow_version}"]
    nf = tmp_path / "novel-factory"
    nf.mkdir()
    (nf / "workflow_state.json").write_text('{"version": "v2.1"}', encoding="utf-8")
    assert resolve_job_command(cmd, tmp_path)[-1] == "v2.1"
