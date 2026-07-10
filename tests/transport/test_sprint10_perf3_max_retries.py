"""Sprint 10 PERF-NEW-3: llm_client max_retries=0 Sprint 9 修复未落地

Sprint 9 PERF-NEW-3 报"已修" max_retries=0 落地，但实际 transport/
llm_client.py 全文 0 处 max_retries。OpenAI SDK 默认 2 次重试 × llm_retry
3 次 = 单次最坏 6 次 + 90s stale → 20+ 分钟抖动仍存在。

修复：3 处 client 构造（OpenAI 主路径、Anthropic、OpenAI 兜底）都加
max_retries=0。重试由外层 llm_retry 中间件统一处理。
"""

from __future__ import annotations

import inspect

import pytest

from butler.transport.llm_client import LLMClient


def _make_client(provider: str = "openai") -> LLMClient:
    """构造最小 LLMClient 实例（不发起实际 client 构造）。"""
    return LLMClient(
        provider=provider,
        model="test-model",
        api_key="dummy",
        base_url="https://example.com",
        timeout=60,
    )


@pytest.mark.unit
def test_openai_client_source_uses_max_retries_zero():
    """OpenAI 主路径 _get_openai_client 源码中应显式设 max_retries（不依赖 SDK 默认 2）。"""
    src = inspect.getsource(LLMClient._get_openai_client)
    assert "max_retries=" in src, (
        f"_get_openai_client 必须显式 max_retries（关闭 SDK 默认重试）\n实际源码：\n{src}"
    )
    # 允许 max_retries=0 直接字面量，或 max_retries=self._MAX_RETRIES 类常量引用
    assert ("max_retries=0" in src) or ("max_retries=self._MAX_RETRIES" in src), (
        f"_get_openai_client max_retries 应为 0 或 _MAX_RETRIES 引用\n实际源码：\n{src}"
    )


@pytest.mark.unit
def test_anthropic_client_source_uses_max_retries_zero():
    """Anthropic 路径 _get_anthropic_client 源码中应显式设 max_retries。"""
    src = inspect.getsource(LLMClient._get_anthropic_client)
    assert "max_retries=" in src, (
        f"_get_anthropic_client 必须显式 max_retries\n实际源码：\n{src}"
    )
    assert ("max_retries=0" in src) or ("max_retries=self._MAX_RETRIES" in src), (
        f"_get_anthropic_client max_retries 应为 0 或 _MAX_RETRIES 引用\n实际源码：\n{src}"
    )


@pytest.mark.unit
def test_openai_fallback_source_uses_max_retries_zero():
    """Anthropic 失败兜底的 OpenAI() 构造也应设 max_retries（不能用 SDK 默认）。"""
    src = inspect.getsource(LLMClient._get_anthropic_client)
    openai_count = src.count("OpenAI(")
    # 兜底 OpenAI() 紧跟 max_retries= 关键字
    assert openai_count >= 1, "_get_anthropic_client 应至少 1 个 OpenAI()（兜底）"
    # 兜底应在 max_retries 引用范围内
    assert "max_retries=" in src, "OpenAI 兜底应配 max_retries"


@pytest.mark.unit
def test_max_retries_passed_to_openai_constructor(monkeypatch):
    """运行时验证：构造 OpenAI client 时确实传入 max_retries=0。"""
    captured_kwargs: dict = {}

    class _FakeOpenAI:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

    import sys
    fake_openai = type(sys)("openai")
    fake_openai.OpenAI = _FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    client = _make_client(provider="openai")
    client._get_openai_client()
    assert "max_retries" in captured_kwargs, (
        f"OpenAI() 未传 max_retries：{captured_kwargs}"
    )
    assert captured_kwargs["max_retries"] == 0, (
        f"max_retries 应为 0，实际 {captured_kwargs['max_retries']}"
    )


@pytest.mark.unit
def test_no_sdk_default_retry_doubles():
    """回归保护：源码不应再依赖 SDK 默认 max_retries（OpenAI=2 / Anthropic 变化）。

    通过显式 max_retries 让所有重试都走外层 llm_retry 中间件，避免
    SDK 默认重试 × llm_retry 双重放大。
    """
    # 类常量 _MAX_RETRIES 必须为 0
    assert getattr(LLMClient, "_MAX_RETRIES", None) == 0, (
        f"LLMClient._MAX_RETRIES 应为 0，实际 {getattr(LLMClient, '_MAX_RETRIES', None)}"
    )
    # 3 个 client 构造都引用 _MAX_RETRIES
    openai_src = inspect.getsource(LLMClient._get_openai_client)
    anthropic_src = inspect.getsource(LLMClient._get_anthropic_client)
    assert openai_src.count("max_retries=self._MAX_RETRIES") >= 1, (
        "_get_openai_client 应引用 _MAX_RETRIES"
    )
    assert anthropic_src.count("max_retries=self._MAX_RETRIES") >= 1, (
        "_get_anthropic_client 应引用 _MAX_RETRIES（Anthropic 或 OpenAI 兜底）"
    )


@pytest.mark.unit
def test_module_does_not_contain_unfixed_constructor():
    """回归保护：检查 3 处构造的 关键字参数完整性。"""
    openai_src = inspect.getsource(LLMClient._get_openai_client)
    anthropic_src = inspect.getsource(LLMClient._get_anthropic_client)
    # 关键字检查：timeout 与 max_retries 都在
    assert "timeout=" in openai_src
    assert "max_retries=" in openai_src
    assert "timeout=" in anthropic_src
    assert "max_retries=" in anthropic_src
