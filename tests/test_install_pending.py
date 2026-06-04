"""Skill install confirmation (WeChat / CLI)."""

from __future__ import annotations

import time

import pytest

from butler.registry.install_pending import (
    PendingSkillInstall,
    clear_pending,
    get_pending,
    save_pending,
)
from butler.registry.registry_errors import InstallConfirmationRequired
from butler.registry.skill_service import SkillRegistryService
from butler.registry.skill_types import SkillSearchHit


@pytest.mark.unit
def test_community_install_requires_confirmation(tmp_path, monkeypatch):
    monkeypatch.delenv("BUTLER_REGISTRY_AUTO_INSTALL", raising=False)

    svc = SkillRegistryService(tenant_id="default")
    assert svc.needs_install_confirmation(trust="community") is True
    assert svc.needs_install_confirmation(trust="builtin") is False
    assert svc.needs_install_confirmation(trust="trusted", confirmed=True) is False

    hit = SkillSearchHit(
        name="fake-community",
        description="x",
        source="clawhub",
        identifier="clawhub:demo-skill",
        trust="community",
    )
    bundle = __import__(
        "butler.registry.skill_types", fromlist=["SkillBundle"]
    ).SkillBundle(
        name="demo-skill",
        files={"SKILL.md": "---\nname: demo-skill\ndescription: x\n---\n\nb\n"},
        source="clawhub",
        identifier="clawhub:demo-skill",
        trust="community",
    )

    monkeypatch.setattr(svc, "inspect", lambda _: hit)
    monkeypatch.setattr(svc, "fetch_bundle", lambda _: bundle)

    with pytest.raises(InstallConfirmationRequired):
        svc.install("clawhub:demo-skill", confirmed=False, force=False)


@pytest.mark.unit
def test_pending_save_and_confirm(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.registry.install_pending.get_butler_home", lambda: tmp_path)
    monkeypatch.setattr(
        "butler.registry.install_pending._pending_path",
        lambda: tmp_path / "pending-installs.json",
    )

    row = PendingSkillInstall(
        identifier="clawhub:demo",
        name="demo",
        description="d",
        source="clawhub",
        trust="community",
        session_key="wx:1",
        platform="wechat",
        external_id="u1",
        requested_at=time.time(),
    )
    save_pending(row)
    got = get_pending(session_key="wx:1", platform="wechat", external_id="u1")
    assert got is not None
    assert got.identifier == "clawhub:demo"
    clear_pending(session_key="wx:1", platform="wechat", external_id="u1")
    assert get_pending(session_key="wx:1", platform="wechat", external_id="u1") is None


@pytest.mark.unit
def test_gateway_confirm_handler_requires_owner(monkeypatch):
    from butler.gateway.registry_commands import handle_confirm_install_command

    monkeypatch.setattr(
        "butler.gateway.owner_gate.is_gateway_owner",
        lambda **_: False,
    )
    out = handle_confirm_install_command(
        "clawhub:x",
        platform="wechat",
        external_id="u1",
        session_key="wx:1",
    )
    assert "Owner" in out or "owner" in out.lower()
