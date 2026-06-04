"""LobeHub marketplace adapter tests (mocked)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from butler.registry.skill_sources.lobehub import LobeHubSource


@pytest.mark.unit
def test_lobehub_search_api():
    source = LobeHubSource()
    payload = {
        "items": [
            {
                "identifier": "acme/pdf-tool",
                "name": "PDF Tool",
                "description": "Process PDF files",
                "tags": ["pdf"],
                "installCount": 10,
            }
        ]
    }
    with patch.dict("os.environ", {"BUTLER_LOBEHUB_TOKEN": "test-token"}, clear=False):
        with patch("butler.registry.skill_sources.lobehub.lobehub_prefer_cli", return_value=False):
            with patch("butler.registry.skill_sources.lobehub.read_cache", return_value=None):
                with patch("butler.registry.skill_sources.lobehub.write_cache"):
                    with patch("butler.registry.skill_sources.lobehub.httpx.get") as mock_get:
                        mock_get.return_value = MagicMock(  # noqa: magicmock-no-spec — lobehub source httpx shim
                            status_code=200,
                            json=lambda: payload,
                        )
                        hits = source.search("pdf", limit=5)
    assert len(hits) == 1
    assert hits[0].identifier == "lobehub:acme/pdf-tool"
    assert hits[0].trust == "community"


@pytest.mark.unit
def test_lobehub_fetch_zip():
    import io
    import zipfile

    source = LobeHubSource()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("SKILL.md", "---\nname: pdf-tool\ndescription: x\n---\n\nBody\n")
    zip_bytes = buf.getvalue()

    with patch.dict("os.environ", {"BUTLER_LOBEHUB_TOKEN": "tok"}, clear=False):
        with patch("butler.registry.skill_sources.lobehub.lobehub_prefer_cli", return_value=False):
            with patch("butler.registry.skill_sources.lobehub._fetch_cli", return_value=None):
                with patch("butler.registry.skill_sources.lobehub.httpx.get") as mock_get:
                    mock_get.return_value = MagicMock(status_code=200, content=zip_bytes)  # noqa: magicmock-no-spec — lobehub source httpx shim
                    bundle = source.fetch("lobehub:acme/pdf-tool")
    assert bundle is not None
    assert "SKILL.md" in bundle.files
