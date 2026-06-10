"""P3: Optional live LLM smoke for Butler gateway (WeChat code path, no iLink HTTP).

Skipped by default (``not live_llm``). Run explicitly:

    BUTLER_RUN_REAL_API_SMOKE=1 MINIMAX_API_KEY=... PYTHONPATH=. \\
        pytest -m live_llm tests/test_wechat_gateway_live_smoke.py -v
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from butler.config import ModelConfig, get_butler_settings, reload_butler_settings
from butler.gateway.message_handler import ButlerMessageHandler
from butler.tenant import tenant_memory_dir
from butler.transport.providers import get_provider
from tests.test_real_api_smoke import _require_smoke_enabled

pytestmark = pytest.mark.live_llm

GW_SMOKE_TOKEN = "gw-smoke-ok"
PROFILE_NICK = "主公LIVEP3"


def _require_minimax_for_gateway() -> None:
    _require_smoke_enabled()
    profile = get_provider("minimax")
    if profile is None:
        pytest.skip("minimax provider profile missing")
    if not profile.resolve_api_key():
        pytest.skip(f"set one of {profile.env_vars} for gateway live smoke")
    reload_butler_settings()
    settings = get_butler_settings()
    mc = settings.get_model_config("butler")
    provider = (mc.provider or settings.default_provider or "minimax").strip().lower()
    if provider != "minimax":
        pytest.skip(f"butler role is {provider}, configure minimax for gateway live smoke")
    model_override = os.getenv("BUTLER_SMOKE_MINIMAX_MODEL", "").strip()
    if model_override:
        settings.set_runtime_model_override(
            "butler", ModelConfig(provider="minimax", model=model_override)
        )


def _write_owner_profile(butler_home, entries: list[str]) -> None:
    mem_dir = tenant_memory_dir(butler_home, "default")
    mem_dir.mkdir(parents=True, exist_ok=True)
    (mem_dir / "profile.json").write_text(
        json.dumps({"entries": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@pytest.mark.live_llm
def test_live_gateway_one_turn_minimax(tmp_butler_home, tmp_path, monkeypatch):
    """Real MiniMax via gateway message_handler (one user turn)."""
    _require_minimax_for_gateway()
    empty_projects = tmp_path / "empty-projects"
    empty_projects.mkdir()
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(empty_projects))

    from tests.test_gateway_handler import _reset_singletons

    _reset_singletons()
    handler = ButlerMessageHandler(channel="gateway")
    sk = "wechat:live-smoke"

    with patch("butler.session.lifecycle.sync_turn_memory", return_value={}):
        out = handler.handle_message(
            f"请只回复这一行英文，不要其它内容：{GW_SMOKE_TOKEN}",
            session_key=sk,
            platform="wechat",
        )

    assert out
    assert "<think>" not in out.lower()
    lowered = out.lower()
    assert GW_SMOKE_TOKEN in lowered or GW_SMOKE_TOKEN.replace("-", " ") in lowered


@pytest.mark.live_llm
def test_live_gateway_owner_profile_nickname(tmp_butler_home, tmp_path, monkeypatch):
    """With profile.json set, ask how Butler addresses the owner (real LLM)."""
    _require_minimax_for_gateway()
    _write_owner_profile(
        tmp_butler_home,
        [f"称呼：{PROFILE_NICK}；微信回复宜短。"],
    )
    empty_projects = tmp_path / "empty-projects"
    empty_projects.mkdir()
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(empty_projects))

    from tests.test_gateway_handler import _reset_singletons

    _reset_singletons()
    handler = ButlerMessageHandler(channel="gateway")
    sk = "wechat:live-profile"

    handler.handle_message("/新对话", session_key=sk, platform="wechat")
    with patch("butler.session.lifecycle.sync_turn_memory", return_value={}):
        out = handler.handle_message(
            "用一句话说明你会怎么称呼我（只答称呼，不要解释）。",
            session_key=sk,
            platform="wechat",
        )

    assert PROFILE_NICK in out or "主公" in out


def _setup_live_project(tmp_path, monkeypatch, *, marker_line: str) -> Path:
    import yaml

    from tests.test_gateway_handler import _reset_singletons

    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    proj = projects_dir / "live-gw-proj"
    proj.mkdir()
    (proj / "docs").mkdir()
    (proj / "README.md").write_text(
        f"# Live gateway smoke\n{marker_line}\n",
        encoding="utf-8",
    )
    (proj / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "live-gw-proj",
                "type": "software",
                "description": "Live gateway smoke project",
                "workspace": str(proj),
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))
    _reset_singletons()
    return proj


@pytest.mark.live_llm
def test_live_gateway_read_file_no_delegate(tmp_butler_home, tmp_path, monkeypatch):
    """Smoke step 3: real LLM reads project README (no delegate_task)."""
    _require_minimax_for_gateway()
    marker = "LIVE_READFILE_MARKER_XYZ"
    _setup_live_project(tmp_path, monkeypatch, marker_line=marker)

    from tests.test_gateway_handler import _reset_singletons

    _reset_singletons()
    handler = ButlerMessageHandler(channel="gateway")
    handler._orchestrator.project_manager.switch_project("live-gw-proj")
    sk = "wechat:live-readfile"

    with patch("butler.session.lifecycle.sync_turn_memory", return_value={}):
        out = handler.handle_message(
            f"请用 read_file 读取当前项目 README，在回复里原样包含这一行：{marker}。"
            "不要 delegate_task，不要委派。",
            session_key=sk,
            platform="wechat",
        )

    assert marker in out
    assert len(out) <= 2500


@pytest.mark.live_llm
def test_live_gateway_delegate_writes_file(tmp_butler_home, tmp_path, monkeypatch):
    """Smoke steps 4–4c: real delegate writes a file under project docs/."""
    _require_minimax_for_gateway()
    _setup_live_project(tmp_path, monkeypatch, marker_line="live base")
    proj = tmp_path / "projects" / "live-gw-proj"
    doc_rel = "docs/live-delegate-smoke.md"
    doc_path = proj / doc_rel
    body_marker = "DELEGATE_LIVE_OK"

    from tests.test_gateway_handler import _reset_singletons

    monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "live-delegate")
    monkeypatch.setenv("BUTLER_ONBOARDING_WELCOME", "0")
    _reset_singletons()
    handler = ButlerMessageHandler(channel="gateway")
    handler._orchestrator.project_manager.switch_project("live-gw-proj")
    handler._orchestrator.project_manager.switch_project_for_chat(
        platform="wechat",
        chat_id="live-delegate",
        name="live-gw-proj",
    )
    sk = handler.resolve_session_key(
        platform="wechat",
        external_id="live-delegate",
    )

    with patch("butler.session.lifecycle.sync_turn_memory", return_value={}):
        out = handler.handle_message(
            f"请交给内容代理：用 write_file 工具在 {doc_rel} 写一行正文「{body_marker}」，"
            "不要用 terminal，不要改其它文件。",
            session_key=sk,
            platform="wechat",
            external_id="live-delegate",
        )

    assert doc_path.is_file(), f"expected file at {doc_path}; gateway out={out[:500]!r}"
    assert body_marker in doc_path.read_text(encoding="utf-8")
    assert len(out) <= 2500
    assert "详细" in out or "代理" in out or "完成" in out


def test_live_gateway_smoke_skipped_without_flag(monkeypatch):
    monkeypatch.delenv("BUTLER_RUN_REAL_API_SMOKE", raising=False)
    with pytest.raises(pytest.skip.Exception):
        _require_smoke_enabled()
