"""Tests for outbound internal ops leak scrubbing."""

from butler.gateway.internal_leak_scrub import scrub_internal_ops_leaks


def test_scrubs_recovery_notice():
    raw = "（会话已从 transcript 恢复工具记录；问「刚才读过哪些文件」时只列 read_file 路径。）\n\n主公好"
    assert "transcript" not in scrub_internal_ops_leaks(raw)
    assert "主公好" in scrub_internal_ops_leaks(raw)


def test_scrubs_approval_phrases():
    raw = "反馈需要审批，先跳过。我直接用已有的搜索结果来回答。\n\n结论"
    out = scrub_internal_ops_leaks(raw)
    assert "审批" not in out
    assert "结论" in out
