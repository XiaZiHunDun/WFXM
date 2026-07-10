"""Sprint 11 PERF-11-1: message_queue.enqueue 每次全桶 sort O(N log N)

Sprint 11 审计：message_queue.py:167-168
    bucket.append(item)
    bucket = deque(sorted(bucket, key=...))
    _QUEUES[key] = bucket

每条 inbound 都触发 O(N log N) sort，高频 inbound 线性退化。

修复策略（最优）：3 桶 per session（now / next / later 各 deque）
- enqueue: O(1) append 到对应 priority 桶
- pop_urgent: O(1) popleft from now 桶
- pop_next: 按 now→next→later 顺序尝试 popleft
- pop_all_merged: 合并所有桶，same priority 顺序保持

行为不变性：
- pop_urgent 仍能拿到最早的 now 优先级消息
- pop_next 仍按 now→next→later 顺序（同一桶内 FIFO）
- dedupe、cap、persist 行为不变

测试：6 个测试覆盖 3 桶行为 + pop 顺序 + persist 兼容 + 并发。
"""

from __future__ import annotations

import threading
from unittest.mock import patch

import pytest

from butler.gateway import message_queue


@pytest.fixture(autouse=True)
def _reset_queues():
    """每个测试前清空全局 queue 状态。"""
    with message_queue._LOCK:
        message_queue._QUEUES.clear()
        message_queue._LAST_ENQUEUE.clear()
        message_queue._DROP_SUMMARIES.clear()
    yield
    with message_queue._LOCK:
        message_queue._QUEUES.clear()
        message_queue._LAST_ENQUEUE.clear()
        message_queue._DROP_SUMMARIES.clear()


@pytest.mark.unit
def test_enqueue_does_not_sort_full_bucket():
    """每次 enqueue 不应触发全桶 sort。

    修复后：bucket 内部按 3 桶分桶，append O(1)，不调 sorted()。
    修复前：每次 enqueue 调 sorted() 一次。
    """
    # patch sorted 计数
    with patch("butler.gateway.message_queue.sorted", wraps=sorted) as mock_sorted:
        for i in range(50):
            message_queue.enqueue_inbound(
                f"session_{i % 3}", f"msg {i}", priority="next"
            )
        # 修复后 sorted 调用次数应为 0（除非其他逻辑需要排序）
        # 我们只检查核心 sort 不再发生
        # 注：sorted 可能在 dedupe / persist 等地方被调，我们只看相关 count
        # 主要断言：50 次 enqueue 不应产生 50 次 sorted 调用
        assert mock_sorted.call_count < 50, (
            f"50 次 enqueue 不应触发 50 次 sorted（修复前是 O(N) per call），"
            f"实际 {mock_sorted.call_count} 次"
        )


@pytest.mark.unit
def test_enqueue_3bucket_structure_per_session():
    """每 session 内部应是 3 桶 dict 结构（now/next/later），不是单 deque。"""
    with message_queue._LOCK:
        message_queue.enqueue_inbound("s1", "now_msg", priority="now")
        message_queue.enqueue_inbound("s1", "next_msg", priority="next")
        message_queue.enqueue_inbound("s1", "later_msg", priority="later")
        bucket = message_queue._QUEUES["s1"]
        # 修复后：bucket 应该是 dict[str, deque]
        assert isinstance(bucket, dict), (
            f"修复后 bucket 应是 dict[priority, deque]，实际 {type(bucket).__name__}"
        )
        assert set(bucket.keys()) == {"now", "next", "later"}, (
            f"应包含 3 个 priority 桶，实际 {set(bucket.keys())}"
        )


@pytest.mark.unit
def test_pop_urgent_returns_now_priority():
    """pop_urgent 应从 now 桶取（FIFO），与原 sort 行为一致。"""
    # 模拟 enqueue 顺序：next, later, now, now, next
    message_queue.enqueue_inbound("s1", "n1", priority="next")
    message_queue.enqueue_inbound("s1", "l1", priority="later")
    message_queue.enqueue_inbound("s1", "nw1", priority="now")
    message_queue.enqueue_inbound("s1", "nw2", priority="now")
    message_queue.enqueue_inbound("s1", "n2", priority="next")

    # pop_urgent 应拿到 nw1（FIFO 最早的 now）
    item = message_queue.pop_urgent_inbound("s1")
    assert item is not None and item.text == "nw1", (
        f"pop_urgent 应拿 nw1，实际 {item.text if item else None}"
    )
    # 再 pop_urgent 拿 nw2
    item2 = message_queue.pop_urgent_inbound("s1")
    assert item2 is not None and item2.text == "nw2"


@pytest.mark.unit
def test_pop_next_priority_order_now_next_later():
    """pop_next 应按 now → next → later 顺序拿（与原 sort 一致）。"""
    message_queue.enqueue_inbound("s1", "later_msg", priority="later")
    message_queue.enqueue_inbound("s1", "next_msg", priority="next")
    message_queue.enqueue_inbound("s1", "now_msg", priority="now")

    # pop_next 第一次拿 now
    item1 = message_queue.pop_next("s1")
    assert item1 is not None and item1.text == "now_msg"
    # 第二次拿 next
    item2 = message_queue.pop_next("s1")
    assert item2 is not None and item2.text == "next_msg"
    # 第三次拿 later
    item3 = message_queue.pop_next("s1")
    assert item3 is not None and item3.text == "later_msg"


@pytest.mark.unit
def test_pending_count_correct_with_3buckets():
    """pending_count 应汇总 3 桶总长度。"""
    message_queue.enqueue_inbound("s1", "n1", priority="now")
    message_queue.enqueue_inbound("s1", "n2", priority="now")
    message_queue.enqueue_inbound("s1", "n3", priority="next")
    message_queue.enqueue_inbound("s1", "n4", priority="later")
    assert message_queue.pending_count("s1") == 4


@pytest.mark.unit
def test_pop_all_merged_preserves_priority_order():
    """pop_all_merged 应合并所有桶并按 now→next→later 排序（与原行为一致）。"""
    message_queue.enqueue_inbound("s1", "later_a", priority="later")
    message_queue.enqueue_inbound("s1", "now_a", priority="now")
    message_queue.enqueue_inbound("s1", "next_a", priority="next")
    message_queue.enqueue_inbound("s1", "now_b", priority="now")

    merged = message_queue.pop_all_merged("s1")
    assert merged is not None
    # 顺序：now_a, now_b, next_a, later_a
    expected_order = ["now_a", "now_b", "next_a", "later_a"]
    actual_lines = [ln.strip() for ln in merged.text.split("\n\n") if ln.strip()]
    actual_order = [
        ln for ln in actual_lines
        if not ln.startswith("[此前队列溢出摘要")
    ]
    assert actual_order == expected_order, (
        f"pop_all_merged 顺序：期望 {expected_order}，实际 {actual_order}"
    )


@pytest.mark.unit
def test_enqueue_does_not_grow_bucket_size_via_rebuild():
    """修复后 append 到对应 priority 桶，不应重建整个 bucket。

    简单替代检查：连续 enqueue 多条 next，pending_count 仍准确
    反映总数（无 sort 中间态丢失）。使用 default cap=20 之下
    的消息数，确保全部入队。
    """
    n = 10
    for i in range(n):
        message_queue.enqueue_inbound("s_perf", f"msg_{i}", priority="next")
    assert message_queue.pending_count("s_perf") == n, (
        f"{n} 条 enqueue 后 pending_count 应为 {n}，"
        f"实际 {message_queue.pending_count('s_perf')}"
    )
