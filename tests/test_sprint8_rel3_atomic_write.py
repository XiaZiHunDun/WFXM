"""Sprint 8 audit fix: REL-3 — atomic_json_write 假原子

Sprint 8 REL-3：`butler/gateway/platforms/helpers.py:11-15`
atomic_json_write 裸 write_text + replace，缺：
  1. fsync — 进程崩溃后可能丢数据
  2. O_NOFOLLOW / symlink 检查 — 写到 symlink 目标等于绕过路径守门

修复：替换实现使用 butler.io.atomic_write_text（升级含 fsync + symlink 拒绝）。
"""

from __future__ import annotations

import json

import pytest

from butler.gateway.platforms.helpers import atomic_json_write


@pytest.mark.unit
def test_atomic_json_write_creates_file(tmp_path):
    payload = {"a": 1, "b": "中文"}
    target = tmp_path / "data.json"

    atomic_json_write(target, payload)

    assert target.is_file()
    assert json.loads(target.read_text(encoding="utf-8")) == payload


@pytest.mark.unit
def test_atomic_json_write_overwrites_existing(tmp_path):
    target = tmp_path / "data.json"
    target.write_text(json.dumps({"old": True}), encoding="utf-8")

    atomic_json_write(target, {"new": True})

    assert json.loads(target.read_text(encoding="utf-8")) == {"new": True}


@pytest.mark.unit
def test_atomic_json_write_creates_parent_dirs(tmp_path):
    target = tmp_path / "deep" / "nested" / "data.json"

    atomic_json_write(target, {"deep": True})

    assert target.is_file()
    assert json.loads(target.read_text(encoding="utf-8")) == {"deep": True}


@pytest.mark.unit
def test_atomic_json_write_rejects_symlink_target(tmp_path):
    """REL-3：atomic_json_write 写入 symlink 目标应被拒绝 — 防路径守门绕过。"""
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    real_file = real_dir / "data.json"
    real_file.write_text(json.dumps({"real": True}), encoding="utf-8")

    link_path = tmp_path / "link.json"
    link_path.symlink_to(real_file)

    with pytest.raises((OSError, ValueError, RuntimeError)):
        atomic_json_write(link_path, {"injected": True})
