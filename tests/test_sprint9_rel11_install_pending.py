"""Sprint 9 audit fix: REL-11 — install_pending get_pending 副作用 + _save_all atomic

Sprint 9 REL-11: butler/registry/install_pending.py:89-99 + 120
get_pending 是"读"路径却 _save_all 写盘清理过期项（line 95-99）；
save_pending 走 _save_all 裸 write_text（line 120），并发 save 互相
覆盖。修复：
  - get_pending 改名 _read_only；只读
  - _save_all 改 atomic_write_text
  - save_pending / clear_pending 持 flock(LOCK_EX) 串行化
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from butler.registry import install_pending as ip


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setattr(ip, "get_butler_home", lambda: tmp_path / "home")
    yield


def _write_row(
    identifier: str = "id1",
    session_key: str = "wechat:u1:p1",
    platform: str = "wechat",
    external_id: str = "u1",
    age_seconds: float = 0,
) -> ip.PendingSkillInstall:
    return ip.PendingSkillInstall(
        identifier=identifier,
        name="TestSkill",
        description="desc",
        source="registry",
        trust="community",
        session_key=session_key,
        platform=platform,
        external_id=external_id,
        requested_at=time.time() - age_seconds,
    )


@pytest.mark.unit
def test_get_pending_does_not_modify_file(tmp_path):
    """get_pending 是"读"路径，不应触发 _save_all 写盘清理。"""
    row = _write_row()
    ip.save_pending(row)

    pending_path = ip._pending_path()
    mtime_before = pending_path.stat().st_mtime

    # 多次调 get_pending，文件 mtime 不应变
    time.sleep(0.05)
    for _ in range(3):
        got = ip.get_pending(
            session_key="wechat:u1:p1", platform="wechat", external_id="u1"
        )
        assert got is not None
        assert got.identifier == "id1"

    mtime_after = pending_path.stat().st_mtime
    assert mtime_before == mtime_after, (
        f"get_pending 不应写盘：mtime {mtime_before} → {mtime_after}"
    )


@pytest.mark.unit
def test_save_pending_uses_atomic_write(tmp_path):
    """save_pending 写盘后无 .tmp 残留。"""
    row = _write_row()
    ip.save_pending(row)

    pending_path = ip._pending_path()
    assert pending_path.is_file()
    # atomic_write_text 不应留 .tmp 残留
    tmp_residue = pending_path.with_suffix(pending_path.suffix + ".tmp")
    assert not tmp_residue.exists(), (
        f"save_pending 不应留 .tmp 残留：{tmp_residue}"
    )


@pytest.mark.unit
def test_save_pending_purges_expired_on_write(tmp_path):
    """save_pending 写盘时仍应清理过期项（保留原行为）。"""
    # 写一个 2h 前的过期项
    expired = _write_row(identifier="expired", age_seconds=7300)
    ip.save_pending(expired)
    pending_path = ip._pending_path()

    # 写入新 row，save 路径会 purge 过期
    new = _write_row(identifier="fresh")
    ip.save_pending(new)

    data = json.loads(pending_path.read_text(encoding="utf-8"))
    entries = data.get("entries") or {}
    assert "expired" not in str(entries)
    # 仍然能读到新 row
    got = ip.get_pending(
        session_key="wechat:u1:p1", platform="wechat", external_id="u1"
    )
    assert got is not None
    assert got.identifier == "fresh"


@pytest.mark.unit
def test_clear_pending_uses_atomic_write(tmp_path):
    """clear_pending 也走 atomic_write。"""
    row = _write_row()
    ip.save_pending(row)
    pending_path = ip._pending_path()
    assert pending_path.is_file()

    ip.clear_pending(
        session_key="wechat:u1:p1", platform="wechat", external_id="u1"
    )

    assert pending_path.is_file()
    tmp_residue = pending_path.with_suffix(pending_path.suffix + ".tmp")
    assert not tmp_residue.exists(), "clear_pending 不应留 .tmp 残留"

    # 数据已清
    data = json.loads(pending_path.read_text(encoding="utf-8"))
    assert data.get("entries") == {}


@pytest.mark.unit
def test_clear_pending_purges_expired_too(tmp_path):
    """clear_pending 写盘时也应清理过期项。"""
    expired = _write_row(identifier="old", age_seconds=7300)
    ip.save_pending(expired)
    ip.clear_pending(
        session_key="wechat:u1:p1", platform="wechat", external_id="u1"
    )

    data = json.loads(ip._pending_path().read_text(encoding="utf-8"))
    assert data.get("entries") == {}


@pytest.mark.unit
def test_save_pending_rejects_symlink_target(tmp_path):
    """save_pending 写盘时若目标路径被替换为 symlink 应被拒。"""
    # 先建一个普通 row 让文件存在
    row = _write_row()
    ip.save_pending(row)
    pending_path = ip._pending_path()

    # 删掉原文件，做一个 symlink 指向外部
    pending_path.unlink()
    external = tmp_path / "external.json"
    external.write_text("leaked", encoding="utf-8")
    pending_path.symlink_to(external)

    # 再调 save_pending — 走 atomic_write_text → 应拒
    with pytest.raises(OSError, match="symlink"):
        ip.save_pending(_write_row(identifier="new"))

    # external 不应被写
    assert external.read_text(encoding="utf-8") == "leaked"


@pytest.mark.integration
def test_concurrent_save_pending_does_not_overwrite(tmp_path):
    """并发 save_pending 不应互相覆盖（写者 LOCK_EX 串行化）。

    用 3 个不同 external_id 制造 3 个独立 entry_key；如果 LOCK_EX 没
    工作，3 个进程读到的 entries 是初始空 []，各自写回只 1 个 row。
    LOCK_EX 串行化后：进程 A 写 [u1]，进程 B 读 [u1] 写 [u1, u2]，
    进程 C 读 [u1, u2] 写 [u1, u2, u3]。
    """
    import subprocess
    import sys
    import textwrap

    butler_home = tmp_path / "home"
    butler_home.mkdir(parents=True, exist_ok=True)

    script = textwrap.dedent(
        f"""
        import json, os, sys, time
        os.environ['BUTLER_HOME'] = {str(butler_home)!r}
        from butler.registry import install_pending as ip
        ident = sys.argv[1]
        ext = sys.argv[2]
        ip.save_pending(ip.PendingSkillInstall(
            identifier=ident, name=ident, description=ident, source='src',
            trust='community', session_key='wechat:ext:p1',
            platform='wechat', external_id=ext, requested_at=time.time(),
        ))
        time.sleep(0.1)
        """
    )

    procs = []
    for ident, ext in [("A", "u1"), ("B", "u2"), ("C", "u3")]:
        p = subprocess.Popen(
            [sys.executable, "-c", script, ident, ext],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        procs.append(p)
    for p in procs:
        out, err = p.communicate(timeout=10)
        assert p.returncode == 0, f"子进程失败: {p.returncode} stderr={err.decode()}"

    data = json.loads(ip._pending_path().read_text(encoding="utf-8"))
    idents = [row.get("identifier") for row in (data.get("entries") or {}).values()]
    for ident in ("A", "B", "C"):
        assert ident in idents, (
            f"concurrent save 应保留全部 row，缺 {ident}：实际 {idents}"
        )


@pytest.mark.unit
def test_get_pending_returns_none_for_nonexistent(tmp_path):
    """不存在的 session_key / external_id 返回 None，不写盘。"""
    pending_path = ip._pending_path()
    assert not pending_path.is_file()

    got = ip.get_pending(
        session_key="wechat:nobody:p1", platform="wechat", external_id="nobody"
    )
    assert got is None
    # 不存在的 session_key 时不应创建文件
    assert not pending_path.is_file(), (
        "get_pending 在 entries 为空时不应创建文件"
    )
