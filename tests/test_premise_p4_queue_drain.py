"""P4 工程前提验证: Queue drain 延迟和收敛性。

验证理论基线文档中的命题:
- 命题 2.3 (Drain 终止): drain 循环在有限步内终止
- 命题 2.4 (无消息饥饿): 停止发送后队列最终清空
- 定理 T2 (队列收敛): drain 机制保证所有入队消息最终被处理
"""

from __future__ import annotations

import time

import pytest

from butler.gateway.message_queue import (
    enqueue_inbound,
    pending_count,
    pop_all_merged,
    pop_next,
    reset_queue,
)


@pytest.fixture(autouse=True)
def _clean_queue():
    reset_queue()
    yield
    reset_queue()


class TestP4DrainConvergence:
    """定理 T2: 队列收敛 — drain 后所有消息被处理。"""

    def test_single_message_drain(self):
        enqueue_inbound("s1", "hello")
        assert pending_count("s1") == 1
        item = pop_next("s1")
        assert item is not None
        assert item.text == "hello"
        assert pending_count("s1") == 0

    def test_multiple_messages_drain_in_order(self):
        for i in range(5):
            enqueue_inbound("s1", f"msg-{i}")
            time.sleep(0.01)  # avoid dedup window

        assert pending_count("s1") == 5
        results = []
        while pending_count("s1") > 0:
            item = pop_next("s1")
            assert item is not None
            results.append(item.text)
        assert results == [f"msg-{i}" for i in range(5)]
        assert pending_count("s1") == 0

    def test_priority_order_now_before_next_before_later(self):
        enqueue_inbound("s1", "later msg", priority="later")
        time.sleep(0.01)
        enqueue_inbound("s1", "next msg", priority="next")
        time.sleep(0.01)
        enqueue_inbound("s1", "/urgent important", priority="now")

        items = []
        while pending_count("s1") > 0:
            items.append(pop_next("s1").text)
        assert items[0] == "/urgent important"  # now first
        assert items[1] == "next msg"           # then next
        assert items[2] == "later msg"          # then later

    def test_collect_mode_merges_all(self):
        for i in range(3):
            enqueue_inbound("s1", f"part-{i}")
            time.sleep(0.01)

        merged = pop_all_merged("s1")
        assert merged is not None
        assert "part-0" in merged.text
        assert "part-1" in merged.text
        assert "part-2" in merged.text
        assert pending_count("s1") == 0

    def test_drain_convergence_large_queue(self):
        """命题 2.3 + 2.4: 20 条消息全部被 drain。"""
        for i in range(20):
            enqueue_inbound("s1", f"bulk-{i}")
            time.sleep(0.005)

        assert pending_count("s1") == 20
        drained = 0
        while pending_count("s1") > 0:
            item = pop_next("s1")
            assert item is not None
            drained += 1
            assert drained <= 20
        assert drained == 20
        assert pending_count("s1") == 0

    def test_empty_queue_pop_returns_none(self):
        assert pop_next("nonexistent") is None
        assert pop_all_merged("nonexistent") is None


class TestP4DrainLatency:
    """P4: Queue drain 延迟 <= 5s (对于合理大小的队列)。"""

    def test_drain_10_messages_under_100ms(self):
        for i in range(10):
            enqueue_inbound("s1", f"latency-{i}")
            time.sleep(0.005)

        t0 = time.perf_counter()
        while pending_count("s1") > 0:
            pop_next("s1")
        elapsed = time.perf_counter() - t0
        assert elapsed < 0.1, f"Drain 10 messages took {elapsed:.3f}s (> 100ms)"

    def test_drain_50_messages_under_500ms(self):
        for i in range(50):
            enqueue_inbound("s1", f"perf-{i}")
            time.sleep(0.003)

        t0 = time.perf_counter()
        while pending_count("s1") > 0:
            pop_next("s1")
        elapsed = time.perf_counter() - t0
        assert elapsed < 0.5, f"Drain 50 messages took {elapsed:.3f}s (> 500ms)"


class TestP4Dedup:
    """去重机制不影响收敛性。"""

    def test_dedup_within_window(self):
        enqueue_inbound("s1", "same text")
        result = enqueue_inbound("s1", "same text")
        assert result is False
        assert pending_count("s1") == 1

    def test_dedup_different_text_passes(self):
        enqueue_inbound("s1", "text A")
        enqueue_inbound("s1", "text B")
        assert pending_count("s1") == 2


class TestP4CapOverflow:
    """容量溢出不导致无限阻塞。"""

    def test_cap_overflow_old_policy(self, monkeypatch):
        monkeypatch.setenv("BUTLER_GATEWAY_QUEUE_CAP", "3")
        monkeypatch.setenv("BUTLER_GATEWAY_QUEUE_DROP", "old")

        for i in range(5):
            enqueue_inbound("s1", f"cap-{i}")
            time.sleep(0.005)

        assert pending_count("s1") <= 3
        while pending_count("s1") > 0:
            pop_next("s1")
        assert pending_count("s1") == 0

    def test_cap_overflow_new_policy(self, monkeypatch):
        monkeypatch.setenv("BUTLER_GATEWAY_QUEUE_CAP", "3")
        monkeypatch.setenv("BUTLER_GATEWAY_QUEUE_DROP", "new")

        for i in range(5):
            enqueue_inbound("s1", f"cap-{i}")
            time.sleep(0.005)

        assert pending_count("s1") <= 3


class TestP4MultiSession:
    """多会话队列互不干扰。"""

    def test_independent_sessions(self):
        enqueue_inbound("s1", "msg for s1")
        enqueue_inbound("s2", "msg for s2")

        assert pending_count("s1") == 1
        assert pending_count("s2") == 1

        item1 = pop_next("s1")
        assert item1.text == "msg for s1"
        assert pending_count("s1") == 0
        assert pending_count("s2") == 1
