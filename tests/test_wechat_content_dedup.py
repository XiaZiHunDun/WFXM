"""WeChat inbound content dedup must not block intentional user resends (M4)."""

from __future__ import annotations

import time

import pytest

from butler.gateway.platforms.helpers import MessageDeduplicator


@pytest.mark.module_test
class TestContentDedupWindow:
    def test_same_content_allowed_after_short_ttl(self):
        dedup = MessageDeduplicator(ttl_seconds=2)
        key = "content:user:abc"
        assert dedup.is_duplicate(key) is False
        assert dedup.is_duplicate(key) is True
        time.sleep(2.1)
        assert dedup.is_duplicate(key) is False

    def test_message_id_dedup_can_use_longer_ttl_independently(self):
        id_dedup = MessageDeduplicator(ttl_seconds=300)
        content_dedup = MessageDeduplicator(ttl_seconds=20)
        mid = "msg-123"
        body = "content:user:hash"
        assert id_dedup.is_duplicate(mid) is False
        assert content_dedup.is_duplicate(body) is False
        assert id_dedup.is_duplicate(mid) is True
        assert content_dedup.is_duplicate(body) is True
