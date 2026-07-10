"""Sprint 21-2 TEST-21-C-2: `SkillLockFile.record_install` 并发竞争 (HIGH).

`butler/registry/skill_lock.py:71-84` `record_install` 走
`_load()` → `data["skills"][name] = ...` → `_save(data)` 三步,
无任何锁. 多线程并发调用会出现 data-loss / torn-write:

场景 A (不同 skill, 跨 thread):
- T1: `_load()` → 缓存返回 data1 (引用同一 dict)
- T2: `_load()` → data2 (与 data1 同一 ref)
- T1: `data1["skills"]["foo"] = ...`  → 共享 dict 已有 foo
- T2: `data2["skills"]["bar"] = ...`  → 共享 dict 已有 foo + bar
- T1: `_save(data1)` → file = foo + bar
- T2: `_save(data2)` → file = foo + bar (同内容)

场景 A 在 cached-dict 共享下看似安全, 但场景 B 暴露真正问题:

场景 B (cache 失效 / 跨 process / `_save` 在 T1/T2 之间):
- T1: `_load()` → data1
- T1: `data1["skills"]["foo"] = ...`
- T1: `_save(data1)` → file mtime 改变, 缓存自动失效
- T2: `_load()` → 缓存 miss, 重读 file → data2 (含 T1 的 foo)
- T2: `data2["skills"]["bar"] = ...`  → data2 = foo + bar
- T2: `_save(data2)` → file = foo + bar ✓

场景 B 也安全. 真正 race 在场景 C — 并发 `_save` 的 OS-level interleaving:

场景 C (T1/T2 同时进入临界区, dict 引用不同):
- T1: `_load()` → data1
- T2: `_load()` → data2 = deepcopy(data1) (例如 cache eviction
  导致 _file_cache.popitem, 或 OS 重启后 process 隔离)
- T1: `data1["skills"]["foo"] = ...`
- T2: `data2["skills"]["bar"] = ...`
- T1: `_save(data1)` → file = foo (bar 丢失!)
- T2: `_save(data2)` → file = bar (foo 丢失!)

修复: 加 `threading.Lock` 串行化 `record_install` (Sprint 21-2).
同进程下所有 SkillLockFile 实例共享一把 lock (per-path 锁,
用 `_LOCKS` dict + str(path) 索引), 跨 process 由 OS-level 文件锁
或 `tempfile` + `os.replace` atomic 写保护, 此 fix 至少消除
同进程 race.
"""

from __future__ import annotations

import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from butler.registry.skill_lock import SkillLockFile
from butler.registry.skill_types import InstalledSkillRecord
from butler.tools._file_cache import clear_cache


def _make_record(name: str) -> InstalledSkillRecord:
    return InstalledSkillRecord(
        name=name,
        source="hub",
        identifier=f"{name}@1.0.0",
        version="1.0.0",
        installed_at="2026-06-04T00:00:00Z",
        content_hash="abc",
        install_path=f"/path/{name}.md",
        scan_verdict="ok",
        trust="community",
    )


@pytest.mark.unit
class TestStaticContract:
    """`SkillLockFile` 必须有 lock 保护 record_install (Sprint 21-2)."""

    def test_record_install_uses_threading_lock(self, tmp_path: Path):
        """`record_install` 实现必须使用 `threading.Lock` 串行化写.

        检查方式: 构造 20 次并发 record_install 调用, mock
        `read_json_cached` 强制每次读盘 (跳过 mtime 缓存), 验证最终
        lock file 包含所有 skill. 若无锁, 会偶发失败 (T2 的 _load
        读到 T1 写入前的文件, T2 的 _save 覆盖 T1 的变更).

        为什么 mock `read_json_cached` 而不是 `_load`?
        `read_json_cached` 按 (path, mtime_ns) 缓存, 同一文件多次
        write_text 在某些文件系统上 mtime 不变, 缓存命中返陈旧 dict.
        这正是 race 的真实场景: 两个线程都从 cache 拿到同一个 dict ref,
        各设自己的 skill, 最后 _save 互相覆盖. 直接 mock 缓存层
        能稳定复现.
        """
        clear_cache()
        lock = tmp_path / "lock.json"
        lock.write_text(
            json.dumps({"version": 1, "skills": {}}),
            encoding="utf-8",
        )
        slf = SkillLockFile(path=lock)

        # Force read_json_cached to always read fresh from file (bypass
        # mtime cache). This simulates the scenario where two threads
        # each get a fresh dict from disk and mutate independently.
        def always_fresh(path):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None

        names = [f"skill-{i}" for i in range(20)]
        barrier = threading.Barrier(len(names))

        def install(name: str) -> None:
            barrier.wait()
            slf.record_install(_make_record(name))

        with patch(
            "butler.registry.skill_lock.read_json_cached",
            side_effect=always_fresh,
        ):
            with ThreadPoolExecutor(max_workers=len(names)) as ex:
                futures = [ex.submit(install, n) for n in names]
                for f in futures:
                    f.result()

        data = json.loads(lock.read_text(encoding="utf-8"))
        skills = data.get("skills") or {}
        missing = [n for n in names if n not in skills]
        assert not missing, (
            f"并发 record_install 后, 这些 skill 丢失: {missing}. "
            f"实际 skills={sorted(skills.keys())}. "
            f"原因: record_install 无锁, _save() 互相覆盖 (Sprint 21-2). "
            f"修复: 加 threading.Lock."
        )


@pytest.mark.unit
class TestRecordInstallBehavior:
    """行为验证: 串行 record_install 无回归."""

    def test_single_thread_record_install_works(self, tmp_path: Path):
        """单线程 record_install → skill 可被 get() 读到 (无锁路径)."""
        clear_cache()
        lock = tmp_path / "lock.json"
        lock.write_text(
            json.dumps({"version": 1, "skills": {}}),
            encoding="utf-8",
        )
        slf = SkillLockFile(path=lock)

        slf.record_install(_make_record("foo"))
        slf.record_install(_make_record("bar"))

        clear_cache()
        assert slf.get("foo") is not None
        assert slf.get("bar") is not None
        assert slf.get("foo").source == "hub"

    def test_remove_then_record_install_round_trip(self, tmp_path: Path):
        """remove → record_install 同一 skill → 新记录可被 get() 读到."""
        clear_cache()
        lock = tmp_path / "lock.json"
        lock.write_text(
            json.dumps({
                "version": 1,
                "skills": {
                    "foo": {
                        "name": "foo",
                        "source": "hub",
                        "identifier": "foo@1.0.0",
                        "version": "1.0.0",
                        "installed_at": "2026-06-04T00:00:00Z",
                        "content_hash": "abc",
                        "install_path": "/path/foo.md",
                        "scan_verdict": "ok",
                        "trust": "community",
                    }
                },
            }),
            encoding="utf-8",
        )
        slf = SkillLockFile(path=lock)

        assert slf.remove("foo") is True
        slf.record_install(_make_record("foo"))
        clear_cache()
        loaded = slf.get("foo")
        assert loaded is not None


@pytest.mark.unit
class TestEdgeCases:
    """边界情况: 同 skill 多次并发 install."""

    def test_concurrent_same_skill_install_consistent(self, tmp_path: Path):
        """10 线程同时 install 同一 skill → 最终 lock file 一致 (任一线程的 record)."""
        clear_cache()
        lock = tmp_path / "lock.json"
        lock.write_text(
            json.dumps({"version": 1, "skills": {}}),
            encoding="utf-8",
        )
        slf = SkillLockFile(path=lock)

        original_load = slf._load

        def deep_copy_load():
            return copy.deepcopy(original_load())

        n_threads = 10
        barrier = threading.Barrier(n_threads)

        def install(_idx: int) -> None:
            barrier.wait()
            slf.record_install(_make_record("shared-skill"))

        def always_fresh(path):
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None

        with patch(
            "butler.registry.skill_lock.read_json_cached",
            side_effect=always_fresh,
        ):
            with ThreadPoolExecutor(max_workers=n_threads) as ex:
                futures = [ex.submit(install, i) for i in range(n_threads)]
                for f in futures:
                    f.result()

        clear_cache()
        data = json.loads(lock.read_text(encoding="utf-8"))
        skills = data.get("skills") or {}
        # shared-skill 必须在, 且字段一致 (任一 record 写入都是合法结果)
        assert "shared-skill" in skills, (
            f"共享 skill 必须在 lock file, 实际 skills={sorted(skills.keys())}"
        )
        record = skills["shared-skill"]
        # stored dict 的字段是 source/identifier/version/... (name 是外层 key)
        assert record["source"] == "hub"
        assert record["identifier"] == "shared-skill@1.0.0"
        assert record["version"] == "1.0.0"
        # 通过 get() 拿 InstalledSkillRecord, 验证 name 也能正确还原
        slf2 = SkillLockFile(path=lock)
        loaded = slf2.get("shared-skill")
        assert loaded is not None
        assert loaded.name == "shared-skill"
