"""Sprint 18-2: BUTLER_PROJECT_CREATE_OPEN prod 环境拒绝 (Sprint 18-2 subagent A CRITICAL-1).

Sprint 18 subagent A 安全审计: BUTLER_PROJECT_CREATE_OPEN=1 是全局越权开关.
任何平台任何 external_id 都识别为 owner, 一旦误带 .env 上线 / CI 残留 /
注入到 .env 即被绕过 owner-only 指令 (/项目 新建, /权限, /批准执行 等).

修复: 当 BUTLER_ENV=prod 时, 即使 BUTLER_PROJECT_CREATE_OPEN=1 也必须返回 False.
is_gateway_owner 在 prod 模式下 fail-closed (不允许任何 BYPASS).

dev/test 行为不变: BUTLER_ENV 未设或为 dev/test 时 BYPASS 仍生效.
"""

from __future__ import annotations

import pytest

from butler.gateway.owner_gate import is_gateway_owner


@pytest.mark.unit
class TestProdRejectsBypass:
    """Sprint 18-2 SEC-18-2-1: prod 环境禁止 BYPASS 越权开关."""

    def test_prod_env_denies_bypass_for_any_platform(self, monkeypatch):
        """BUTLER_ENV=prod + BYPASS=1 → 任何平台都必须拒绝.

        防误带 .env 上线 / CI 残留 / 注入到 .env.
        """
        monkeypatch.setenv("BUTLER_ENV", "prod")
        monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")
        # 任意 platform + 任意 external_id — 全拒
        assert not is_gateway_owner(platform="wechat", external_id="owner1")
        assert not is_gateway_owner(platform="cli", external_id="any")
        assert not is_gateway_owner(platform="telegram", external_id="attacker")

    def test_prod_env_denies_without_owner_allowlist(self, monkeypatch):
        """prod + 无 owner 列表 → fail-closed (Sprint 8 行为不变)."""
        monkeypatch.setenv("BUTLER_ENV", "prod")
        monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
        monkeypatch.delenv("BUTLER_OWNER_WECHAT_ID", raising=False)
        monkeypatch.delenv("WECHAT_ALLOWED_USERS", raising=False)
        monkeypatch.delenv("BUTLER_GATEWAY_ALLOWLIST", raising=False)
        assert not is_gateway_owner(platform="wechat", external_id="anyone")

    def test_prod_env_owner_allowlist_still_works(self, monkeypatch):
        """prod 环境下 owner 显式 allowlist 仍生效 (BYPASS 禁用但配置 owner 仍可用)."""
        monkeypatch.setenv("BUTLER_ENV", "prod")
        monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
        monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "owner1")
        # owner 在白名单 → 放行
        assert is_gateway_owner(platform="wechat", external_id="owner1")
        # 非 owner → 拒
        assert not is_gateway_owner(platform="wechat", external_id="stranger")


@pytest.mark.unit
class TestDevEnvBypassUnchanged:
    """dev / test 环境 BYPASS 行为不变 (Sprint 8 行为不变)."""

    def test_dev_env_bypass_still_works(self, monkeypatch):
        """BUTLER_ENV=dev + BYPASS=1 → 放行 (开发体验)."""
        monkeypatch.setenv("BUTLER_ENV", "dev")
        monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")
        assert is_gateway_owner(platform="cli", external_id="any")

    def test_unset_env_bypass_still_works(self, monkeypatch):
        """BUTLER_ENV 未设 (默认) + BYPASS=1 → 放行 (向后兼容)."""
        monkeypatch.delenv("BUTLER_ENV", raising=False)
        monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")
        assert is_gateway_owner(platform="cli", external_id="any")

    def test_test_env_bypass_still_works(self, monkeypatch):
        """BUTLER_ENV=test + BYPASS=1 → 放行 (CI 集成测试)."""
        monkeypatch.setenv("BUTLER_ENV", "test")
        monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")
        assert is_gateway_owner(platform="cli", external_id="any")

    @pytest.mark.parametrize("env_value", ["PROD", "Prod", "prOd"])
    def test_prod_case_insensitive(self, monkeypatch, env_value):
        """prod 字符串大小写不敏感 (防御性: 但ler 启动时也做 normalize)."""
        monkeypatch.setenv("BUTLER_ENV", env_value)
        monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")
        assert not is_gateway_owner(platform="cli", external_id="any")


@pytest.mark.unit
class TestEnvUnchangedRegression:
    """确保不破坏其他既有 owner gate 行为."""

    def test_empty_allowlist_denies_all(self, monkeypatch):
        """Sprint 8 行为: owner 列表空 + 无 BYPASS → 拒绝 (回归)."""
        monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
        monkeypatch.delenv("BUTLER_ENV", raising=False)
        monkeypatch.delenv("BUTLER_OWNER_WECHAT_ID", raising=False)
        monkeypatch.delenv("WECHAT_ALLOWED_USERS", raising=False)
        monkeypatch.delenv("BUTLER_GATEWAY_ALLOWLIST", raising=False)
        assert not is_gateway_owner(platform="wechat", external_id="anyone")

    def test_wechat_allowlist_unchanged(self, monkeypatch):
        """Sprint 8 行为: owner + friend 通过, stranger 拒绝 (回归)."""
        monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
        monkeypatch.delenv("BUTLER_ENV", raising=False)
        monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "owner1")
        monkeypatch.setenv("WECHAT_ALLOWED_USERS", "friend2")
        assert is_gateway_owner(platform="wechat", external_id="owner1")
        assert is_gateway_owner(platform="wechat", external_id="friend2")
        assert not is_gateway_owner(platform="wechat", external_id="stranger")
