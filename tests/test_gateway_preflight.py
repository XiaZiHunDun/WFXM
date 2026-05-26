"""Regression tests for scripts/lib/butler-gateway-preflight.sh."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


_REPO = Path(__file__).resolve().parents[1]
_PREFLIGHT = _REPO / "scripts" / "lib" / "butler-gateway-preflight.sh"


def _make_gateway_root(tmp_path: Path, *, env_lines: list[str]) -> tuple[Path, Path]:
    root = tmp_path / "gateway-root"
    root.mkdir()
    (root / "butler").symlink_to(_REPO / "butler", target_is_directory=True)
    (root / ".env").write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    butler_home = tmp_path / "butler-home"
    (butler_home / "wechat" / "accounts").mkdir(parents=True)
    (butler_home / "config.yaml").write_text("default_model: test\n", encoding="utf-8")
    (butler_home / "wechat" / "accounts" / "demo.json").write_text("{}", encoding="utf-8")
    return root, butler_home


def _run_preflight(root: Path, butler_home: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "BUTLER_HOME": str(butler_home),
            "BUTLER_OWNER_WECHAT_ID": "",
            "BUTLER_GATEWAY_ALLOWLIST": "",
            "WECHAT_ALLOWED_USERS": "",
            "WECHAT_GROUP_ALLOWED_USERS": "",
        }
    )
    command = f'export ROOT="{root}"; source "{_PREFLIGHT}"; butler_gateway_preflight'
    return subprocess.run(
        ["bash", "-lc", command],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_gateway_preflight_accepts_wechat_allowed_users(tmp_path):
    root, butler_home = _make_gateway_root(
        tmp_path,
        env_lines=[
            "MINIMAX_API_KEY=test-key",
            "WECHAT_TOKEN=test-token",
            "WECHAT_ACCOUNT_ID=test-account",
            "WECHAT_DM_POLICY=allowlist",
            "WECHAT_ALLOWED_USERS=u1,u2",
            "WECHAT_GROUP_POLICY=disabled",
            "BUTLER_TOOL_SAFE_ROOT=/tmp",
            "BUTLER_DEFAULT_PROJECT=Demo",
        ],
    )

    proc = _run_preflight(root, butler_home)

    assert "Gateway owner/allowlist configured" in proc.stdout
    assert "未配置 BUTLER_OWNER_WECHAT_ID / BUTLER_GATEWAY_ALLOWLIST / WECHAT_ALLOWED_USERS" not in proc.stdout


def test_gateway_preflight_warns_on_group_open(tmp_path):
    root, butler_home = _make_gateway_root(
        tmp_path,
        env_lines=[
            "MINIMAX_API_KEY=test-key",
            "WECHAT_TOKEN=test-token",
            "WECHAT_ACCOUNT_ID=test-account",
            "WECHAT_DM_POLICY=disabled",
            "WECHAT_GROUP_POLICY=open",
            "BUTLER_OWNER_WECHAT_ID=owner1",
            "BUTLER_TOOL_SAFE_ROOT=/tmp",
            "BUTLER_DEFAULT_PROJECT=Demo",
        ],
    )

    proc = _run_preflight(root, butler_home)

    assert "WECHAT_GROUP_POLICY=open — group ingress is fully exposed" in proc.stdout


def test_gateway_preflight_normalizes_policy_case(tmp_path):
    root, butler_home = _make_gateway_root(
        tmp_path,
        env_lines=[
            "MINIMAX_API_KEY=test-key",
            "WECHAT_TOKEN=test-token",
            "WECHAT_ACCOUNT_ID=test-account",
            "WECHAT_DM_POLICY=Open",
            "BUTLER_OWNER_WECHAT_ID=owner1",
            "BUTLER_TOOL_SAFE_ROOT=/tmp",
            "BUTLER_DEFAULT_PROJECT=Demo",
        ],
    )

    proc = _run_preflight(root, butler_home)

    assert "WECHAT_DM_POLICY=open — set allowlist + WECHAT_ALLOWED_USERS before exposing the Bot" in proc.stdout


def test_gateway_preflight_treats_whitespace_allowlist_as_empty(tmp_path):
    root, butler_home = _make_gateway_root(
        tmp_path,
        env_lines=[
            "MINIMAX_API_KEY=test-key",
            "WECHAT_TOKEN=test-token",
            "WECHAT_ACCOUNT_ID=test-account",
            "WECHAT_DM_POLICY=allowlist",
            "WECHAT_ALLOWED_USERS=   ",
            "WECHAT_GROUP_POLICY=disabled",
            "BUTLER_TOOL_SAFE_ROOT=/tmp",
            "BUTLER_DEFAULT_PROJECT=Demo",
        ],
    )

    proc = _run_preflight(root, butler_home)

    assert "WECHAT_DM_POLICY=allowlist but WECHAT_ALLOWED_USERS is empty" in proc.stdout
    assert "未配置 BUTLER_OWNER_WECHAT_ID / BUTLER_GATEWAY_ALLOWLIST / WECHAT_ALLOWED_USERS" in proc.stdout
