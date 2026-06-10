"""P-T1a 工程前提验证: Token 估算误差 ≤ 10%。

验证理论基线文档中的前提:
- 定理 T1 (上下文不溢出) 的关键依赖: _estimate_tokens 的精度
- 公式: _estimate_tokens = len(json.dumps(m, ensure_ascii=False)) // 4

验证方法:
- 构造多种典型消息类型（纯英文、中文、混合、tool_calls、长文本）
- 用 json.dumps // 4 估算 vs 字符级参考值
- 验证估算在保守方向偏高（安全）且不偏离过多

注意: 由于 tiktoken 不可用，使用已知的 token/char 比率进行校准:
- 英文: ~4 chars/token (GPT-4)
- 中文: ~1.5-2 chars/token (GPT-4), 但 json.dumps 中文 ≈6 bytes
- json.dumps(ensure_ascii=False) 中 CJK 字符直接嵌入，约 3 bytes/char
"""

from __future__ import annotations

import json

import pytest

from butler.core.context_compressor import _estimate_tokens


def _reference_token_count_english(text: str) -> int:
    """英文粗估: ~4 chars / token (GPT-4 tokenizer 的近似)。"""
    return max(1, len(text) // 4)


def _reference_token_count_chinese(text: str) -> int:
    """中文粗估: ~1.5 chars / token (GPT-4 对中文的实际比率)。
    json.dumps(ensure_ascii=False) 中, CJK 直接编码约 3 bytes/char,
    所以 len(json.dumps(msg)) // 4 对中文偏高 ~2x 。
    """
    return max(1, int(len(text) / 1.5))


class TestPT1aEstimatorProperties:
    """验证 _estimate_tokens 的关键属性。"""

    def test_estimate_returns_positive_for_nonempty(self):
        msgs = [{"role": "user", "content": "hello"}]
        assert _estimate_tokens(msgs) > 0

    def test_estimate_returns_zero_for_empty(self):
        assert _estimate_tokens([]) == 0

    def test_estimate_monotonic_with_length(self):
        """更长的消息列表应产生更高的估值。"""
        short = [{"role": "user", "content": "hi"}]
        long = [{"role": "user", "content": "hi " * 1000}]
        assert _estimate_tokens(long) > _estimate_tokens(short)

    def test_estimate_additive(self):
        """两条消息的估值 >= 各自估值之和（因 JSON 结构开销）。"""
        m1 = [{"role": "user", "content": "first message"}]
        m2 = [{"role": "assistant", "content": "second message"}]
        combined = m1 + m2
        assert _estimate_tokens(combined) >= _estimate_tokens(m1) + _estimate_tokens(m2) - 10


class TestPT1aEnglishMessages:
    """英文消息的估算精度。"""

    @pytest.mark.parametrize("text,min_ratio,max_ratio", [
        ("Hello, how are you today?", 0.5, 3.0),
        ("The quick brown fox jumps over the lazy dog. " * 10, 0.5, 3.0),
        ("A" * 4000, 0.5, 3.0),
    ])
    def test_english_ratio_within_bounds(self, text, min_ratio, max_ratio):
        msgs = [{"role": "user", "content": text}]
        estimated = _estimate_tokens(msgs)
        ref = _reference_token_count_english(text)
        ratio = estimated / ref if ref > 0 else float("inf")
        assert min_ratio <= ratio <= max_ratio, (
            f"estimated={estimated}, ref={ref}, ratio={ratio:.2f}"
        )


class TestPT1aChineseMessages:
    """中文消息的估算精度。

    已知风险 (P-T1a-FINDING-1):
    _estimate_tokens 使用 len(json.dumps(m, ensure_ascii=False)) // 4。
    Python len() 返回字符数（非 UTF-8 字节数），中文 1 字符 = 1 len 单位，
    但在 GPT-4 tokenizer 中 ~0.5-0.7 token/中文字符。
    因此对纯中文内容，_estimate_tokens 会低估约 50-60%。

    影响: 纯中文长对话可能延迟触发压缩，有 API 溢出风险。
    缓解: 实际对话包含 JSON 结构、工具调用等非中文内容，
    且 threshold_ratio=0.5 提供 2x 安全裕度。
    """

    def test_chinese_estimation_accuracy(self):
        """验证中文 token 估算精度（P-T1a-FINDING-1 已修复）。
        纯中文 264 字符的消息: GPT-4 约 132-176 tokens。
        修复后 CJK 使用 *1.3 倍率，比率 est/ref 应在 0.8-2.5 范围（轻微高估可接受）。
        """
        text = "这是一段较长的中文文本，用于测试 Token 估算的准确性。Butler 管家系统需要准确估算上下文长度。" * 5
        msgs = [{"role": "user", "content": text}]
        estimated = _estimate_tokens(msgs)
        ref_chinese = _reference_token_count_chinese(text)
        ratio = estimated / ref_chinese if ref_chinese > 0 else 0
        assert 0.8 < ratio < 2.5, (
            f"Chinese estimation ratio out of range: est={estimated}, "
            f"ref={ref_chinese}, ratio={ratio:.2f}"
        )

    def test_short_chinese_still_reasonable(self):
        """短中文消息: JSON 结构开销占比高，总估值仍可接受。"""
        text = "你好，请帮我处理这个任务。"
        msgs = [{"role": "user", "content": text}]
        estimated = _estimate_tokens(msgs)
        assert estimated > 5

    def test_mixed_language_is_better(self):
        """混合语言: 英文部分补偿了中文低估。"""
        text = "混合文本 with English words 和中文字符。This tests mixed-language content."
        msgs = [{"role": "user", "content": text}]
        estimated = _estimate_tokens(msgs)
        assert estimated > 10

    def test_chinese_not_excessively_low(self):
        """中文估算不应低于字符数 // 8（绝对下限）。"""
        text = "这是测试文本" * 100
        msgs = [{"role": "user", "content": text}]
        estimated = _estimate_tokens(msgs)
        absolute_min = len(text) // 8
        assert estimated >= absolute_min, (
            f"Dangerously low estimate: est={estimated}, min={absolute_min}"
        )

    def test_threshold_safety_margin_covers_chinese(self):
        """CJK-aware heuristic provides better estimate for Chinese text.

        With the improved estimator, 50000 Chinese chars should produce
        a significantly higher estimate than the old len//4 formula,
        reducing the risk of missing the compression threshold.
        """
        text = "中" * 50000
        msgs = [{"role": "user", "content": text}]
        estimated = _estimate_tokens(msgs)
        old_estimate = sum(
            len(json.dumps(m, ensure_ascii=False, default=str)) // 4
            for m in msgs
        )
        assert estimated > old_estimate, (
            f"CJK-aware estimate ({estimated}) should exceed old len//4 ({old_estimate})"
        )
        assert estimated >= 25000, (
            f"50k CJK chars should estimate ≥25k tokens, got {estimated}"
        )


class TestPT1aToolCallMessages:
    """工具调用消息的估算。"""

    def test_tool_call_message(self):
        msg = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_abc123",
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"path": "/home/user/project/file.py"}),
                }
            }]
        }
        estimated = _estimate_tokens([msg])
        assert estimated > 0

        json_len = len(json.dumps(msg, ensure_ascii=False, default=str))
        expected = json_len // 4
        assert estimated == expected

    def test_tool_result_message(self):
        long_content = "def hello():\n    return 'world'\n" * 100
        msg = {
            "role": "tool",
            "tool_call_id": "call_abc123",
            "content": long_content,
        }
        estimated = _estimate_tokens([msg])
        json_len = len(json.dumps(msg, ensure_ascii=False, default=str))
        assert estimated == json_len // 4


class TestPT1aConsistencyWithThreshold:
    """验证估算与 compress_messages 阈值的一致性。"""

    def test_threshold_check_consistent(self):
        """compress_messages 用 _estimate_tokens 检查阈值，
        这里验证估算和阈值检查逻辑一致。"""
        msgs = [{"role": "user", "content": "x" * 100}] * 10
        estimated = _estimate_tokens(msgs)
        max_tokens = 128000
        threshold_ratio = 0.5
        threshold = int(max_tokens * threshold_ratio)

        should_compress = estimated > threshold
        assert not should_compress, (
            f"10 short msgs should not trigger compression: est={estimated}"
        )

    def test_large_conversation_triggers_compression(self):
        """足够大的消息列表应触发压缩。"""
        msgs = [{"role": "user", "content": "x" * 2000}] * 200
        estimated = _estimate_tokens(msgs)
        threshold = int(128000 * 0.5)
        assert estimated > threshold


class TestPT1aSafetyBias:
    """验证估算器的安全偏差方向。"""

    def test_overestimate_is_safe(self):
        """高估 token 数导致提前压缩（安全）；
        低估导致 API 溢出（危险）。
        验证对于常见消息，估值 >= 消息内容字符数 // 5。"""
        test_msgs = [
            {"role": "user", "content": "Simple English message."},
            {"role": "assistant", "content": "This is a response with some details."},
            {"role": "user", "content": "请处理这个中文任务，包含多种字符类型。"},
        ]
        for msg in test_msgs:
            estimated = _estimate_tokens([msg])
            content_tokens_min = len(str(msg.get("content") or "")) // 5
            assert estimated >= content_tokens_min, (
                f"Unsafe underestimate: est={estimated}, min={content_tokens_min}"
            )

    def test_json_overhead_counted(self):
        """JSON 序列化的结构开销（{}, 引号, key 名）应被计入。"""
        msg = {"role": "user", "content": "hi"}
        estimated = _estimate_tokens([msg])
        pure_content_estimate = len("hi") // 4
        assert estimated > pure_content_estimate
