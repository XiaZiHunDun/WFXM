"""PROD-P2-03: security trust patch batch tests."""

from __future__ import annotations

import pytest

from butler.config_secrets import (
    encrypt_secrets_file,
    provider_secrets,
    write_provider_secret,
)
from butler.gateway.pii_scrub import scrub_outbound_text
from butler.mcp.config import validate_http_url
from butler.mcp.types import McpServerConfig


def test_secrets_fernet_roundtrip(tmp_path, monkeypatch):
    pytest.importorskip("cryptography")
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_SECRETS_ENCRYPT", "1")
    monkeypatch.setenv("BUTLER_SECRETS_ENCRYPT_KEY", key)

    write_provider_secret("minimax", "sk-test-key", home=tmp_path)
    raw = (tmp_path / "secrets.yaml").read_text(encoding="utf-8")
    assert "FERNET:" in raw
    assert "sk-test-key" not in raw
    assert provider_secrets(tmp_path).get("minimax") == "sk-test-key"


def test_secrets_encrypt_migrate_apply(tmp_path, monkeypatch):
    pytest.importorskip("cryptography")
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_SECRETS_ENCRYPT", "1")
    monkeypatch.setenv("BUTLER_SECRETS_ENCRYPT_KEY", key)

    path = tmp_path / "secrets.yaml"
    path.write_text(
        "providers:\n  openai:\n    api_key: plain-key\n",
        encoding="utf-8",
    )
    path.chmod(0o600)

    dry = encrypt_secrets_file(home=tmp_path, dry_run=True)
    assert dry["ok"] is True
    assert int(dry.get("changed") or 0) == 1
    assert "FERNET:" not in path.read_text(encoding="utf-8")

    applied = encrypt_secrets_file(home=tmp_path, dry_run=False)
    assert applied["ok"] is True
    assert "FERNET:" in path.read_text(encoding="utf-8")
    assert provider_secrets(tmp_path).get("openai") == "plain-key"


@pytest.mark.parametrize(
    "url",
    [
        "http://10.0.0.1/mcp",
        "http://172.16.0.1/mcp",
        "http://192.168.1.1/mcp",
        "http://169.254.169.254/mcp",
    ],
)
def test_mcp_http_literal_private_ip_blocked(url):
    cfg = McpServerConfig(
        server_id="x",
        transport="http",
        url=url,
        hosts_allow=(url.split("//")[1].split("/")[0],),
    )
    assert validate_http_url(cfg) is not None


def test_mcp_http_private_ip_allowed_when_flag(monkeypatch):
    monkeypatch.setenv("BUTLER_MCP_HTTP_ALLOW_PRIVATE", "1")
    cfg = McpServerConfig(
        server_id="x",
        transport="http",
        url="http://10.0.0.1/mcp",
    )
    assert validate_http_url(cfg) is None


def test_pii_scrub_bearer_token():
    token = "Bearer " + ("a" * 32)
    out = scrub_outbound_text(f"Authorization: {token}")
    assert token not in out
    assert "Bearer" in out or "令牌" in out


def test_pii_scrub_aws_access_key():
    key = "AKIAIOSFODNN7EXAMPLE"
    out = scrub_outbound_text(f"AWS key {key}")
    assert key not in out


def test_pii_scrub_github_pat():
    pat = "ghp_" + ("x" * 36)
    out = scrub_outbound_text(f"github={pat}")
    assert pat not in out


def test_pii_scrub_link_local_ip():
    out = scrub_outbound_text("metadata at 169.254.169.254")
    assert "169.254.169.254" not in out
