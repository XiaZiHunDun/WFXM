"""Sprint 8 audit fix: SEC-5 — wechat_ilink 出口未调 PII 脱敏

Sprint 8 SEC-5：`wechat_ilink.format_message` / `send` / `send_wechat_direct`
三个出站函数都没调 `scrub_outbound_text`。Sprint 7 在 `pii_scrub.py` 增强
5 类规则（银行卡 / API 密钥 / JWT / 私网 IP）但主路径没消费。

修复点：format_message 出口前 scrub — 一处覆盖 send / send_wechat_direct
两条主路径。
"""

from __future__ import annotations

from butler.gateway.platforms.wechat_ilink import WeChatAdapter
from butler.gateway.platforms.base import PlatformConfig


def _make_adapter() -> WeChatAdapter:
    return WeChatAdapter(
        PlatformConfig(
            token="dummy",
            extra={"account_id": "test"},
        )
    )


def test_format_message_scrubs_phone_number():
    """format_message 应在 normalize 前 scrub 手机号。"""
    adapter = _make_adapter()
    text = "联系 13800138000 处理。"

    out = adapter.format_message(text)

    assert "13800138000" not in out
    assert "[手机号已脱敏]" in out


def test_format_message_scrubs_bank_card_with_luhn():
    """银行卡号（Luhn 合法）应被脱敏。"""
    adapter = _make_adapter()
    # 4111111111111111 is Luhn-valid
    text = "支付卡号 4111111111111111 已收到。"

    out = adapter.format_message(text)

    assert "4111111111111111" not in out
    assert "[银行卡号已脱敏]" in out


def test_format_message_scrubs_api_key():
    """sk- 开头 API key 应被脱敏。"""
    adapter = _make_adapter()
    text = "我的 key 是 sk-proj1234567890abcdefABCDEF。"

    out = adapter.format_message(text)

    assert "sk-proj1234567890abcdefABCDEF" not in out
    assert "[API密钥已脱敏]" in out


def test_format_message_preserves_normal_text():
    """正常文本不应被误伤。"""
    adapter = _make_adapter()
    text = "今天的会议记录已上传，请查收。"

    out = adapter.format_message(text)

    assert out.strip() != ""
    assert "已脱敏" not in out
