"""Sprint 22-8 QUAL-21-D-3: `__import__("shutil")` 反模式 in SkillRegistryService.install.

`butler/registry/skill_service.py:252` 在 `install()` 方法内
硬塞 `shutil_rmtree = __import__("shutil").rmtree` — 这是
"inline dynamic import" 反模式, 几个问题:
1. **可读性差**: 1 行同时做 import + attribute access,
   阅读者要先反推 "哦这是拿 shutil.rmtree"
2. **import 路径解析开销**: `__import__` 每次调用都走
   sys.modules 查找 + 可能触发 PEP 451 finder. 静态
   `import shutil` 在 module load 时一次性完成
3. **linter/类型检查盲区**: 静态 import 让 mypy/pyright
   知道 `shutil` 的类型, `__import__("shutil")` 返
   `Any`, `Any.rmtree` 也是 `Any` — IDE 失去所有帮助
4. **与代码库风格不一致**: 同文件 line 247 已经用
   `import logging` (经典静态 import), 同一函数内
   风格分裂

修复: 顶部 `import shutil`, 函数体直接 `shutil.rmtree(...)`.

行为保证 (本测试):
1) 模块顶部有 `import shutil` (结构性)
2) `install()` 方法源码不含 `__import__("shutil")` (结构性)
3) **block 路径行为保留**: scan_quarantine 返 verdict="block"
   → 调用 `shutil.rmtree(qpath, ignore_errors=True)` 清掉
   quarantine 目录 + 抛 `ValueError("Install blocked: ...")`
4) **clean install 路径行为保留**: verdict 非 block → 走到
   `install_from_quarantine` 成功路径
"""

from __future__ import annotations

import importlib
import inspect
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------- helpers ----------

def _reload_skill_service():
    """Reload skill_service module to pick up import-level changes."""
    from butler.registry import skill_service
    importlib.reload(skill_service)
    return skill_service


# ---------- structural tests ----------

@pytest.mark.unit
class TestShutilStaticImport:
    """模块顶部 `import shutil` (反 `__import__` 反模式)."""

    def test_module_imports_shutil_at_top_level(self):
        """skill_service.py 顶部有静态 `import shutil`."""
        from butler.registry import skill_service
        src = inspect.getsource(skill_service)
        # 检查模块顶部区域 (前 30 行, 不含方法体)
        top = "\n".join(src.splitlines()[:30])
        assert "import shutil" in top, (
            f"skill_service.py 顶部应 import shutil (静态), "
            f"顶部 30 行:\n{top}"
        )

    def test_install_method_does_not_use_dunder_import(self):
        """`install()` 方法源码不含 `__import__` (反模式)."""
        from butler.registry import skill_service
        method_src = inspect.getsource(skill_service.SkillRegistryService.install)
        assert "__import__" not in method_src, (
            f"install() 不应再用 __import__ 反模式, "
            f"源码:\n{method_src}"
        )

    def test_shutil_attribute_accessible_at_module_level(self):
        """`shutil` 在 module namespace 中可访问 (说明顶部 import 生效)."""
        from butler.registry import skill_service
        assert hasattr(skill_service, "shutil"), (
            "skill_service module 缺 shutil 属性 — 顶部 import 未生效"
        )
        # 与 stdlib 一致
        import shutil as stdlib_shutil
        assert skill_service.shutil is stdlib_shutil


# ---------- behavioral tests ----------

@pytest.mark.unit
class TestInstallBlockPathRemovesQuarantine:
    """block 路径: 调 shutil.rmtree + 抛 ValueError."""

    def test_block_verdict_invokes_shutil_rmtree(self, tmp_path, monkeypatch):
        """verdict='block' → shutil.rmtree(qpath, ignore_errors=True) 被调."""
        from butler.registry import skill_service

        rm_called: dict[str, object] = {"path": None, "kwargs": None}
        real_rmtree = shutil.rmtree

        def spy_rmtree(path, *args, **kwargs):
            rm_called["path"] = path
            rm_called["kwargs"] = (args, kwargs)
            return real_rmtree(path, *args, **kwargs)

        # mock 整条依赖链, 让 install 走到 block 路径
        fake_qpath = tmp_path / "fake_quarantine"
        fake_qpath.mkdir()
        # 创建内部文件确认被删
        (fake_qpath / "evil.txt").write_text("x", encoding="utf-8")

        svc = skill_service.SkillRegistryService(tenant_id="t1")
        # 准备一个 fake hit + fake bundle
        from butler.registry.skill_types import (
            InstalledSkillRecord,
            SkillBundle,
            SkillSearchHit,
        )

        fake_hit = SkillSearchHit(
            name="evil",
            description="d",
            source="github",
            identifier="github:evil",
            trust="community",
        )
        fake_bundle = SkillBundle(
            name="evil",
            source="github",
            identifier="github:evil",
            files={"SKILL.md": "---\nname: evil\n---\nbody\n"},
            metadata={},
        )

        # mock 自检 inspection / fetch
        monkeypatch.setattr(svc, "inspect", lambda ident: fake_hit)
        monkeypatch.setattr(svc, "fetch_bundle", lambda ident: fake_bundle)
        # needs_install_confirmation 走默认路径 (community + not forced)
        # pre-scan 跳过 (无法 import install_scan 时已有 try/except)
        monkeypatch.setattr(svc, "needs_install_confirmation", lambda **kw: False)
        # 关键: quarantine 路径 + scan 返 block
        monkeypatch.setattr(
            skill_service, "quarantine_bundle",
            lambda bundle, tenant_id="": fake_qpath,
        )
        monkeypatch.setattr(
            skill_service, "scan_quarantine",
            lambda qpath: ("block", ["evil_pattern detected"]),
        )
        # patch shutil.rmtree (在 skill_service module namespace)
        with patch.object(skill_service.shutil, "rmtree", spy_rmtree):
            with pytest.raises(ValueError, match="Install blocked"):
                svc.install("github:evil", confirmed=True)

        # 验证 rmtree 被调
        assert rm_called["path"] == fake_qpath, (
            f"shutil.rmtree 应被调用且 path == fake_qpath, "
            f"实际 path: {rm_called['path']!r}"
        )
        args, kwargs = rm_called["kwargs"]
        assert kwargs.get("ignore_errors") is True, (
            f"shutil.rmtree 应传 ignore_errors=True, 实际 kwargs: {kwargs}"
        )
        # quarantine 目录已被清掉
        assert not fake_qpath.exists(), (
            f"block 路径应清掉 quarantine 目录, 实际仍存在: {fake_qpath}"
        )

    def test_block_verdict_error_message_includes_issues(self, tmp_path, monkeypatch):
        """ValueError 信息含 scan issues (用户能定位)."""
        from butler.registry import skill_service
        from butler.registry.skill_types import SkillBundle, SkillSearchHit

        fake_qpath = tmp_path / "fake_q"
        fake_qpath.mkdir()
        svc = skill_service.SkillRegistryService(tenant_id="t1")
        fake_hit = SkillSearchHit(
            name="x", description="", source="github",
            identifier="github:x", trust="community",
        )
        fake_bundle = SkillBundle(
            name="x", source="github", identifier="github:x",
            files={"SKILL.md": "---\nname: x\n---\nb\n"},
            metadata={},
        )
        monkeypatch.setattr(svc, "inspect", lambda ident: fake_hit)
        monkeypatch.setattr(svc, "fetch_bundle", lambda ident: fake_bundle)
        monkeypatch.setattr(svc, "needs_install_confirmation", lambda **kw: False)
        monkeypatch.setattr(
            skill_service, "quarantine_bundle",
            lambda bundle, tenant_id="": fake_qpath,
        )
        monkeypatch.setattr(
            skill_service, "scan_quarantine",
            lambda qpath: ("block", ["curl_pipe", "base64_decode"]),
        )
        monkeypatch.setattr(skill_service.shutil, "rmtree", lambda *a, **kw: None)

        with pytest.raises(ValueError) as exc_info:
            svc.install("github:x", confirmed=True)
        msg = str(exc_info.value)
        assert "Install blocked" in msg
        assert "curl_pipe" in msg
        assert "base64_decode" in msg
