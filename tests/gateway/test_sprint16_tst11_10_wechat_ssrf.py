"""Sprint 16 TST-11-10: butler/registry/url_safety.py + wechat_ilink._download_remote_media SSRF 覆盖.

bug: audit 标记 0 e2e with redirector/IPv6/0.0.0.0:
  - butler/registry/url_safety.py is_safe_url/assert_safe_redirect/safe_registry_get
  - butler/gateway/platforms/wechat_ilink.py:1720 _download_remote_media
  - 已存在 1 个最小 unit test (test_phase_b_external::test_url_safety_blocks_private),
    但缺: 0.0.0.0 / IPv6 ::1 / 169.254 全段 / metadata.google.internal / .local /
    .internal / ftp/file scheme / DNS 解析失败 / allowed_hosts bypass /
    safe_registry_get redirect 行为 / _download_remote_media 集成

修复: 补全 SSRF 覆盖, 重点是常见绕过向量 (0.0.0.0, IPv6, metadata)。

注意: wechat_ilink._download_remote_media 使用 ``butler.registry.url_safety.is_safe_url``；
集成测试 patch ``butler.registry.url_safety.is_safe_url``。
"""

from __future__ import annotations

import ipaddress
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from butler.registry import url_safety as butler_url_safety
from butler.registry.url_safety import (
    assert_safe_redirect,
    is_safe_url,
    safe_registry_get,
)


# ── 公共 fixture: 清空 allowed_hosts, mock DNS for public host tests ──


@pytest.fixture(autouse=True)
def _clear_allowed_hosts(monkeypatch):
    """默认情况下, BUTLER_REGISTRY_ALLOWED_HOSTS 为空, 严格 SSRF 模式。"""
    monkeypatch.delenv("BUTLER_REGISTRY_ALLOWED_HOSTS", raising=False)


# ── is_safe_url 阻断 ──


class TestIsSafeUrlBlocks:
    @pytest.mark.parametrize("host", [
        "http://10.0.0.1/admin",
        "http://10.255.255.254/admin",
        "http://172.16.0.1/admin",
        "http://172.31.255.254/admin",
        "http://192.168.0.1/admin",
        "http://192.168.1.100/admin",
    ])
    def test_blocks_rfc1918_private(self, host):
        assert is_safe_url(host) is False, f"应阻断 RFC1918 私有 IP: {host}"

    @pytest.mark.parametrize("host", [
        "http://127.0.0.1/",
        "http://127.0.0.1:8080/admin",
        "http://127.255.255.254/",
    ])
    def test_blocks_loopback_v4(self, host):
        assert is_safe_url(host) is False, f"应阻断 IPv4 loopback: {host}"

    def test_blocks_zero_address(self):
        """0.0.0.0: Linux 解析为所有接口, 是经典 SSRF 绕过。
        _addr_blocked 用 is_reserved 判定, 应拦。"""
        assert is_safe_url("http://0.0.0.0/") is False, (
            "应阻断 0.0.0.0 (Linux 解析为所有接口, 易被 SSRF 利用)"
        )

    def test_blocks_zero_address_with_port(self):
        """0.0.0.0:6379 (Redis 经典 SSRF 目标)。"""
        assert is_safe_url("http://0.0.0.0:6379/") is False

    @pytest.mark.parametrize("host", [
        "http://169.254.169.254/latest/meta-data/",  # AWS metadata
        "http://169.254.169.254/computeMetadata/v1/",  # GCP metadata
        "http://169.254.170.2/",  # ECS task metadata
        "http://169.254.0.1/",  # link-local
    ])
    def test_blocks_link_local_169_254(self, host):
        assert is_safe_url(host) is False, f"应阻断 link-local: {host}"

    @pytest.mark.parametrize("host", [
        "http://[::1]/admin",
        "http://[::1]:8080/",
        "http://[::ffff:127.0.0.1]/",  # IPv4-mapped IPv6 loopback
    ])
    def test_blocks_ipv6_loopback(self, host):
        assert is_safe_url(host) is False, f"应阻断 IPv6 loopback: {host}"

    def test_blocks_ipv6_ula(self):
        """fc00::/7 (IPv6 ULA) — _PRIVATE_NETWORKS 含此段。"""
        assert is_safe_url("http://[fc00::1]/admin") is False

    def test_blocks_ipv6_link_local(self):
        """fe80::/10 link-local (经 is_link_local 判定)。"""
        assert is_safe_url("http://[fe80::1]/") is False, (
            "应阻断 IPv6 link-local fe80::/10"
        )

    @pytest.mark.parametrize("host", [
        "http://localhost/admin",
        "http://localhost:6379/",  # Redis
    ])
    def test_blocks_localhost_name(self, host):
        assert is_safe_url(host) is False

    @pytest.mark.parametrize("host", [
        "http://metadata.google.internal/",
        "http://metadata.google/",
    ])
    def test_blocks_gcp_metadata(self, host):
        assert is_safe_url(host) is False, f"应阻断 GCP metadata: {host}"

    @pytest.mark.parametrize("host", [
        "http://server.local/admin",
        "http://printer.local/",
        "http://api.internal/health",
    ])
    def test_blocks_local_internal_tld(self, host):
        assert is_safe_url(host) is False, f"应阻断 .local / .internal: {host}"

    @pytest.mark.parametrize("host", [
        "ftp://example.com/file",
        "file:///etc/passwd",
        "gopher://example.com:25/",
    ])
    def test_blocks_non_http_schemes(self, host):
        assert is_safe_url(host) is False, f"应阻断非 http(s) scheme: {host}"

    def test_blocks_empty_url(self):
        assert is_safe_url("") is False
        assert is_safe_url("   ") is False

    def test_blocks_url_with_no_host(self):
        assert is_safe_url("http:///path") is False

    def test_blocks_dns_resolution_failure(self):
        """getaddrinfo 失败 → 阻断。"""
        with patch.object(butler_url_safety.socket, "getaddrinfo", side_effect=OSError("no DNS")):
            assert is_safe_url("https://nonexistent.invalid/") is False

    def test_blocks_when_dns_resolves_to_private(self):
        """公网域名解析到私有 IP → 阻断。"""
        fake_info = [(2, 1, 6, "", ("192.168.1.1", 0))]
        with patch.object(butler_url_safety.socket, "getaddrinfo", return_value=fake_info):
            assert is_safe_url("http://attacker.example.com/") is False, (
                "域名解析到 192.168.1.1 → 应阻断"
            )

    def test_blocks_when_dns_resolves_to_loopback(self):
        """公网域名解析到 127.0.0.1 → 阻断。"""
        fake_info = [(2, 1, 6, "", ("127.0.0.1", 0))]
        with patch.object(butler_url_safety.socket, "getaddrinfo", return_value=fake_info):
            assert is_safe_url("http://attacker.example.com/") is False

    def test_blocks_when_dns_resolves_to_link_local(self):
        """公网域名解析到 169.254.169.254 → 阻断。"""
        fake_info = [(2, 1, 6, "", ("169.254.169.254", 0))]
        with patch.object(butler_url_safety.socket, "getaddrinfo", return_value=fake_info):
            assert is_safe_url("http://attacker.example.com/") is False

    def test_blocks_garbage_url(self):
        assert is_safe_url("not a url") is False


# ── is_safe_url 放行 ──


class TestIsSafeUrlAllows:
    def test_allows_public_ip_v4(self):
        """公网 IP (1.1.1.1, 8.8.8.8) → 放行。"""
        assert is_safe_url("http://1.1.1.1/") is True
        assert is_safe_url("http://8.8.8.8/") is True

    def test_allows_public_domain_example(self):
        """example.com → 放行。"""
        assert is_safe_url("https://example.com/") is True

    def test_allows_public_domain_via_mock_dns(self):
        """任意公网域名通过 mock DNS 放行。"""
        fake_info = [(2, 1, 6, "", ("93.184.216.34", 0))]  # example.com 真实 IP
        with patch.object(butler_url_safety.socket, "getaddrinfo", return_value=fake_info):
            assert is_safe_url("https://any-public-domain.example/") is True

    def test_allowed_hosts_bypass(self, monkeypatch):
        """BUTLER_REGISTRY_ALLOWED_HOSTS 列出的 host → 跳过 IP/域名所有检查。"""
        monkeypatch.setenv("BUTLER_REGISTRY_ALLOWED_HOSTS", "internal.corp,trusted.local")
        # 私有 IP 域名本应被拦, 但因为在 allowed 列表 → 直接放行
        assert is_safe_url("https://internal.corp/api") is True
        # trusted.local 也不走 .local 检查
        assert is_safe_url("https://trusted.local/admin") is True
        # 未列出的公网 host (mock DNS) 仍放行
        fake_info = [(2, 1, 6, "", ("93.184.216.34", 0))]
        with patch.object(butler_url_safety.socket, "getaddrinfo", return_value=fake_info):
            assert is_safe_url("http://attacker.example.com/") is True

    def test_allowed_hosts_empty_does_not_bypass(self, monkeypatch):
        """空字符串 env → 不 bypass。"""
        monkeypatch.setenv("BUTLER_REGISTRY_ALLOWED_HOSTS", "")
        assert is_safe_url("http://10.0.0.1/") is False

    def test_unlisted_host_still_validated(self, monkeypatch):
        """未在允许列表的 host → 仍走标准 SSRF 校验。"""
        monkeypatch.setenv("BUTLER_REGISTRY_ALLOWED_HOSTS", "internal.corp")
        # 私有 IP 不在 allowed → 仍被拦
        assert is_safe_url("http://10.0.0.1/") is False


# ── assert_safe_redirect ──


class TestAssertSafeRedirect:
    def test_blocks_private_ip_redirect(self):
        assert assert_safe_redirect("http://10.0.0.1/") is False

    def test_blocks_localhost_redirect(self):
        assert assert_safe_redirect("http://localhost/") is False

    def test_blocks_metadata_redirect(self):
        assert assert_safe_redirect("http://169.254.169.254/") is False

    def test_allows_public_ip_redirect(self):
        assert assert_safe_redirect("http://1.1.1.1/") is True

    def test_allows_public_domain_via_mock_dns(self):
        fake_info = [(2, 1, 6, "", ("93.184.216.34", 0))]
        with patch.object(butler_url_safety.socket, "getaddrinfo", return_value=fake_info):
            assert assert_safe_redirect("https://any-public.example/") is True


# ── safe_registry_get ──


class TestSafeRegistryGet:
    def test_blocks_unsafe_url_raises(self):
        """is_safe_url=False → raise ValueError, 不发请求。"""
        with patch("httpx.get") as mock_get:
            with pytest.raises(ValueError, match="unsafe registry url"):
                safe_registry_get("http://10.0.0.1/admin")
        mock_get.assert_not_called()

    def test_allows_safe_url_calls_with_no_redirects(self):
        """is_safe_url=True → httpx.get(url, follow_redirects=False, timeout=25.0)。"""
        mock_resp = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
        mock_resp.status_code = 200
        with patch("httpx.get", return_value=mock_resp) as mock_get:
            result = safe_registry_get("https://example.com/file.json")
        assert result is mock_resp
        call_kwargs = mock_get.call_args.kwargs
        assert call_kwargs["follow_redirects"] is False
        assert call_kwargs["timeout"] == 25.0

    def test_follows_one_safe_redirect(self):
        """301/302/303/307/308 + Location 指向 safe URL → 跟随一次。"""
        first_resp = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
        first_resp.status_code = 301
        first_resp.headers = {"location": "https://example.com/new"}
        second_resp = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
        second_resp.status_code = 200

        with patch("httpx.get") as mock_get:
            mock_get.side_effect = [first_resp, second_resp]
            result = safe_registry_get("https://example.com/old")
        assert result is second_resp
        assert mock_get.call_count == 2

    @pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
    def test_follows_all_redirect_codes(self, status):
        """所有 5 个 3xx 状态码都应触发 redirect 跟随。"""
        first_resp = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
        first_resp.status_code = status
        first_resp.headers = {"location": "https://example.com/dest"}
        second_resp = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
        second_resp.status_code = 200

        with patch("httpx.get") as mock_get:
            mock_get.side_effect = [first_resp, second_resp]
            result = safe_registry_get("https://example.com/src")
        assert result is second_resp
        assert mock_get.call_count == 2

    def test_blocks_redirect_to_unsafe_target(self):
        """301 → Location 指向 10.0.0.1 → 不跟随。"""
        first_resp = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
        first_resp.status_code = 302
        first_resp.headers = {"location": "http://10.0.0.1/admin"}

        with patch("httpx.get", return_value=first_resp) as mock_get:
            result = safe_registry_get("https://example.com/redirect")
        assert result is first_resp
        assert mock_get.call_count == 1, "unsafe redirect 不应被跟随"

    def test_redirect_without_location_header(self):
        """301 但无 Location header → 不跟随。"""
        first_resp = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
        first_resp.status_code = 301
        first_resp.headers = {}

        with patch("httpx.get", return_value=first_resp) as mock_get:
            result = safe_registry_get("https://example.com/")
        assert result is first_resp
        assert mock_get.call_count == 1

    def test_relative_redirect_resolved_against_base(self):
        """Location 是相对路径 → urljoin 解析。"""
        first_resp = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
        first_resp.status_code = 307
        first_resp.headers = {"location": "/v2/file.json"}
        second_resp = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
        second_resp.status_code = 200

        with patch("httpx.get") as mock_get:
            mock_get.side_effect = [first_resp, second_resp]
            safe_registry_get("https://example.com/v1/file.json")
        second_call_url = mock_get.call_args_list[1].args[0]
        assert second_call_url == "https://example.com/v2/file.json"

    def test_custom_kwargs_passed_through(self):
        """调用方 kwargs (如 headers) 应透传到 httpx.get。"""
        mock_resp = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
        mock_resp.status_code = 200
        with patch("httpx.get", return_value=mock_resp) as mock_get:
            safe_registry_get("https://example.com/", headers={"X-Foo": "bar"})
        assert mock_get.call_args.kwargs.get("headers") == {"X-Foo": "bar"}


# ── WeChatAdapter._download_remote_media 集成 ──


class TestDownloadRemoteMedia:
    """WeChatAdapter._download_remote_media 使用 butler.registry.url_safety.is_safe_url。"""

    @pytest.fixture
    def adapter(self, tmp_path, monkeypatch):
        from butler.gateway.platforms.types import PlatformConfig
        from butler.gateway.platforms.wechat_ilink import WeChatAdapter

        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        a = WeChatAdapter(
            PlatformConfig(token="api-token", extra={"account_id": "bot-acc"}),
        )
        a._send_session = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
        a._send_session.closed = False
        return a

    @pytest.mark.asyncio
    @pytest.mark.parametrize("unsafe_url", [
        "http://127.0.0.1/internal.png",
        "http://10.0.0.1/internal.png",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost/admin",
    ])
    async def test_blocks_unsafe_url(self, adapter, unsafe_url):
        """_download_remote_media 调 is_safe_url 拦截不安全 URL。
        这些 URL 即使在 hermes impl 也被拦 (metadata / 私有 IP)。"""
        with patch("butler.registry.url_safety.is_safe_url", return_value=False):
            with pytest.raises(ValueError, match="SSRF"):
                await adapter._download_remote_media(unsafe_url)
        adapter._send_session.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_blocks_when_is_safe_url_returns_false(self, adapter):
        """is_safe_url 返 False (无论什么原因) → 抛 ValueError。"""
        with patch("butler.registry.url_safety.is_safe_url", return_value=False):
            with pytest.raises(ValueError, match="SSRF"):
                await adapter._download_remote_media("http://anything.example/")

    @pytest.mark.asyncio
    async def test_value_error_includes_offending_url(self, adapter):
        """ValueError 消息应含原 URL, 便于诊断。"""
        url = "http://169.254.169.254/latest/meta-data/"
        with patch("butler.registry.url_safety.is_safe_url", return_value=False):
            with pytest.raises(ValueError) as exc_info:
                await adapter._download_remote_media(url)
        assert url in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_downloads_safe_url_to_tempfile(self, adapter):
        """is_safe_url 通过 → 调 session.get → 写到临时文件, 后缀来自 URL。"""
        with patch("butler.registry.url_safety.is_safe_url", return_value=True):
            fake_resp = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
            fake_resp.raise_for_status = MagicMock()  # noqa: magicmock-no-spec — method shim on mock resp
            fake_resp.read = AsyncMock(return_value=b"FAKE-IMAGE-DATA")  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager

            fake_session = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
            fake_session.__aenter__ = AsyncMock(return_value=fake_resp)  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
            fake_session.__aexit__ = AsyncMock(return_value=None)  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
            adapter._send_session.get = MagicMock(return_value=fake_session)  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager

            path = await adapter._download_remote_media("https://example.com/img.png")

        try:
            assert path.endswith(".png"), f"后缀应来自 URL: {path}"
            assert os.path.exists(path)
            with open(path, "rb") as f:
                assert f.read() == b"FAKE-IMAGE-DATA"
        finally:
            if os.path.exists(path):
                os.unlink(path)

    @pytest.mark.asyncio
    async def test_default_bin_suffix_when_no_extension(self, adapter):
        """URL 无后缀 → .bin。"""
        with patch("butler.registry.url_safety.is_safe_url", return_value=True):
            fake_resp = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
            fake_resp.raise_for_status = MagicMock()  # noqa: magicmock-no-spec — method shim on mock resp
            fake_resp.read = AsyncMock(return_value=b"X")  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager

            fake_session = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
            fake_session.__aenter__ = AsyncMock(return_value=fake_resp)  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
            fake_session.__aexit__ = AsyncMock(return_value=None)  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
            adapter._send_session.get = MagicMock(return_value=fake_session)  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager

            path = await adapter._download_remote_media("https://example.com/api/endpoint")

        try:
            assert path.endswith(".bin")
        finally:
            if os.path.exists(path):
                os.unlink(path)

    @pytest.mark.asyncio
    async def test_strips_query_string_for_suffix(self, adapter):
        """URL 含 ?query → 取 ? 前部分决定后缀。"""
        with patch("butler.registry.url_safety.is_safe_url", return_value=True):
            fake_resp = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
            fake_resp.raise_for_status = MagicMock()  # noqa: magicmock-no-spec — method shim on mock resp
            fake_resp.read = AsyncMock(return_value=b"X")  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager

            fake_session = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
            fake_session.__aenter__ = AsyncMock(return_value=fake_resp)  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
            fake_session.__aexit__ = AsyncMock(return_value=None)  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
            adapter._send_session.get = MagicMock(return_value=fake_session)  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager

            path = await adapter._download_remote_media("https://example.com/img.jpg?v=123")

        try:
            assert path.endswith(".jpg")
        finally:
            if os.path.exists(path):
                os.unlink(path)

    @pytest.mark.asyncio
    async def test_30_second_timeout_wraps_fetch(self, adapter):
        """asyncio.wait_for 用 30s 超时。"""
        with patch("butler.registry.url_safety.is_safe_url", return_value=True):
            fake_resp = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
            fake_resp.raise_for_status = MagicMock()  # noqa: magicmock-no-spec — method shim on mock resp
            fake_resp.read = AsyncMock(return_value=b"X")  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager

            fake_session = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
            fake_session.__aenter__ = AsyncMock(return_value=fake_resp)  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
            fake_session.__aexit__ = AsyncMock(return_value=None)  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
            adapter._send_session.get = MagicMock(return_value=fake_session)  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager

            with patch("butler.gateway.platforms.wechat_ilink.asyncio.wait_for") as mock_wait:
                mock_wait.return_value = b"X"
                path = await adapter._download_remote_media("https://example.com/file.png")
        try:
            assert path.endswith(".png")
            assert mock_wait.call_args.kwargs["timeout"] == 30
        finally:
            if os.path.exists(path):
                os.unlink(path)

    @pytest.mark.asyncio
    async def test_session_get_called_with_url(self, adapter):
        """session.get 应被调用且 url 参数匹配。"""
        with patch("butler.registry.url_safety.is_safe_url", return_value=True):
            fake_resp = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
            fake_resp.raise_for_status = MagicMock()  # noqa: magicmock-no-spec — method shim on mock resp
            fake_resp.read = AsyncMock(return_value=b"X")  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager

            fake_session = MagicMock()  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
            fake_session.__aenter__ = AsyncMock(return_value=fake_resp)  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
            fake_session.__aexit__ = AsyncMock(return_value=None)  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager
            adapter._send_session.get = MagicMock(return_value=fake_session)  # noqa: magicmock-no-spec — httpx Response/AsyncClient/ContextManager

            url = "https://cdn.example.com/image.jpeg"
            path = await adapter._download_remote_media(url)
        try:
            adapter._send_session.get.assert_called_once_with(url)
        finally:
            if os.path.exists(path):
                os.unlink(path)


# ── 静态契约 ──


class TestStaticContract:
    def test_exports_required_symbols(self):
        for name in ("is_safe_url", "assert_safe_redirect", "safe_registry_get", "httpx_fetch_kwargs"):
            assert hasattr(butler_url_safety, name), f"url_safety 应导出 {name}"

    def test_httpx_fetch_kwargs_disables_redirects(self):
        """默认 fetch kwargs 关闭重定向, SSRF 强化。"""
        kw = butler_url_safety.httpx_fetch_kwargs()
        assert kw["follow_redirects"] is False
        assert kw["timeout"] == 25.0

    def test_blocked_schemes_are_frozen(self):
        """_BLOCKED_SCHEMES 不可变。"""
        assert isinstance(butler_url_safety._BLOCKED_SCHEMES, frozenset)
        assert butler_url_safety._BLOCKED_SCHEMES == frozenset({"http", "https"})

    def test_private_networks_covers_known_ranges(self):
        """_PRIVATE_NETWORKS 含 RFC1918 + loopback + link-local + IPv6 ULA。"""
        nets = butler_url_safety._PRIVATE_NETWORKS
        targets = [
            "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
            "127.0.0.0/8", "169.254.0.0/16", "::1/128", "fc00::/7",
        ]
        for cidr in targets:
            net = ipaddress.ip_network(cidr)
            assert net in nets, f"_PRIVATE_NETWORKS 缺 {cidr}"
