"""EXT-5 MarkItDown MCP manifest and integrate contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from butler.mcp.extension_manifest import get_manifest, get_manifest_by_server_id
from butler.mcp.extension_verify import verify_manifest
from butler.memory.document_ingest import ingest_enabled, ingest_output_root

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / ".butler/extensions/markitdown-ingest/manifest.yaml"


@pytest.mark.unit
def test_markitdown_manifest_exists():
    assert MANIFEST.is_file()


@pytest.mark.unit
def test_markitdown_manifest_fields():
    manifest = get_manifest("markitdown-ingest")
    assert manifest is not None
    assert manifest.ext_id == "ext-5"
    assert manifest.server_id == "markitdown"
    tools = {t.registered for t in manifest.tools}
    assert "mcp_markitdown_convert_to_markdown" in tools
    assert manifest.preflight_script.endswith("butler-extension-ext5-preflight.sh")


@pytest.mark.unit
def test_markitdown_manifest_by_server_id():
    manifest = get_manifest_by_server_id("markitdown")
    assert manifest is not None
    assert manifest.id == "markitdown-ingest"


@pytest.mark.unit
def test_markitdown_verify_secrets_only_no_golden(monkeypatch):
    manifest = get_manifest("markitdown-ingest")
    assert manifest is not None
    monkeypatch.delenv("BUTLER_MCP_ENABLED", raising=False)
    report = verify_manifest(manifest, run_golden=False)
    assert report.ok is True
    assert not report.errors


@pytest.mark.unit
def test_ingest_output_root_under_workspace(tmp_path):
    out = ingest_output_root(tmp_path)
    assert out == tmp_path / ".butler" / "ingest"


@pytest.mark.unit
def test_integrate_script_documents_uvx_markitdown():
    script = (ROOT / "scripts/butler-extension-ext5-integrate.sh").read_text(encoding="utf-8")
    assert "markitdown:" in script
    assert "uvx" in script
    assert "convert_to_markdown" in script
