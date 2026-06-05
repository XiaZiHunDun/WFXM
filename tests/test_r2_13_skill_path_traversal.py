"""R2-13 [H] skill_path_traversal_log_continue — 越界 content_path 应当 ERROR + 记入 buffer.

`butler/skills/manager.py:311-319` (`_load_skill_from_path`):

    rel = str(fm.get("content_path") or "").strip()
    if rel:
        root = self._skills_root_for(path, source)
        content_path = (root / rel).resolve()
        try:
            content_path.relative_to(root.resolve())
        except ValueError:
            logger.warning("Skill content_path escapes skills root: %s", rel)
            return sk  # ← 静默返回 sk, 无 exc_info, 不记 diagnostics

问题:
1) WARNING 级别 (无 exc_info) — 安全事件被降级, traceback 丢
2) 静默 return sk — 越界 content_path 失败被吞, 排障极难
3) 不进 recent_skill_load_errors — /诊断看不到
4) 行为仍 "skill 可加载但无 inner content", 这部分可保留

修复: 引入 SKILL_LOAD_ERR_PATH_TRAVERSAL error code, 越界时:
- log at ERROR with exc_info (保留 traceback)
- 记入 recent_skill_load_errors (R2-8 已有的 buffer)
- 保留现有行为: 仍 return sk (skill 仍可用, 只是 inner content 缺失)

行为保证:
1) content_path 越界 (e.g. ../../../etc/passwd) → recent_skill_load_errors
   有 code=path_traversal_attempt entry
2) log at ERROR with exc_info
3) 合法 content_path (skills root 内) → 不污染 buffer
4) Skill 仍可加载 (return sk), 行为不变
5) 越界 rel 路径写入 error message (operator 可见)
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from butler.skills.manager import (
    SKILL_LOAD_ERR_PATH_TRAVERSAL,
    SkillManager,
    _clear_recent_skill_load_errors,
    recent_skill_load_errors,
)


@pytest.fixture(autouse=True)
def _reset_load_errors():
    """Reset the recent skill load errors buffer between tests."""
    _clear_recent_skill_load_errors()
    yield
    _clear_recent_skill_load_errors()


# -----------------------------------------------------------------------
# Test 1: path traversal attempt is recorded
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestPathTraversalRecorded:
    """content_path 越界时, 失败记入 recent_skill_load_errors."""

    def test_traversal_recorded_in_recent_errors(self, tmp_path: Path):
        """content_path 指向 skills root 之外 → code=path_traversal_attempt."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        # content_path 越界: 从 skills_dir 出发, 回到 tmp_path (即 skills root 之外)
        evil = skills_dir / "evil-skill.md"
        evil.write_text(
            "---\n"
            "name: evil-skill\n"
            "install_type: directory\n"
            "content_path: ../outside.md\n"
            "---\n",
            encoding="utf-8",
        )

        mgr = SkillManager(skills_dir=str(skills_dir))
        # 触发 load (content_path 解析发生在 _load_skill_from_path 内部)
        sk = mgr.get_skill("evil-skill")

        errors = recent_skill_load_errors()
        assert any(
            e.code == SKILL_LOAD_ERR_PATH_TRAVERSAL for e in errors
        ), (
            f"path traversal 必须记入 recent_skill_load_errors, 实际: {errors!r}"
        )
        # skill 仍可加载 (不阻塞用户), 但 inner content 缺失
        assert sk is not None, "skill 应仍可加载 (越界 content_path 不应阻塞)"
        assert "_content_path" not in sk, (
            "越界 content_path 不应被采纳, _content_path 字段不应出现"
        )

    def test_error_entry_contains_path(self, tmp_path: Path):
        """错误 entry 必须含 path + message 字段, 供 /诊断 透明."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        evil = skills_dir / "evil-skill.md"
        evil.write_text(
            "---\n"
            "name: evil-skill\n"
            "install_type: directory\n"
            "content_path: ../outside.md\n"
            "---\n",
            encoding="utf-8",
        )

        mgr = SkillManager(skills_dir=str(skills_dir))
        mgr.get_skill("evil-skill")

        errors = recent_skill_load_errors()
        traversal_errors = [
            e for e in errors if e.code == SKILL_LOAD_ERR_PATH_TRAVERSAL
        ]
        assert len(traversal_errors) == 1
        err = traversal_errors[0]
        assert err.path == evil, f"error path 应指向 skill 文件, 实际: {err.path}"
        assert err.message, "error message 必须非空"
        assert "evil-skill" in str(err.path) or "outside" in err.message, (
            f"message 应提及越界 content_path, 实际: {err.message!r}"
        )


# -----------------------------------------------------------------------
# Test 2: log at ERROR with exc_info
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestErrorLogHasExcInfo:
    """越界事件必须 log at ERROR, 保留 traceback."""

    def test_traversal_logs_error_with_exc_info(
        self, tmp_path: Path, caplog
    ):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        evil = skills_dir / "evil-skill.md"
        evil.write_text(
            "---\n"
            "name: evil-skill\n"
            "install_type: directory\n"
            "content_path: ../outside.md\n"
            "---\n",
            encoding="utf-8",
        )

        mgr = SkillManager(skills_dir=str(skills_dir))
        with caplog.at_level(logging.DEBUG, logger="butler.skills.manager"):
            mgr.get_skill("evil-skill")

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        traversal_records = [
            r for r in error_records if "path" in r.message.lower() or "escapes" in r.message.lower()
        ]
        assert traversal_records, (
            f"path traversal 必须 log at ERROR, "
            f"实际 records: {[(r.levelname, r.message) for r in caplog.records]}"
        )
        assert any(r.exc_info is not None for r in traversal_records), (
            "ERROR log 必须含 exc_info (保留 traceback)"
        )


# -----------------------------------------------------------------------
# Test 3: legitimate content_path does NOT pollute the buffer
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestLegitimatePathClean:
    """合法 content_path (skills root 内) → 不污染 diagnostics buffer."""

    def test_legitimate_content_path_no_traversal_error(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        content_dir = skills_dir / "good-skill_dir"
        content_dir.mkdir()
        # inner content 必须也有 frontmatter (_parse_skill_md 要求)
        (content_dir / "main.md").write_text(
            "---\nname: good-skill\n---\nbody content here\n",
            encoding="utf-8",
        )
        stub = skills_dir / "good-skill.md"
        stub.write_text(
            "---\n"
            "name: good-skill\n"
            "install_type: directory\n"
            "content_path: good-skill_dir/main.md\n"
            "---\n",
            encoding="utf-8",
        )

        mgr = SkillManager(skills_dir=str(skills_dir))
        sk = mgr.get_skill("good-skill")

        # 合法路径: 不应记入 path_traversal
        traversal_errors = [
            e for e in recent_skill_load_errors()
            if e.code == SKILL_LOAD_ERR_PATH_TRAVERSAL
        ]
        assert traversal_errors == [], (
            f"合法 content_path 不应记入 path_traversal, 实际: {traversal_errors!r}"
        )
        # 行为: skill 加载, 带 inner content
        assert sk is not None
        assert "body content here" in sk.get("content", ""), (
            f"合法 content_path 应注入 inner content, 实际: {sk.get('content')!r}"
        )


# -----------------------------------------------------------------------
# Test 4: error code constant is exposed
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestErrorCodeExposed:
    """SKILL_LOAD_ERR_PATH_TRAVERSAL 常量必须导出 (供 /诊断 聚合)."""

    def test_constant_is_non_empty_string(self):
        assert isinstance(SKILL_LOAD_ERR_PATH_TRAVERSAL, str)
        assert SKILL_LOAD_ERR_PATH_TRAVERSAL, "constant 必须非空"
        # 应为稳定 identifier (lowercase snake)
        assert SKILL_LOAD_ERR_PATH_TRAVERSAL.replace("_", "").isalnum(), (
            f"code 应是 lowercase snake, 实际: {SKILL_LOAD_ERR_PATH_TRAVERSAL!r}"
        )
