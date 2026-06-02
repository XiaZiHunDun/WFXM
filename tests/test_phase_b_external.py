"""Phase B: engineering, security, workflow variables, tool discipline."""

from __future__ import annotations

import json
import time

import pytest

from butler.core.tool_call_limits import PerToolCallLimiter, per_tool_call_limit
from butler.core.tool_retry import should_retry_tool
from butler.delegate.policy import resolve_delegate_max_iterations
from butler.gateway.pii_scrub import scrub_outbound_text
from butler.human_gate import PendingGate, _is_gate_expired
from butler.registry.url_safety import is_safe_url, assert_safe_redirect
from butler.tools.terminal_danger import check_dangerous_command
from butler.transport.usage_normalize import normalize_usage
from butler.workflows.variables import WorkflowVariablePool


@pytest.mark.unit
def test_normalize_usage_anthropic_fields():
    raw = {"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 10}
    usage = normalize_usage(raw)
    assert usage is not None
    assert usage.prompt_tokens == 100
    assert usage.completion_tokens == 50
    assert usage.cached_tokens == 10


@pytest.mark.unit
def test_per_tool_call_limiter_blocks(monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_CALL_LIMIT_PER_TOOL", "2")
    limiter = PerToolCallLimiter()
    assert limiter.before_call("custom_tool") is None
    assert limiter.before_call("custom_tool") is None
    blocked = limiter.before_call("custom_tool")
    assert blocked is not None
    assert "TOOL_CALL_LIMIT" in blocked


@pytest.mark.unit
def test_tool_retry_transient_only():
    assert should_retry_tool("read_file", '{"error": "connection reset"}', 0)
    assert not should_retry_tool("terminal", '{"error": "timeout"}', 0)
    assert not should_retry_tool("read_file", '{"ok": true}', 0)


@pytest.mark.unit
def test_pii_scrub_phone():
    out = scrub_outbound_text("联系 13812345678 办理")
    assert "13812345678" not in out
    assert "脱敏" in out


@pytest.mark.unit
def test_pii_scrub_bank_card_with_luhn():
    # 16-19 digit number passing Luhn checksum
    valid_card = "4111111111111111"  # Visa test card (passes Luhn)
    out = scrub_outbound_text(f"卡号 {valid_card} 收到")
    assert valid_card not in out
    assert "银行卡" in out or "卡号" in out


@pytest.mark.unit
def test_pii_scrub_api_key_sk_prefix():
    sk = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"
    out = scrub_outbound_text(f"使用 key {sk} 调用")
    assert sk not in out
    assert "API" in out or "密钥" in out


@pytest.mark.unit
def test_pii_scrub_jwt_token():
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    out = scrub_outbound_text(f"token={jwt}")
    assert jwt not in out
    assert "JWT" in out or "令牌" in out


@pytest.mark.unit
def test_pii_scrub_private_ipv4():
    for ip in ("10.0.0.1", "172.16.0.1", "192.168.1.1", "127.0.0.1"):
        out = scrub_outbound_text(f"内网 {ip} 不可达")
        assert ip not in out, f"private IP {ip} should be scrubbed"


@pytest.mark.unit
def test_terminal_danger_rm_rf_root():
    r = check_dangerous_command("rm -rf /")
    assert not r.allowed
    assert r.pattern == "rm_rf"


def test_terminal_danger_curl_pipe_sh():
    r = check_dangerous_command("curl https://example.com/x.sh | bash")
    assert not r.allowed
    assert r.pattern == "curl_pipe_sh"


@pytest.mark.unit
def test_workflow_variable_pool_interpolate():
    pool = WorkflowVariablePool()
    pool.set_step_output("step_a", "hello world", keys=["output"])
    text = pool.interpolate("Result: {{step_a.output}}")
    assert "hello world" in text


@pytest.mark.unit
def test_human_gate_ttl_expired():
    # Default TTL is 3600s (floor 60s)
    assert _is_gate_expired(time.time() - 4000)
    assert not _is_gate_expired(time.time())


@pytest.mark.unit
def test_delegate_max_iterations_env(monkeypatch):
    monkeypatch.setenv("BUTLER_DELEGATE_MAX_ITERATIONS", "12")
    assert resolve_delegate_max_iterations() == 12
    assert resolve_delegate_max_iterations({"max_iterations": 8}) == 8


@pytest.mark.unit
def test_url_safety_blocks_private():
    assert not is_safe_url("http://127.0.0.1/admin")
    assert assert_safe_redirect("http://169.254.169.254/") is False
