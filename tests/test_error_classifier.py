"""butler.core.error_classifier 模块的综合测试。

覆盖范围：
1. FailoverReason 枚举 — 所有变体均存在
2. ClassifiedError 数据类 — 构造、字段、默认值
3. classify_api_error() — HTTP 状态码驱动、消息模式驱动、传输层启发式
4. is_retryable() — 返回 should_retry 标志
5. is_local_processing_error() — 识别本地处理错误，排除 HTTP 错误
6. 提供者特定模式匹配
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from butler.core.error_classifier import (
    ClassifiedError,
    FailoverReason,
    classify_api_error,
    is_local_processing_error,
    is_retryable,
)


# ═══════════════════════════════════════════════════════════════════════
# 辅助：轻量级模拟异常
# ═══════════════════════════════════════════════════════════════════════


class MockError(Exception):
    """可附加任意属性的通用模拟异常。"""

    def __init__(self, message: str = "", **attrs):
        super().__init__(message)
        for k, v in attrs.items():
            setattr(self, k, v)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def classified_rate_limit():
    """预分类为 rate_limit 的 ClassifiedError。"""
    return ClassifiedError(
        reason=FailoverReason.rate_limit,
        message="rate limit exceeded",
        should_retry=True,
        http_status=429,
    )


@pytest.fixture
def classified_auth():
    """预分类为 auth 的 ClassifiedError。"""
    return ClassifiedError(
        reason=FailoverReason.auth,
        message="unauthorized",
        should_retry=False,
        should_rotate_credential=True,
        http_status=401,
    )


# ═══════════════════════════════════════════════════════════════════════
# 1. FailoverReason 枚举
# ═══════════════════════════════════════════════════════════════════════


class TestFailoverReason:
    """FailoverReason 枚举的全部变体验证。"""

    def test_all_variants_exist(self):
        """所有预期的枚举变体均已定义。"""
        expected = {
            "auth",
            "auth_permanent",
            "billing",
            "rate_limit",
            "upstream_rate_limit",
            "overloaded",
            "server_error",
            "timeout",
            "context_overflow",
            "payload_too_large",
            "model_not_found",
            "provider_policy_blocked",
            "content_policy_blocked",
            "format_error",
            "ssl_cert_verification",
            "image_too_large",
            "unknown",
        }
        actual = {m.name for m in FailoverReason}
        assert actual == expected, f"枚举变体不匹配。缺失: {expected - actual}, 多余: {actual - expected}"

    @pytest.mark.parametrize("member", list(FailoverReason))
    def test_member_is_str(self, member):
        """每个枚举成员都是 str 子类，可直接字符串比较。"""
        assert isinstance(member, str)
        assert member == member.value

    def test_reason_values_are_unique(self):
        """所有 value 字符串唯一。"""
        values = [m.value for m in FailoverReason]
        assert len(values) == len(set(values)), "存在重复的 value"


# ═══════════════════════════════════════════════════════════════════════
# 2. ClassifiedError 数据类
# ═══════════════════════════════════════════════════════════════════════


class TestClassifiedError:
    """ClassifiedError 数据类的构造与默认值。"""

    def test_construction_with_reason_only(self):
        """仅提供 reason 构造，其余字段使用默认值。"""
        err = ClassifiedError(reason=FailoverReason.unknown)
        assert err.reason == FailoverReason.unknown
        assert err.message == ""
        assert err.should_retry is False
        assert err.should_rotate_credential is False
        assert err.should_fallback_model is False
        assert err.should_compress is False
        assert err.http_status is None
        assert err.provider_hint is None
        assert err.extra == {}

    def test_construction_with_all_fields(self):
        """提供全部字段构造。"""
        err = ClassifiedError(
            reason=FailoverReason.rate_limit,
            message="too many requests",
            should_retry=True,
            should_rotate_credential=False,
            should_fallback_model=True,
            should_compress=False,
            http_status=429,
            provider_hint="openrouter",
            extra={"retry_after": 30},
        )
        assert err.reason == FailoverReason.rate_limit
        assert err.message == "too many requests"
        assert err.should_retry is True
        assert err.should_rotate_credential is False
        assert err.should_fallback_model is True
        assert err.should_compress is False
        assert err.http_status == 429
        assert err.provider_hint == "openrouter"
        assert err.extra == {"retry_after": 30}

    def test_default_extra_is_independent(self):
        """两个实例的 extra 字段互不影响。"""
        a = ClassifiedError(reason=FailoverReason.unknown)
        b = ClassifiedError(reason=FailoverReason.unknown)
        a.extra["key"] = "value"
        assert b.extra == {}, "默认值不应共享同一 dict 引用"


# ═══════════════════════════════════════════════════════════════════════
# 3. classify_api_error() — HTTP 状态码驱动
# ═══════════════════════════════════════════════════════════════════════


class TestClassifyHttpStatus:
    """基于 HTTP 状态码的分类测试。"""

    def test_429_rate_limit(self):
        """429 → rate_limit，应重试。"""
        err = MockError("Too many requests", status_code=429)
        result = classify_api_error(err, http_status=429)
        assert result.reason == FailoverReason.rate_limit
        assert result.should_retry is True
        assert result.http_status == 429

    def test_429_overloaded_via_message(self):
        """429 且消息含 'overloaded' → overloaded。"""
        err = MockError("Service is temporarily overloaded", status_code=429)
        result = classify_api_error(err, http_status=429)
        assert result.reason == FailoverReason.overloaded
        assert result.should_retry is True

    def test_429_upstream_rate_limit(self):
        """429 + openrouter + provider returned error → upstream_rate_limit。"""
        err = MockError(
            "Provider returned error: upstream rate limited",
            status_code=429,
            body={"error": {"message": "Provider returned error", "metadata": {"upstream": "anthropic"}}},
        )
        result = classify_api_error(err, http_status=429, provider="openrouter")
        assert result.reason == FailoverReason.upstream_rate_limit
        assert result.should_retry is True
        assert result.should_fallback_model is True

    def test_401_auth(self):
        """401 → auth（非永久性），应轮换凭据。"""
        err = MockError("Unauthorized", status_code=401)
        result = classify_api_error(err, http_status=401)
        assert result.reason == FailoverReason.auth
        assert result.should_retry is False
        assert result.should_rotate_credential is True

    def test_401_auth_permanent(self):
        """401 + 'expired' 关键词 → auth_permanent。"""
        err = MockError("API key has expired", status_code=401)
        result = classify_api_error(err, http_status=401)
        assert result.reason == FailoverReason.auth_permanent
        assert result.should_retry is False
        assert result.should_rotate_credential is True

    def test_407_auth(self):
        """407 → auth。"""
        err = MockError("Proxy Authentication Required", status_code=407)
        result = classify_api_error(err, http_status=407)
        assert result.reason == FailoverReason.auth

    def test_403_forbidden_as_auth(self):
        """403 → auth（未触发 billing 模式时）。"""
        err = MockError("Forbidden", status_code=403)
        result = classify_api_error(err, http_status=403)
        assert result.reason == FailoverReason.auth
        assert result.should_retry is False
        assert result.should_fallback_model is True

    def test_403_billing(self):
        """403 + billing 关键词 → billing。"""
        err = MockError("Insufficient credits", status_code=403)
        result = classify_api_error(err, http_status=403)
        assert result.reason == FailoverReason.billing
        assert result.should_retry is False

    def test_402_billing(self):
        """402 → billing。"""
        err = MockError("Payment Required", status_code=402)
        result = classify_api_error(err, http_status=402)
        assert result.reason == FailoverReason.billing
        assert result.should_retry is False
        assert result.should_fallback_model is True

    def test_500_server_error(self):
        """500 → server_error，应重试。"""
        err = MockError("Internal Server Error", status_code=500)
        result = classify_api_error(err, http_status=500)
        assert result.reason == FailoverReason.server_error
        assert result.should_retry is True

    def test_500_context_overflow(self):
        """500 + context overflow 关键词 → context_overflow（优先匹配）。"""
        err = MockError("context length exceeded", status_code=500)
        result = classify_api_error(err, http_status=500)
        assert result.reason == FailoverReason.context_overflow
        assert result.should_compress is True

    def test_502_server_error(self):
        """502 → server_error。"""
        err = MockError("Bad Gateway", status_code=502)
        result = classify_api_error(err, http_status=502)
        assert result.reason == FailoverReason.server_error
        assert result.should_retry is True

    def test_503_overloaded(self):
        """503 → overloaded，应重试。"""
        err = MockError("Service Unavailable", status_code=503)
        result = classify_api_error(err, http_status=503)
        assert result.reason == FailoverReason.overloaded
        assert result.should_retry is True

    def test_529_overloaded(self):
        """529 → overloaded。"""
        err = MockError("Too Many Requests", status_code=529)
        result = classify_api_error(err, http_status=529)
        assert result.reason == FailoverReason.overloaded
        assert result.should_retry is True

    def test_400_context_overflow(self):
        """400 + 'context length' → context_overflow。"""
        err = MockError("context length exceeded", status_code=400)
        result = classify_api_error(err, http_status=400)
        assert result.reason == FailoverReason.context_overflow
        assert result.should_retry is True
        assert result.should_compress is True

    def test_400_image_too_large(self):
        """400 + 'image too large' → image_too_large。"""
        err = MockError("image too large for model", status_code=400)
        result = classify_api_error(err, http_status=400)
        assert result.reason == FailoverReason.image_too_large
        assert result.should_compress is True

    def test_400_format_error(self):
        """400 + 'invalid parameter' → format_error。"""
        err = MockError("invalid parameter supplied", status_code=400)
        result = classify_api_error(err, http_status=400)
        assert result.reason == FailoverReason.format_error
        assert result.should_retry is False

    def test_400_model_not_found(self):
        """400 + 'model not found' → model_not_found。"""
        err = MockError("model not found: foo", status_code=400)
        result = classify_api_error(err, http_status=400)
        assert result.reason == FailoverReason.model_not_found
        assert result.should_retry is False
        assert result.should_fallback_model is True

    def test_400_fallback_format_error(self):
        """400 不含任何特定模式 → format_error（兜底）。"""
        err = MockError("some random bad request", status_code=400)
        result = classify_api_error(err, http_status=400)
        assert result.reason == FailoverReason.format_error
        assert result.should_retry is False

    def test_413_payload_too_large(self):
        """413 → payload_too_large，应压缩。"""
        err = MockError("Request Entity Too Large", status_code=413)
        result = classify_api_error(err, http_status=413)
        assert result.reason == FailoverReason.payload_too_large
        assert result.should_retry is True
        assert result.should_compress is True

    def test_404_model_not_found(self):
        """404 + 'model not found' → model_not_found。"""
        err = MockError("model not found: gpt-4-unknown", status_code=404)
        result = classify_api_error(err, http_status=404)
        assert result.reason == FailoverReason.model_not_found
        assert result.should_retry is False
        assert result.should_fallback_model is True

    def test_404_provider_policy_blocked(self):
        """404 + 'no endpoints available matching your guardrail' → provider_policy_blocked。"""
        err = MockError("no endpoints available matching your guardrail", status_code=404)
        result = classify_api_error(err, http_status=404)
        assert result.reason == FailoverReason.provider_policy_blocked

    def test_404_billing(self):
        """404 + billing 关键词 → billing。"""
        err = MockError("insufficient credits for this model", status_code=404)
        result = classify_api_error(err, http_status=404)
        assert result.reason == FailoverReason.billing

    def test_404_unknown_fallback(self):
        """404 不含特定模式 → unknown（兜底）。"""
        err = MockError("some random 404", status_code=404)
        result = classify_api_error(err, http_status=404)
        assert result.reason == FailoverReason.unknown
        assert result.should_retry is True

    def test_408_timeout(self):
        """408 → timeout，应重试。"""
        err = MockError("Request Timeout", status_code=408)
        result = classify_api_error(err, http_status=408)
        assert result.reason == FailoverReason.timeout
        assert result.should_retry is True

    def test_408_via_status_attribute(self):
        """408 通过 .status_code 属性自动提取。"""
        err = MockError("timed out", status_code=408)
        result = classify_api_error(err)
        assert result.reason == FailoverReason.timeout
        assert result.should_retry is True


# ═══════════════════════════════════════════════════════════════════════
# 4. classify_api_error() — 消息模式驱动（无状态码）
# ═══════════════════════════════════════════════════════════════════════


class TestClassifyMessagePatterns:
    """基于错误消息文本模式的分类测试（无 HTTP 状态码）。"""

    def test_rate_limit_via_message(self):
        """消息含 'rate limit' → rate_limit。"""
        err = MockError("We hit a rate limit, please slow down")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.rate_limit
        assert result.should_retry is True
        assert result.should_fallback_model is True

    def test_overloaded_via_message(self):
        """消息含 'overloaded' → overloaded。"""
        err = MockError("Server is overloaded, try again later")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.overloaded
        assert result.should_retry is True

    def test_billing_via_message(self):
        """消息含 'insufficient credits' → billing。"""
        err = MockError("Your account has insufficient credits")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.billing
        assert result.should_retry is False
        assert result.should_fallback_model is True

    def test_context_overflow_via_message(self):
        """消息含 'context length' → context_overflow。"""
        err = MockError("context length exceeded the maximum")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.context_overflow
        assert result.should_retry is True
        assert result.should_compress is True

    def test_payload_too_large_via_message(self):
        """消息含 'payload too large' → payload_too_large。"""
        err = MockError("payload too large for the server")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.payload_too_large
        assert result.should_compress is True

    def test_model_not_found_via_message(self):
        """消息含 'is not a valid model' → model_not_found。"""
        err = MockError("'foobar' is not a valid model")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.model_not_found
        assert result.should_retry is False
        assert result.should_fallback_model is True

    def test_auth_via_message(self):
        """消息含 'invalid api key' → auth。"""
        err = MockError("invalid api key provided")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.auth
        assert result.should_retry is True
        assert result.should_rotate_credential is True

    def test_format_error_via_message(self):
        """消息含 'unknown parameter' → format_error。"""
        err = MockError("unknown parameter 'foo' in request")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.format_error
        assert result.should_retry is False

    def test_content_policy_blocked_via_message(self):
        """消息含 'violates our usage policies' → content_policy_blocked。"""
        err = MockError("Your request violates our usage policies")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.content_policy_blocked
        assert result.should_retry is False
        assert result.should_fallback_model is True

    def test_provider_policy_blocked_via_message(self):
        """消息含 'policy restricted' → provider_policy_blocked。"""
        err = MockError("This model is policy restricted for your account")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.provider_policy_blocked

    def test_timeout_via_message(self):
        """消息含 'timed out' → timeout。"""
        err = MockError("Connection timed out while waiting for response")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.timeout
        assert result.should_retry is True

    def test_deadline_exceeded_via_message(self):
        """消息含 'deadline exceeded' → timeout。"""
        err = MockError("Deadline exceeded before response arrived")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.timeout

    def test_ssl_cert_verification_via_message(self):
        """消息含 'certificate verify failed' → ssl_cert_verification。"""
        err = MockError("SSL: certificate verify failed")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.ssl_cert_verification
        assert result.should_retry is False

    def test_unknown_fallback(self):
        """无法匹配任何模式 → unknown。"""
        err = MockError("completely unrecognizable error message xyzzy")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.unknown
        assert result.should_retry is True


# ═══════════════════════════════════════════════════════════════════════
# 5. classify_api_error() — 提供者特定模式
# ═══════════════════════════════════════════════════════════════════════


class TestProviderSpecificPatterns:
    """提供者特定错误消息的分类。"""

    @pytest.mark.parametrize("keyword", [
        "rate limit",
        "rate_limit",
        "too many requests",
        "throttled",
        "resource_exhausted",
    ])
    def test_various_rate_limit_texts(self, keyword):
        """多种限流表述均能正确识别。"""
        err = MockError(f"Error: {keyword}")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.rate_limit

    @pytest.mark.parametrize("keyword", [
        "overloaded",
        "temporarily overloaded",
        "at capacity",
        "over capacity",
    ])
    def test_various_overloaded_texts(self, keyword):
        """多种过载表述均能正确识别。"""
        err = MockError(f"Error: service is {keyword}")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.overloaded

    @pytest.mark.parametrize("keyword", [
        "insufficient credits",
        "insufficient_quota",
        "out of funds",
        "payment required",
        "spending limit",
    ])
    def test_various_billing_texts(self, keyword):
        """多种计费错误表述均能正确识别。"""
        err = MockError(f"Billing error: {keyword}")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.billing

    @pytest.mark.parametrize("keyword", [
        "context length",
        "context window",
        "token limit",
        "maximum context",
        "上下文长度",
    ])
    def test_various_context_overflow_texts(self, keyword):
        """多种上下文溢出表述均能正确识别。"""
        err = MockError(f"Error: {keyword} exceeded")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.context_overflow

    @pytest.mark.parametrize("keyword", [
        "invalid api key",
        "unauthorized",
        "forbidden",
        "token expired",
        "access denied",
    ])
    def test_various_auth_texts(self, keyword):
        """多种认证错误表述均能正确识别。"""
        err = MockError(f"Auth error: {keyword}")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.auth

    @pytest.mark.parametrize("keyword", [
        "certificate verify failed",
        "self-signed certificate",
        "certificate has expired",
        "hostname mismatch",
    ])
    def test_various_ssl_texts(self, keyword):
        """多种 SSL 错误表述均能正确识别。"""
        err = MockError(f"TLS error: {keyword}")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.ssl_cert_verification


# ═══════════════════════════════════════════════════════════════════════
# 6. classify_api_error() — 错误码分类
# ═══════════════════════════════════════════════════════════════════════


class TestClassifyErrorCode:
    """基于 provider 结构化错误码的分类。"""

    def test_invalid_request_error_code(self):
        """error_code = 'invalid_request_error' → format_error。"""
        err = MockError(
            "Bad request",
            body={"error": {"code": "invalid_request_error", "message": "bad"}},
        )
        result = classify_api_error(err)
        assert result.reason == FailoverReason.format_error
        assert result.should_retry is False

    def test_insufficient_quota_code(self):
        """error_code = 'insufficient_quota' → billing。"""
        err = MockError(
            "Quota exceeded",
            body={"error": {"code": "insufficient_quota", "message": "no quota"}},
        )
        result = classify_api_error(err)
        assert result.reason == FailoverReason.billing
        assert result.should_fallback_model is True

    def test_content_policy_violation_code(self):
        """error_code = 'content_policy_violation' → content_policy_blocked。"""
        err = MockError(
            "Content flagged",
            body={"error": {"code": "content_policy_violation", "message": "blocked"}},
        )
        result = classify_api_error(err)
        assert result.reason == FailoverReason.content_policy_blocked
        assert result.should_fallback_model is True


# ═══════════════════════════════════════════════════════════════════════
# 7. is_retryable()
# ═══════════════════════════════════════════════════════════════════════


class TestIsRetryable:
    """is_retryable() 应返回 classified.should_retry。"""

    def test_returns_true_when_should_retry_is_true(self, classified_rate_limit):
        """should_retry=True 时返回 True。"""
        assert is_retryable(classified_rate_limit) is True

    def test_returns_false_when_should_retry_is_false(self, classified_auth):
        """should_retry=False 时返回 False。"""
        assert is_retryable(classified_auth) is False

    def test_independent_of_reason(self):
        """返回值仅取决于 should_retry，与 reason 无关。"""
        for reason in FailoverReason:
            err_true = ClassifiedError(reason=reason, should_retry=True)
            err_false = ClassifiedError(reason=reason, should_retry=False)
            assert is_retryable(err_true) is True
            assert is_retryable(err_false) is False


# ═══════════════════════════════════════════════════════════════════════
# 8. is_local_processing_error()
# ═══════════════════════════════════════════════════════════════════════


class TestIsLocalProcessingError:
    """is_local_processing_error() 的识别逻辑。"""

    def test_typeerror_is_local(self):
        """TypeError（如 JSON 序列化失败）应识别为本地错误。"""
        err = TypeError("object of type 'NoneType' is not JSON serializable")
        assert is_local_processing_error(err) is True

    def test_attributeerror_is_local(self):
        """AttributeError（消息含 'attributeerror:' 前缀）应识别为本地错误。"""
        err = AttributeError("attributeerror: 'NoneType' object has no attribute 'foo'")
        assert is_local_processing_error(err) is True

    def test_valueerror_is_local(self):
        """ValueError（消息含 'valueerror:' 前缀）应识别为本地错误。"""
        err = ValueError("valueerror: invalid literal for int()")
        assert is_local_processing_error(err) is True

    def test_keyerror_is_local(self):
        """KeyError（消息含 'keyerror:' 前缀）应识别为本地错误。"""
        err = KeyError("keyerror: 'missing_key'")
        assert is_local_processing_error(err) is True

    def test_http_status_error_is_not_local(self):
        """带有 HTTP 状态码的错误不应识别为本地错误。"""
        err = MockError("object of type 'NoneType' is not JSON serializable", status_code=500)
        assert is_local_processing_error(err) is False

    def test_transport_error_is_not_local(self):
        """传输层错误（TimeoutError）不应识别为本地错误。"""
        err = TimeoutError("Connection timed out")
        assert is_local_processing_error(err) is False

    def test_connection_error_is_not_local(self):
        """ConnectionError 不应识别为本地错误。"""
        err = ConnectionError("Connection refused")
        assert is_local_processing_error(err) is False

    def test_ssl_error_is_not_local(self):
        """SSL 证书错误即使消息匹配本地模式，也不应识别为本地错误。"""
        err = MockError("SSL: certificate verify failed")
        assert is_local_processing_error(err) is False

    def test_recursion_error_is_local(self):
        """RecursionError（消息含 'recursionerror'）应识别为本地错误。"""
        err = RecursionError("recursionerror maximum recursion depth exceeded")
        assert is_local_processing_error(err) is True

    def test_runtime_error_is_local(self):
        """RuntimeError（消息含 'runtimeerror:' 前缀）应识别为本地错误。"""
        err = RuntimeError("runtimeerror: maximum recursion depth exceeded")
        assert is_local_processing_error(err) is True

    def test_no_matching_pattern_is_not_local(self):
        """消息不匹配任何本地模式时返回 False。"""
        err = Exception("just a random error")
        assert is_local_processing_error(err) is False

    def test_oserror_is_not_local(self):
        """OSError 不应识别为本地错误。"""
        err = OSError("disk full")
        assert is_local_processing_error(err) is False


# ═══════════════════════════════════════════════════════════════════════
# 9. 边界情况与集成测试
# ═══════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """边界情况与集成场景。"""

    def test_generic_valueerror_returns_unknown(self):
        """普通 ValueError（非本地处理错误场景）→ unknown。"""
        err = ValueError("some generic value error")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.unknown
        assert result.should_retry is True

    def test_none_message_handled(self):
        """异常字符串表示为空时不应崩溃。"""
        err = MockError("")
        result = classify_api_error(err)
        assert isinstance(result, ClassifiedError)
        assert result.reason == FailoverReason.unknown

    def test_provider_hint_preserved(self):
        """provider 参数应被保留在 provider_hint 中。"""
        err = MockError("test")
        result = classify_api_error(err, provider="anthropic")
        assert result.provider_hint == "anthropic"

    def test_http_status_override(self):
        """显式 http_status 参数优先于异常属性。"""
        err = MockError("test", status_code=500)
        result = classify_api_error(err, http_status=401)
        assert result.reason == FailoverReason.auth

    def test_error_body_extraction_from_response_attr(self):
        """从 .response 属性提取 body。"""
        err = MockError(
            "Error",
            response={"error": {"message": "context length exceeded"}},
        )
        result = classify_api_error(err)
        assert result.reason == FailoverReason.context_overflow

    def test_error_body_extraction_from_error_attr(self):
        """从 .error 属性提取 body。"""
        err = MockError(
            "Error",
            error={"error": {"message": "invalid api key"}},
        )
        result = classify_api_error(err)
        assert result.reason == FailoverReason.auth

    def test_message_composition_includes_body_message(self):
        """合成的错误文本应包含 body 中的消息。"""
        err = MockError(
            "ConnectionError",
            body={"error": {"message": "rate limit exceeded"}},
        )
        result = classify_api_error(err)
        assert result.reason == FailoverReason.rate_limit

    def test_both_status_and_message_pattern(self):
        """状态码与消息模式同时存在时，context_overflow 模式在 400 分支内优先匹配。"""
        err = MockError("context_overflow", status_code=400)
        result = classify_api_error(err, http_status=400)
        assert result.reason == FailoverReason.context_overflow

    def test_http_status_via_code_attr(self):
        """通过 .code 属性提取状态码（模拟 aiohttp）。"""
        err = MockError("Service Unavailable", code=503)
        result = classify_api_error(err)
        assert result.reason == FailoverReason.overloaded

    def test_http_status_via_http_status_attr(self):
        """通过 .http_status 属性提取状态码。"""
        err = MockError("Internal Server Error", http_status=500)
        result = classify_api_error(err)
        assert result.reason == FailoverReason.server_error

    def test_http_status_via_status_attr(self):
        """通过 .status 属性提取状态码。"""
        err = MockError("Unauthorized", status=401)
        result = classify_api_error(err)
        assert result.reason == FailoverReason.auth

    def test_status_code_extraction_via_regex(self):
        """当异常无显式属性时，正则匹配错误消息中的状态码。"""
        err = MockError("HTTP 429 Too Many Requests")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.rate_limit

    def test_content_policy_blocked_high_priority(self):
        """内容政策拦截具有最高优先级（在状态码检查之前）。"""
        err = MockError("Your request was flagged by our safety system", status_code=400)
        result = classify_api_error(err, http_status=400)
        assert result.reason == FailoverReason.content_policy_blocked
        assert result.should_retry is False
        assert result.should_fallback_model is True

    def test_classified_error_preserves_http_status(self):
        """结果中的 http_status 字段应反映输入。"""
        err = MockError("error", status_code=500)
        result = classify_api_error(err, http_status=500)
        assert result.http_status == 500

    def test_image_too_large_via_message(self):
        """消息含 'image too large' → image_too_large（无状态码时）。"""
        err = MockError("image too large for processing")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.image_too_large
        assert result.should_compress is True

    def test_payload_too_large_via_413_pattern_in_message(self):
        """消息含 'error code: 413' → payload_too_large。"""
        err = MockError("Error code: 413 - request entity too large")
        result = classify_api_error(err)
        assert result.reason == FailoverReason.payload_too_large