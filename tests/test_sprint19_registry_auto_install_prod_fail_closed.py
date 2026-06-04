"""Sprint 19-3: REGISTRY_AUTO_INSTALL prod fail-closed (Sprint 19 SEC-19-3).

Sprint 19 subagent A 安全审计: `needs_install_confirmation` 读
`BUTLER_REGISTRY_AUTO_INSTALL` 但**不检查 BUTLER_ENV=prod**. 攻击面:
运维误带 .env 上线 / CI 残留 / 镜像层注入 → 任意 community skill 可无确认
自动 install (clawhub / marketplace 任意代码 → 写 ~/.butler/skills/).

与 Sprint 18-2 SEC-18-2-1 (BUTLER_PROJECT_CREATE_OPEN prod 禁用) 同模式:
prod 环境硬拒越权 BYPASS, owner 行为仅依赖显式 allowlist.

修复: `needs_install_confirmation` 在 BUTLER_ENV=prod 时**忽略**该 env var,
community skill 始终走 confirmation 流程, fail-closed.
"""

from __future__ import annotations

import pytest

from butler.registry.skill_service import SkillRegistryService


@pytest.mark.unit
class TestProdFailClosed:
    """BUTLER_ENV=prod 时 BUTLER_REGISTRY_AUTO_INSTALL=1 必须被忽略."""

    def test_prod_env_ignores_auto_install_env(self, monkeypatch):
        """BUTLER_ENV=prod + BUTLER_REGISTRY_AUTO_INSTALL=1 → 仍需 confirmation."""
        monkeypatch.setenv("BUTLER_ENV", "prod")
        monkeypatch.setenv("BUTLER_REGISTRY_AUTO_INSTALL", "1")

        svc = SkillRegistryService(tenant_id="default")
        assert svc.needs_install_confirmation(trust="community") is True, (
            "prod 环境 BUTLER_REGISTRY_AUTO_INSTALL=1 应被忽略, community 必须确认"
        )

    def test_prod_env_ignores_other_truthy_values(self, monkeypatch):
        """BUTLER_ENV=prod + BUTLER_REGISTRY_AUTO_INSTALL=true|yes|on → 仍需 confirmation."""
        monkeypatch.setenv("BUTLER_ENV", "prod")
        for truthy in ("true", "yes", "on", "TRUE", "Yes"):
            monkeypatch.setenv("BUTLER_REGISTRY_AUTO_INSTALL", truthy)
            svc = SkillRegistryService(tenant_id="default")
            assert svc.needs_install_confirmation(trust="community") is True, (
                f"prod 环境 BUTLER_REGISTRY_AUTO_INSTALL={truthy} 应被忽略"
            )

    def test_prod_env_builtin_trusted_still_skips(self, monkeypatch):
        """prod 环境 builtin / trusted 仍 skip (这些 trust 本来就免确认)."""
        monkeypatch.setenv("BUTLER_ENV", "prod")
        monkeypatch.delenv("BUTLER_REGISTRY_AUTO_INSTALL", raising=False)

        svc = SkillRegistryService(tenant_id="default")
        assert svc.needs_install_confirmation(trust="builtin") is False
        assert svc.needs_install_confirmation(trust="trusted") is False

    def test_prod_env_force_or_confirmed_still_skips(self, monkeypatch):
        """prod 环境 force / confirmed=True 仍 skip (显式信号)."""
        monkeypatch.setenv("BUTLER_ENV", "prod")
        monkeypatch.delenv("BUTLER_REGISTRY_AUTO_INSTALL", raising=False)

        svc = SkillRegistryService(tenant_id="default")
        assert svc.needs_install_confirmation(trust="community", force=True) is False
        assert svc.needs_install_confirmation(trust="community", confirmed=True) is False


@pytest.mark.unit
class TestDevEnvPreservesOptIn:
    """dev / test / 未设 env 时 BUTLER_REGISTRY_AUTO_INSTALL=1 仍 opt-in 生效."""

    def test_dev_env_auto_install_skips_confirmation(self, monkeypatch):
        """BUTLER_ENV=dev + BUTLER_REGISTRY_AUTO_INSTALL=1 → community 跳过 confirmation."""
        monkeypatch.setenv("BUTLER_ENV", "dev")
        monkeypatch.setenv("BUTLER_REGISTRY_AUTO_INSTALL", "1")

        svc = SkillRegistryService(tenant_id="default")
        assert svc.needs_install_confirmation(trust="community") is False, (
            "dev 环境 BUTLER_REGISTRY_AUTO_INSTALL=1 应正常 opt-in 跳过"
        )

    def test_unset_env_auto_install_skips_confirmation(self, monkeypatch):
        """BUTLER_ENV 未设 + BUTLER_REGISTRY_AUTO_INSTALL=1 → community 跳过 (向后兼容)."""
        monkeypatch.delenv("BUTLER_ENV", raising=False)
        monkeypatch.setenv("BUTLER_REGISTRY_AUTO_INSTALL", "1")

        svc = SkillRegistryService(tenant_id="default")
        assert svc.needs_install_confirmation(trust="community") is False

    def test_test_env_auto_install_skips_confirmation(self, monkeypatch):
        """BUTLER_ENV=test + BUTLER_REGISTRY_AUTO_INSTALL=1 → community 跳过 (CI 一致性)."""
        monkeypatch.setenv("BUTLER_ENV", "test")
        monkeypatch.setenv("BUTLER_REGISTRY_AUTO_INSTALL", "1")

        svc = SkillRegistryService(tenant_id="default")
        assert svc.needs_install_confirmation(trust="community") is False


@pytest.mark.unit
class TestStaticContract:
    """静态契约: needs_install_confirmation 必须含 prod fail-closed 检查."""

    def test_prod_check_present(self):
        """skill_service.py 的 needs_install_confirmation 必须检查 BUTLER_ENV=prod."""
        import inspect
        from butler.registry import skill_service

        src = inspect.getsource(skill_service.SkillRegistryService.needs_install_confirmation)
        assert "BUTLER_ENV" in src, (
            "needs_install_confirmation 必须含 BUTLER_ENV 检查 (prod fail-closed)"
        )
        assert "prod" in src, "needs_install_confirmation 必须显式拦截 prod"
