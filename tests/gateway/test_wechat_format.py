"""R6-3: unit tests for butler.gateway.platforms.wechat_format."""

from __future__ import annotations

import pytest

from butler.gateway.platforms import wechat_format as wf


@pytest.mark.unit
class TestRewriteHeadersForWechat:
    def test_h1_becomes_bracket_title(self):
        assert wf._rewrite_headers_for_wechat("# Deploy") == "【Deploy】"

    def test_h2_becomes_bold(self):
        assert wf._rewrite_headers_for_wechat("## Notes") == "**Notes**"

    def test_plain_line_unchanged(self):
        assert wf._rewrite_headers_for_wechat("plain text") == "plain text"


@pytest.mark.unit
class TestRewriteTableBlockForWechat:
    def test_two_column_table_becomes_bullets(self):
        lines = ["| Name | Value |", "| --- | --- |", "| foo | bar |"]
        out = wf._rewrite_table_block_for_wechat(lines)
        assert "- Name: foo" in out
        assert "Value: bar" in out

    def test_short_table_passthrough(self):
        lines = ["| only |"]
        assert wf._rewrite_table_block_for_wechat(lines) == "| only |"


@pytest.mark.unit
class TestNormalizeMarkdownBlocks:
    def test_collapses_extra_blank_lines(self):
        raw = "line one\n\n\n\nline two"
        out = wf._normalize_markdown_blocks(raw)
        assert out.count("\n\n") == 1
        assert "line one" in out and "line two" in out


@pytest.mark.unit
class TestSplitTextForWechatDelivery:
    def test_empty_returns_empty_list(self):
        assert wf._split_text_for_wechat_delivery("", 2000) == []

    def test_short_single_message_compact_mode(self):
        assert wf._split_text_for_wechat_delivery("hello", 2000) == ["hello"]

    def test_splits_short_chatty_multiline_block(self):
        content = "你好\n收到\n明白"
        chunks = wf._split_text_for_wechat_delivery(content, 2000)
        assert len(chunks) == 3
        assert chunks == ["你好", "收到", "明白"]

    def test_per_line_mode_splits_by_unit(self):
        content = "第一行\n第二行"
        chunks = wf._split_text_for_wechat_delivery(content, 2000, split_per_line=True)
        assert len(chunks) == 2

    def test_oversized_content_uses_packing(self):
        long_block = "段落\n\n" + ("x" * 1200)
        chunks = wf._split_text_for_wechat_delivery(long_block, 500)
        assert len(chunks) >= 2
        assert all(len(c) <= 500 for c in chunks)


@pytest.mark.unit
class TestDeliveryUnitHelpers:
    def test_should_split_short_chat_block(self):
        block = "好的\n收到\n继续"
        assert wf._should_split_short_chat_block_for_wechat(block) is True

    def test_heading_block_not_split_as_chat(self):
        block = "标题：\n好的\n收到"
        assert wf._should_split_short_chat_block_for_wechat(block) is False
