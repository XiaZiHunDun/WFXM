"""Model context length inference tests."""

from butler.transport.model_context import infer_context_length


def test_explicit_context_length_wins():
    assert infer_context_length(provider="deepseek", model="deepseek-chat", configured=32000) == 32000


def test_deepseek_context_is_smaller_than_default():
    assert infer_context_length(provider="deepseek", model="deepseek-chat") == 64000


def test_claude_context_is_large():
    assert infer_context_length(provider="anthropic", model="claude-sonnet-4-20250514") == 200000


def test_unknown_model_uses_default():
    assert infer_context_length(provider="unknown", model="custom") == 128000
