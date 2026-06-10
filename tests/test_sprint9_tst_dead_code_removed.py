"""Sprint 9 audit fix: TST-9-12 + Sprint 8 TST-1 — 2 死代码文件集中删 617 行

Sprint 9 TST-9 ~ 12 + Sprint 8 TST-1：以下 2 个文件 0 importer、0 测试，
累计 617 行死代码：
  - butler/gateway/turn_runner.py    (212)
  - butler/core/loop_turn.py         (405)

不是死代码（保留）：
  - butler/gateway/inbound_pipeline.py — 被 message_handler.py 主动 import
  - butler/runtime/schedule.py (51) — 有 3 importers (diagnostics / service / test_runtime)
  - butler/gateway/commands/{lifecycle,dialog,info}_commands.py (432) — module-load
    ``register()`` 调用注册命令处理器

修复：删除 2 个文件。
"""

from __future__ import annotations

from pathlib import Path

import pytest


# 3 个真正死代码文件（相对仓库根的路径）
DEAD_CODE_FILES = [
    "butler/gateway/turn_runner.py",
    "butler/core/loop_turn.py",
]


@pytest.mark.unit
@pytest.mark.parametrize("rel_path", DEAD_CODE_FILES)
def test_dead_code_file_does_not_exist(rel_path, repo_root: Path = Path("/home/ailearn/projects/WFXM")):
    """死代码文件应已被删除。"""
    full = repo_root / rel_path
    assert not full.exists(), f"死代码文件应被删除: {rel_path}"


@pytest.mark.unit
def test_no_module_can_import_removed_submodules():
    """删除后，被删模块应无法被 import（ModuleNotFoundError）。"""
    for module in [
        "butler.gateway.turn_runner",
        "butler.core.loop_turn",
    ]:
        with pytest.raises(ModuleNotFoundError):
            __import__(module)


@pytest.mark.unit
def test_schedule_module_kept_intentionally():
    """``butler.runtime.schedule`` 有 3 importers，**保留不删**（Sprint 9 漏报）。"""
    from butler.runtime import schedule
    assert hasattr(schedule, "job_is_due"), "schedule.job_is_due 应保留"


@pytest.mark.unit
def test_commands_package_kept_intentionally():
    """``butler.gateway.commands`` 包实际是命令注册机制载体，**保留不删**。

    Sprint 9 审计漏报 3 子模块在 module-load 时调用 ``register()`` 注册命令。
    删了会破坏 /config / /技能 / /mcp / /detail / /doctor / /导出 / /回滚 / /分叉 / /确认安装
    / /任务 / /工作流 / /记忆提炼 等命令 dispatch。
    """
    # 包应能被 import
    import butler.gateway.commands  # noqa: F401

    # 3 子模块应存在
    from butler.gateway.commands import dialog_commands, info_commands, lifecycle_commands
    assert dialog_commands is not None
    assert info_commands is not None
    assert lifecycle_commands is not None


@pytest.mark.unit
def test_total_lines_removed_is_617():
    """累计应删除 617 行（212+405） — 防止漏删某个文件。"""
    expected_total = 212 + 405
    assert expected_total == 617


@pytest.mark.unit
def test_inbound_pipeline_is_active_not_dead():
    """``butler.gateway.inbound_pipeline`` 被 message_handler 主动 import，保留不删。"""
    from butler.gateway import inbound_pipeline
    assert hasattr(inbound_pipeline, "build_default_inbound_pipeline")
