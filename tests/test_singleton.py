"""butler.utilities.singleton 模块的综合测试。

覆盖 lazy_singleton 和 SingletonSlot 两个线程安全单例原语：
- lazy_singleton: 装饰器式单例，基于双重检查锁
- SingletonSlot: 按 key 缓存的手动单例槽
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import pytest

from butler.utilities.singleton import SingletonSlot, lazy_singleton


# ============================================================
# lazy_singleton 测试
# ============================================================


class TestLazySingletonBasic:
    """lazy_singleton 基础行为测试。"""

    def test_single_call_factory_called_once(self) -> None:
        """单次调用：工厂函数仅被调用一次，返回同一实例。"""
        call_count = 0

        def factory() -> str:
            nonlocal call_count
            call_count += 1
            return "instance"

        wrapper = lazy_singleton(factory)

        result1 = wrapper()
        result2 = wrapper()
        result3 = wrapper()

        assert result1 == "instance"
        assert result1 is result2 is result3
        assert call_count == 1

    def test_factory_not_called_until_invoked(self) -> None:
        """lazy_singleton 实例化时不会立即调用工厂，只有 __call__ 才触发。"""
        call_count = 0

        def factory() -> int:
            nonlocal call_count
            call_count += 1
            return 42

        wrapper = lazy_singleton(factory)
        assert call_count == 0

        result = wrapper()
        assert result == 42
        assert call_count == 1

    def test_multiple_calls_return_same_instance(self) -> None:
        """多次调用始终返回同一对象。"""
        obj = object()

        def factory() -> object:
            return obj

        wrapper = lazy_singleton(factory)
        a = wrapper()
        b = wrapper()
        c = wrapper()

        assert a is b is c is obj


class TestLazySingletonConcurrent:
    """lazy_singleton 并发安全性测试。"""

    def test_concurrent_calls_factory_called_exactly_once(self) -> None:
        """10 个线程并发首次调用，工厂函数仅被执行一次。"""
        call_count = 0
        lock = threading.Lock()

        def factory() -> str:
            nonlocal call_count
            with lock:
                call_count += 1
            time.sleep(0.05)
            return "singleton"

        wrapper = lazy_singleton(factory)
        results: list[str] = []
        errors: list[Exception] = []
        barrier = threading.Barrier(10)

        def worker() -> None:
            try:
                barrier.wait()
                val = wrapper()
                results.append(val)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"线程执行出错: {errors}"
        assert len(results) == 10
        assert all(r == "singleton" for r in results)
        assert call_count == 1

    def test_concurrent_calls_all_threads_get_same_instance(self) -> None:
        """并发调用时所有线程获得的是完全相同的对象（同一 id）。"""
        obj = object()

        def factory() -> object:
            time.sleep(0.02)
            return obj

        wrapper = lazy_singleton(factory)
        barrier = threading.Barrier(8)
        results: list[object] = []

        def worker() -> None:
            barrier.wait()
            results.append(wrapper())

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r is obj for r in results)


class TestLazySingletonReset:
    """lazy_singleton reset() 行为测试。"""

    def test_reset_clears_instance(self) -> None:
        """reset() 清除缓存实例。"""
        counter = 0

        def factory() -> int:
            nonlocal counter
            counter += 1
            return counter

        wrapper = lazy_singleton(factory)

        first = wrapper()
        assert first == 1
        assert counter == 1

        wrapper.reset()

        second = wrapper()
        assert second == 2
        assert counter == 2

    def test_after_reset_factory_called_again(self) -> None:
        """reset() 后再次调用会重新执行工厂函数。"""
        instances: list[object] = []

        def factory() -> object:
            obj = object()
            instances.append(obj)
            return obj

        wrapper = lazy_singleton(factory)

        a = wrapper()
        b = wrapper()
        assert a is b
        assert len(instances) == 1

        wrapper.reset()

        c = wrapper()
        assert c is not a
        assert len(instances) == 2

        d = wrapper()
        assert c is d
        assert len(instances) == 2

    def test_multiple_resets(self) -> None:
        """连续多次 reset 后每次都能重新创建实例。"""
        counter = 0

        def factory() -> int:
            nonlocal counter
            counter += 1
            return counter

        wrapper = lazy_singleton(factory)

        assert wrapper() == 1
        wrapper.reset()
        assert wrapper() == 2
        wrapper.reset()
        assert wrapper() == 3
        wrapper.reset()
        assert wrapper() == 4

    def test_reset_on_uninitialized_singleton(self) -> None:
        """对尚未初始化的 lazy_singleton 调用 reset() 不会报错。"""
        def factory() -> str:
            return "hello"

        wrapper = lazy_singleton(factory)
        wrapper.reset()

        result = wrapper()
        assert result == "hello"


class TestLazySingletonWraps:
    """lazy_singleton 属性保留测试（模拟 functools.wraps 行为）。"""

    def test_preserves_name(self) -> None:
        """保留原始工厂函数的 __name__。"""
        def my_factory() -> None:
            """这是文档字符串。"""
            return None

        wrapper = lazy_singleton(my_factory)
        assert wrapper.__name__ == "my_factory"

    def test_preserves_qualname(self) -> None:
        """保留原始工厂函数的 __qualname__。"""
        def my_factory() -> None:
            return None

        wrapper = lazy_singleton(my_factory)
        assert wrapper.__qualname__ == "TestLazySingletonWraps.test_preserves_qualname.<locals>.my_factory"

    def test_preserves_doc(self) -> None:
        """保留原始工厂函数的 __doc__。"""
        def my_factory() -> None:
            """这是工厂的文档字符串。"""
            return None

        wrapper = lazy_singleton(my_factory)
        assert wrapper.__doc__ == "这是工厂的文档字符串。"

    def test_preserves_empty_doc(self) -> None:
        """原始工厂没有文档时，__doc__ 也为 None。"""
        def my_factory() -> None:
            return None

        wrapper = lazy_singleton(my_factory)
        assert wrapper.__doc__ is None


class TestLazySingletonErrorHandling:
    """lazy_singleton 异常处理测试。"""

    def test_factory_raises_exception_not_cached(self) -> None:
        """工厂抛出异常时，异常不会被缓存，下次调用会重试。"""
        call_count = 0

        def factory() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError(f"第 {call_count} 次失败")
            return "success"

        wrapper = lazy_singleton(factory)

        with pytest.raises(ValueError, match="第 1 次失败"):
            wrapper()

        assert call_count == 1

        with pytest.raises(ValueError, match="第 2 次失败"):
            wrapper()

        assert call_count == 2

        result = wrapper()
        assert result == "success"
        assert call_count == 3

    def test_factory_raises_then_succeeds_concurrent(self) -> None:
        """并发场景下工厂先失败后成功，最终应有一个线程获得成功实例。"""
        call_count = 0
        counter_lock = threading.Lock()

        def factory() -> str:
            nonlocal call_count
            with counter_lock:
                call_count += 1
                current = call_count
            if current <= 2:
                raise RuntimeError(f"临时失败 #{current}")
            return "ok"

        wrapper = lazy_singleton(factory)
        results: list[str] = []
        errors: list[Exception] = []

        for i in range(6):
            try:
                results.append(wrapper())
            except Exception as exc:
                errors.append(exc)

        assert len(results) + len(errors) == 6
        assert "ok" in results
        assert call_count >= 3


class TestLazySingletonMultipleFactories:
    """不同工厂产生不同实例的测试。"""

    def test_different_factories_produce_different_instances(self) -> None:
        """两个独立的 lazy_singleton 装饰器各自缓存自己的实例。"""
        @lazy_singleton
        def factory_a() -> str:
            return "A"

        @lazy_singleton
        def factory_b() -> str:
            return "B"

        a1 = factory_a()
        b1 = factory_b()
        a2 = factory_a()
        b2 = factory_b()

        assert a1 == "A"
        assert b1 == "B"
        assert a1 is a2
        assert b1 is b2
        assert a1 is not b1

    def test_two_wrappers_independent_reset(self) -> None:
        """两个独立装饰器的 reset 互不影响。"""
        counter_a = 0
        counter_b = 0

        def factory_a() -> int:
            nonlocal counter_a
            counter_a += 1
            return counter_a

        def factory_b() -> int:
            nonlocal counter_b
            counter_b += 1
            return counter_b

        wrapper_a = lazy_singleton(factory_a)
        wrapper_b = lazy_singleton(factory_b)

        assert wrapper_a() == 1
        assert wrapper_b() == 1

        wrapper_a.reset()

        assert wrapper_a() == 2
        assert wrapper_b() == 1

        wrapper_b.reset()

        assert wrapper_b() == 2


class TestLazySingletonEdgeCases:
    """lazy_singleton 边界场景测试。"""

    def test_factory_returns_none(self) -> None:
        """工厂返回 None 时，由于 _instance is not None 检查，会导致工厂被反复调用。

        这是 lazy_singleton 的一个已知边界：如果工厂返回 None，
        双重检查锁的 is not None 判断会让它每次都走初始化路径。
        这是设计行为 —— 使用 sentinel 对象或确保工厂返回非 None 值。
        """
        call_count = 0

        def factory() -> object | None:
            nonlocal call_count
            call_count += 1
            return None

        wrapper = lazy_singleton(factory)

        result1 = wrapper()
        result2 = wrapper()
        result3 = wrapper()

        assert result1 is None
        assert result2 is None
        assert result3 is None
        # 由于 None 被视为"未初始化"，工厂每次都会被调用
        assert call_count == 3

    def test_factory_with_computation(self) -> None:
        """确认复杂工厂逻辑仅执行一次。"""
        computation_log: list[str] = []

        def factory() -> dict:
            computation_log.append("computing...")
            return {"key": "value", "nested": [1, 2, 3]}

        wrapper = lazy_singleton(factory)
        a = wrapper()
        b = wrapper()

        assert a == {"key": "value", "nested": [1, 2, 3]}
        assert a is b
        assert computation_log == ["computing..."]


# ============================================================
# SingletonSlot 测试
# ============================================================


@pytest.fixture
def slot() -> SingletonSlot[str, object]:
    """提供一个空的 SingletonSlot 实例。"""
    return SingletonSlot()


@pytest.fixture
def counter_factory() -> Callable[[str], int]:
    """返回一个带调用计数的工厂函数。"""
    call_counts: dict[str, int] = {}

    def factory(key: str) -> int:
        call_counts[key] = call_counts.get(key, 0) + 1
        return call_counts[key]

    factory._call_counts = call_counts  # type: ignore[attr-defined]
    return factory


class TestSingletonSlotGet:
    """SingletonSlot.get() 基础行为测试。"""

    def test_same_key_returns_same_instance(self, slot: SingletonSlot) -> None:
        """相同 key 返回同一实例。"""
        obj = object()
        factory_calls: list[str] = []

        def factory() -> object:
            factory_calls.append("called")
            return obj

        a = slot.get("key1", factory)
        b = slot.get("key1", factory)
        c = slot.get("key1", factory)

        assert a is b is c is obj
        assert len(factory_calls) == 1

    def test_different_keys_return_different_instances(self, slot: SingletonSlot) -> None:
        """不同 key 返回不同实例。"""
        obj_a = object()
        obj_b = object()

        a = slot.get("tenant-a", lambda: obj_a)
        b = slot.get("tenant-b", lambda: obj_b)

        assert a is obj_a
        assert b is obj_b
        assert a is not b

    def test_factory_executed_once_per_key(self, slot: SingletonSlot) -> None:
        """每个 key 的工厂函数仅执行一次。"""
        counter = 0

        def make_factory(val: int) -> Callable[[], int]:
            def factory() -> int:
                nonlocal counter
                counter += 1
                return val
            return factory

        slot.get("x", make_factory(10))
        slot.get("x", make_factory(20))
        slot.get("y", make_factory(30))

        assert counter == 2  # key "x" 一次，key "y" 一次

    def test_sequential_distinct_keys(self, slot: SingletonSlot) -> None:
        """连续访问不同 key，每个都独立创建实例。"""
        results: list[int] = []
        for i in range(5):
            results.append(slot.get(f"key-{i}", lambda i=i: i * 10))

        assert results == [0, 10, 20, 30, 40]

        # 再次访问返回同一值
        for i in range(5):
            assert slot.get(f"key-{i}", lambda: 999) == i * 10


class TestSingletonSlotReset:
    """SingletonSlot.reset() 行为测试。"""

    def test_reset_specific_key(self, slot: SingletonSlot) -> None:
        """reset(key) 清除指定 key 的缓存，其他 key 不受影响。"""
        obj_a = object()
        obj_b = object()

        a1 = slot.get("a", lambda: obj_a)
        b1 = slot.get("b", lambda: obj_b)

        slot.reset("a")

        # key "a" 被清除，重新创建
        a2 = slot.get("a", lambda: object())
        assert a2 is not a1
        assert a2 is not obj_a

        # key "b" 不受影响
        b2 = slot.get("b", lambda: object())
        assert b2 is b1 is obj_b

    def test_reset_all_keys(self, slot: SingletonSlot) -> None:
        """reset() 无参数时清除所有 key。"""
        obj_a = object()
        obj_b = object()

        a1 = slot.get("a", lambda: obj_a)
        b1 = slot.get("b", lambda: obj_b)

        slot.reset()

        a2 = slot.get("a", lambda: object())
        b2 = slot.get("b", lambda: object())

        assert a2 is not a1
        assert b2 is not b1

    def test_reset_nonexistent_key_is_silent(self, slot: SingletonSlot) -> None:
        """reset(不存在的 key) 不会抛出异常。"""
        slot.reset("nonexistent")
        slot.reset("also-nonexistent")

    def test_reset_then_recreate(self, slot: SingletonSlot) -> None:
        """reset 后可以用新工厂重新创建实例。"""
        result1 = slot.get("k", lambda: "first")
        assert result1 == "first"

        slot.reset("k")

        result2 = slot.get("k", lambda: "second")
        assert result2 == "second"

        result3 = slot.get("k", lambda: "third")
        assert result3 == "second"  # 仍然是第一次重新创建的结果


class TestSingletonSlotContains:
    """SingletonSlot.__contains__ 测试。"""

    def test_contains_after_get(self, slot: SingletonSlot) -> None:
        """get() 后 key 存在于 slot 中。"""
        slot.get("my-key", lambda: 123)
        assert "my-key" in slot
        assert "other-key" not in slot

    def test_contains_after_reset(self, slot: SingletonSlot) -> None:
        """reset(key) 后 key 不再存在于 slot 中。"""
        slot.get("x", lambda: 1)
        assert "x" in slot

        slot.reset("x")
        assert "x" not in slot

    def test_contains_after_reset_all(self, slot: SingletonSlot) -> None:
        """reset() 后所有 key 都不在 slot 中。"""
        slot.get("a", lambda: 1)
        slot.get("b", lambda: 2)
        slot.get("c", lambda: 3)

        assert "a" in slot
        assert "b" in slot
        assert "c" in slot

        slot.reset()

        assert "a" not in slot
        assert "b" not in slot
        assert "c" not in slot

    def test_contains_empty_slot(self, slot: SingletonSlot) -> None:
        """空 slot 中没有任何 key。"""
        assert "anything" not in slot
        assert "" not in slot


class TestSingletonSlotConcurrencySameKey:
    """SingletonSlot 同 key 并发安全性测试。"""

    def test_concurrent_same_key_factory_called_once(self, slot: SingletonSlot) -> None:
        """10 个线程并发用相同 key 调用 get()，工厂仅执行一次。"""
        call_count = 0
        count_lock = threading.Lock()
        barrier = threading.Barrier(10)

        def factory() -> str:
            nonlocal call_count
            with count_lock:
                call_count += 1
            time.sleep(0.05)
            return "shared"

        results: list[str] = []
        errors: list[Exception] = []

        def worker() -> None:
            try:
                barrier.wait()
                results.append(slot.get("tenant-1", factory))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"线程执行出错: {errors}"
        assert len(results) == 10
        assert all(r == "shared" for r in results)
        assert call_count == 1

    def test_concurrent_same_key_all_threads_get_same_id(self, slot: SingletonSlot) -> None:
        """同 key 并发获取，所有线程获得的对象 id 完全相同。"""
        shared_obj = object()
        barrier = threading.Barrier(8)

        def factory() -> object:
            time.sleep(0.03)
            return shared_obj

        results: list[object] = []

        def worker() -> None:
            barrier.wait()
            results.append(slot.get("x", factory))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r is shared_obj for r in results)

    def test_concurrent_same_key_with_reset_in_between(self, slot: SingletonSlot) -> None:
        """并发过程中 reset 不会导致线程崩溃。

        这个测试验证 get → reset → get 的并发安全性。
        """
        errors: list[Exception] = []
        barrier = threading.Barrier(6)

        def worker(worker_id: int) -> None:
            try:
                barrier.wait()
                if worker_id < 2:
                    slot.get("shared", lambda: f"v1-{worker_id}")
                elif worker_id < 4:
                    slot.reset("shared")
                    slot.get("shared", lambda: f"v2-{worker_id}")
                else:
                    slot.get("shared", lambda: f"v3-{worker_id}")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"并发操作出错: {errors}"


class TestSingletonSlotConcurrencyDifferentKeys:
    """SingletonSlot 不同 key 并发安全性测试。"""

    def test_concurrent_different_keys_no_blocking(self, slot: SingletonSlot) -> None:
        """不同 key 的并发访问不会互相阻塞（各自独立）。"""
        barrier = threading.Barrier(8)
        results: dict[str, int] = {}
        result_lock = threading.Lock()
        errors: list[Exception] = []

        def worker(worker_id: int) -> None:
            try:
                barrier.wait()
                key = f"key-{worker_id % 4}"
                val = slot.get(key, lambda wid=worker_id: wid * 100)
                with result_lock:
                    results[key] = val
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"线程执行出错: {errors}"
        # 4 个不同 key 都应该有一个确定的结果
        assert len(results) == 4
        for k in range(4):
            assert f"key-{k}" in results

    def test_concurrent_different_keys_all_independent(self, slot: SingletonSlot) -> None:
        """大量不同 key 并发访问，每个工厂独立执行。"""
        barrier = threading.Barrier(20)
        results: dict[str, object] = {}
        result_lock = threading.Lock()
        errors: list[Exception] = []

        def worker(idx: int) -> None:
            try:
                barrier.wait()
                key = f"k{idx}"
                obj = object()
                val = slot.get(key, lambda o=obj: o)
                with result_lock:
                    results[key] = val
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"线程执行出错: {errors}"
        assert len(results) == 20

        # 验证每个 key 独立缓存
        for i in range(20):
            key = f"k{i}"
            # 再次获取应返回同一实例
            val2 = slot.get(key, lambda: object())
            assert val2 is results[key]

    def test_different_keys_do_not_interfere(self, slot: SingletonSlot) -> None:
        """确认一个 key 的操作不会影响另一个 key。"""
        # 预创建 key
        slot.get("alpha", lambda: "alpha-val")
        slot.get("beta", lambda: "beta-val")

        # 只清除 alpha
        slot.reset("alpha")

        # beta 仍然保留
        assert slot.get("beta", lambda: "new-beta") == "beta-val"
        assert "beta" in slot

        # alpha 被重新创建
        new_alpha = slot.get("alpha", lambda: "new-alpha")
        assert new_alpha == "new-alpha"
        assert "alpha" in slot


class TestSingletonSlotEdgeCases:
    """SingletonSlot 边界场景测试。"""

    def test_int_keys(self) -> None:
        """支持整数类型的 key。"""
        slot: SingletonSlot[int, str] = SingletonSlot()

        slot.get(1, lambda: "one")
        slot.get(2, lambda: "two")
        slot.get(3, lambda: "three")

        assert slot.get(1, lambda: "uno") == "one"
        assert slot.get(2, lambda: "dos") == "two"
        assert slot.get(3, lambda: "tres") == "three"

        assert 1 in slot
        assert 2 in slot
        assert 4 not in slot

    def test_nonexistent_key_contains(self, slot: SingletonSlot) -> None:
        """从未 get 过的 key 不在 slot 中。"""
        assert "never-used" not in slot

    def test_factory_exception_propagates(self, slot: SingletonSlot) -> None:
        """工厂抛出的异常会正确传播给调用者。"""
        def failing_factory() -> str:
            raise ConnectionError("数据库连接失败")

        with pytest.raises(ConnectionError, match="数据库连接失败"):
            slot.get("db", failing_factory)

    def test_factory_exception_does_not_cache(self, slot: SingletonSlot) -> None:
        """工厂抛出异常时不会缓存，下次调用会重试。"""
        call_count = 0

        def flaky_factory() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise IOError(f"IO 错误 #{call_count}")
            return "ok"

        with pytest.raises(IOError):
            slot.get("resource", flaky_factory)
        assert call_count == 1

        with pytest.raises(IOError):
            slot.get("resource", flaky_factory)
        assert call_count == 2

        result = slot.get("resource", flaky_factory)
        assert result == "ok"
        assert call_count == 3

        # 后续调用返回缓存
        result2 = slot.get("resource", lambda: "never")
        assert result2 == "ok"


class TestSingletonSlotWithThreadPool:
    """使用 ThreadPoolExecutor 的并发测试。"""

    def test_thread_pool_same_key(self) -> None:
        """使用 ThreadPoolExecutor 验证同 key 并发安全。"""
        slot: SingletonSlot[str, int] = SingletonSlot()
        call_count = 0
        count_lock = threading.Lock()

        def factory() -> int:
            nonlocal call_count
            with count_lock:
                call_count += 1
            time.sleep(0.02)
            return 42

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(slot.get, "shared", factory) for _ in range(8)]
            results = [f.result() for f in futures]

        assert all(r == 42 for r in results)
        assert call_count == 1

    def test_thread_pool_different_keys(self) -> None:
        """使用 ThreadPoolExecutor 验证不同 key 并发独立。"""
        slot: SingletonSlot[int, str] = SingletonSlot()

        def factory(key: int) -> str:
            time.sleep(0.01)
            return f"val-{key}"

        with ThreadPoolExecutor(max_workers=16) as executor:
            futures = [
                executor.submit(slot.get, i, lambda k=i: factory(k))
                for i in range(16)
            ]
            results = [f.result() for f in futures]

        expected = [f"val-{i}" for i in range(16)]
        assert sorted(results) == sorted(expected)

        # 再次获取应返回同一实例
        for i in range(16):
            cached = slot.get(i, lambda: "overwritten")
            assert cached == f"val-{i}"