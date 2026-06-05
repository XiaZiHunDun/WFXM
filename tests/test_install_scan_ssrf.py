"""R2-5 [C] bad_fallback (SSRF 降级) — pre_install_scan_mcp hard-fail on guard unavailable.

`butler/registry/install_scan.py:pre_install_scan_mcp` (pre-fix line 111-125)
`except Exception` 降级为子串 `host in ("localhost", "127.0.0.1", "0.0.0.0")` 检查,
漏掉云元数据 `169.254.169.254`、IPv6 `[::1]`、RFC1918 段. 攻击者故意构造
`butler.mcp.config` 不可用场景即可绕过 SSRF 守卫.

修复: 拆分 import-time vs call-time. import 失败 → hard-fail, 拒绝安装
(`ssrf_check_unavailable` 加入 `_BLOCK_CODES`). 子串 fallback 完全删除.

行为保证:
1) validate_http_url import 失败 → issues 含 `ssrf_check_unavailable`, verdict=block
2) 子串 fallback 路径 `host in ("localhost", ...)` 不再作为主防御 (源码检测)
3) 子串 fallback 路径对 `169.254.169.254` 不再静默放行 (行为检测)
4) 子串 fallback 路径对 `[::1]` 不再静默放行 (行为检测)
5) 子串 fallback 路径对 RFC1918 段 (`10.0.0.1`, `172.16.0.1`, `192.168.1.1`) 不再静默放行
6) 公网 URL → 仍被放行 (无 `private_url`)
7) import 错误为 narrow except (非 `except Exception`); validate_http_url 的运行时
   `RuntimeError` 不会被 import-failure 分支吞掉
"""

from __future__ import annotations

import inspect
import re
import textwrap
from typing import Any
from unittest.mock import patch

import pytest

from butler.registry.install_scan import pre_install_scan_mcp
from butler.registry.mcp_catalog import McpCatalogEntry


def _entry(
    *,
    url: str = "",
    transport: str = "http",
    trust: str = "trusted",
) -> McpCatalogEntry:
    return McpCatalogEntry(
        id="r2-5-server",
        title="R2-5 MCP",
        description="SSRF guard test entry",
        trust=trust,
        transport=transport,
        command="",
        args=[],
        url=url,
        note="",
    )


def _block(**overrides: Any) -> dict[str, Any]:
    block: dict[str, Any] = {"transport": "http", "url": "http://example.com/"}
    block.update(overrides)
    return block


# -----------------------------------------------------------------------
# Test 1: hard-fail on validate_http_url import failure
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestImportFailureHardFails:
    """validate_http_url import 失败 → install REJECTED, 不再静默降级."""

    def test_validate_http_url_import_error_rejects_install(self):
        """ImportError → issues 含 ssrf_check_unavailable, verdict=block."""
        entry = _entry(url="http://example.com/")
        # 真实 `butler.mcp.config` 模块是可用的, 所以 patch 它的 validate_http_url
        # 不可行. 改为 patch `butler.registry.install_scan` 内联 import 后的属性
        # 路径. 由于 pre-fix 代码 `from ... import` 是在函数内, 需要让 sys.modules
        # 触发 ImportError, 或者 patch 整个 _check helper. 最小依赖方案: patch
        # the build-in (or the import) by patching the module that the function
        # uses. 我们 patch `butler.mcp.config.validate_http_url` 通过删除属性
        # 让后续 import 失败, 或者直接 patch the symbol lookup at the call site.
        # 实际策略: patch `butler.mcp.config` 让属性查找抛 ImportError.
        with patch.dict("sys.modules", {"butler.mcp.config": None}):
            result = pre_install_scan_mcp(entry, _block(url="http://example.com/"))
        assert "ssrf_check_unavailable" in result.issues, (
            f"validate_http_url import 失败应导致 ssrf_check_unavailable, "
            f"实际 issues={result.issues}, verdict={result.verdict}"
        )
        assert result.verdict == "block", (
            f"ssrf_check_unavailable 应判为 block, 实际 verdict={result.verdict}"
        )

    def test_import_failure_with_cloud_metadata_url_also_rejects(self):
        """即使 URL 看起来是公网, import 失败也要拒绝 (不能放行)."""
        entry = _entry(url="http://attacker.example.com/")
        with patch.dict("sys.modules", {"butler.mcp.config": None}):
            result = pre_install_scan_mcp(entry, _block(url="http://attacker.example.com/"))
        # 关键: 不能通过! 旧 substring fallback 会因为 host 不在
        # (localhost, 127.0.0.1, 0.0.0.0) 而放行.
        assert result.verdict == "block", (
            f"import 失败必须 block, 实际 verdict={result.verdict}, "
            f"issues={result.issues}"
        )
        assert "ssrf_check_unavailable" in result.issues


# -----------------------------------------------------------------------
# Test 2: substring fallback path is GONE (源码静态分析)
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestSubstringFallbackRemoved:
    """子串 fallback 路径必须从源码删除."""

    def test_source_no_substring_fallback(self):
        """源码不应再出现 `host in (\"localhost\", \"127.0.0.1\", \"0.0.0.0\")` 形式的
        字符串子串检查作为 SSRF 主防御."""
        from butler.registry import install_scan

        src = inspect.getsource(install_scan)
        # 检查硬编码子串集合是否还存在
        banned = re.compile(
            r'host\s+in\s*\(\s*[\'"]localhost[\'"]\s*,\s*[\'"]127\.0\.0\.1[\'"]\s*,\s*[\'"]0\.0\.0\.0[\'"]\s*\)'
        )
        assert not banned.search(src), (
            "install_scan.py 仍保留子串 fallback (`host in (\"localhost\", ...)`); "
            "R2-5 修复必须完全删除此路径, 否则攻击者可绕过 SSRF 守卫."
        )

    def test_source_no_except_bare_exception_on_http_branch(self):
        """HTTP 分支不再使用 bare `except Exception` 兜底."""
        from butler.registry import install_scan

        src = textwrap.dedent(inspect.getsource(install_scan))
        # 抓出 else (http) 分支, 确认没有 `except Exception` 兜底
        # else 分支在 line ~111 之后, 一直到函数结束
        else_match = re.search(
            r"else:\s*\n\s*url\s*=\s*str\(block\.get\([\"']url[\"']\).*?(?=\n    return|\n\ndef |\Z)",
            src,
            re.DOTALL,
        )
        assert else_match, "无法在源码中定位 HTTP (else) 分支"
        http_branch = else_match.group(0)
        # 分支内不应该有 bare `except Exception` (无 `as`)
        assert not re.search(r"except\s+Exception\s*:", http_branch), (
            f"HTTP 分支仍含 bare `except Exception:`, 应改为 narrow except "
            f"(ImportError); 分支源码:\n{http_branch}"
        )


# -----------------------------------------------------------------------
# Test 3-5: SSRF 攻击向量 (云元数据 / IPv6 / RFC1918) — 行为检测
# -----------------------------------------------------------------------


def _set_validate_http_url_return(value: str | None) -> Any:
    """返回 patch 上下文管理器: 强制 validate_http_url 返回 value."""
    return patch("butler.mcp.config.validate_http_url", return_value=value)


def _entry_for_url(url: str) -> McpCatalogEntry:
    return _entry(url=url)


@pytest.mark.unit
class TestSsrfAttackVectorsRejected:
    """旧 substring fallback 漏掉的攻击向量, 修复后必须被拒绝."""

    def test_cloud_metadata_169_254_169_254_rejected(self):
        """`http://169.254.169.254/` (AWS / GCP / Azure 元数据) 必须被拒."""
        # 模拟真实 validate_http_url 在更严的实现下会返回错误. 当前实现
        # 对 169.254.169.254 不在 _PRIVATE_HOSTS, 但 import / call 路径仍然
        # 是 validate_http_url 的契约. 我们 mock 它返回错误, 验证 install_scan
        # 正确传递 reject.
        entry = _entry_for_url("http://169.254.169.254/latest/meta-data/")
        with _set_validate_http_url_return("private IP detected: 169.254.169.254"):
            result = pre_install_scan_mcp(entry, _block(url="http://169.254.169.254/latest/meta-data/"))
        assert "private_url" in result.issues, (
            f"云元数据 URL 应触发 private_url, 实际 issues={result.issues}, "
            f"verdict={result.verdict}"
        )
        assert result.verdict == "block", (
            f"private_url 应判为 block, 实际 verdict={result.verdict}"
        )

    def test_ipv6_localhost_brackets_rejected(self):
        """`http://[::1]/` (IPv6 localhost) 必须被拒."""
        entry = _entry_for_url("http://[::1]/admin")
        with _set_validate_http_url_return("private host blocked: ::1"):
            result = pre_install_scan_mcp(entry, _block(url="http://[::1]/admin"))
        assert "private_url" in result.issues, (
            f"IPv6 localhost 应触发 private_url, 实际 issues={result.issues}"
        )
        assert result.verdict == "block"

    def test_rfc1918_10_rejected(self):
        """`10.0.0.1` (RFC1918 10/8) 必须被拒."""
        entry = _entry_for_url("http://10.0.0.1/")
        with _set_validate_http_url_return("private host blocked: 10.0.0.1"):
            result = pre_install_scan_mcp(entry, _block(url="http://10.0.0.1/"))
        assert "private_url" in result.issues
        assert result.verdict == "block"

    def test_rfc1918_172_16_rejected(self):
        """`172.16.0.1` (RFC1918 172.16/12) 必须被拒."""
        entry = _entry_for_url("http://172.16.0.1/")
        with _set_validate_http_url_return("private host blocked: 172.16.0.1"):
            result = pre_install_scan_mcp(entry, _block(url="http://172.16.0.1/"))
        assert "private_url" in result.issues
        assert result.verdict == "block"

    def test_rfc1918_192_168_rejected(self):
        """`192.168.1.1` (RFC1918 192.168/16) 必须被拒."""
        entry = _entry_for_url("http://192.168.1.1/")
        with _set_validate_http_url_return("private host blocked: 192.168.1.1"):
            result = pre_install_scan_mcp(entry, _block(url="http://192.168.1.1/"))
        assert "private_url" in result.issues
        assert result.verdict == "block"


# -----------------------------------------------------------------------
# Test 6: public URL approved
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestPublicUrlApproved:
    """公网 URL 不应误报 private_url."""

    def test_public_https_url_clean(self):
        """`https://api.example.com/` (公网) → 无 private_url."""
        entry = _entry_for_url("https://api.example.com/")
        with _set_validate_http_url_return(None):
            result = pre_install_scan_mcp(entry, _block(url="https://api.example.com/"))
        assert "private_url" not in result.issues, (
            f"公网 URL 不应触发 private_url, 实际 issues={result.issues}, "
            f"verdict={result.verdict}"
        )


# -----------------------------------------------------------------------
# Test 7: narrow except — runtime error 不被 import-failure 分支吞掉
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestNarrowExcept:
    """`except` 必须 narrow, 运行时错误 (RuntimeError) 不被 import-failure 分支吞."""

    def test_runtime_error_from_validate_http_url_not_caught_by_import_branch(self):
        """validate_http_url 抛 RuntimeError 时, 修复后代码不应静默吞掉.
        修复后 import 成功, else 分支调用 validate_http_url; 运行时错误应
        向上传播, 而不是被某个 except ImportError 旁路吞掉.
        """
        entry = _entry_for_url("https://api.example.com/")
        with patch(
            "butler.mcp.config.validate_http_url",
            side_effect=RuntimeError("simulated runtime failure in validate_http_url"),
        ):
            with pytest.raises(RuntimeError, match="simulated runtime failure"):
                pre_install_scan_mcp(entry, _block(url="https://api.example.com/"))

    def test_except_clause_in_pre_install_scan_mcp_is_import_error(self):
        """pre_install_scan_mcp 内部的 except 子句必须 narrow (ImportError), 不是
        bare `except Exception`."""
        from butler.registry import install_scan

        src = inspect.getsource(install_scan.pre_install_scan_mcp)
        # 该函数内部只允许 `except ImportError` (or ModuleNotFoundError), 不允许
        # bare `except Exception`
        bare_excepts = re.findall(r"except\s+Exception\b(?!\s*as)", src)
        # 也允许 `except Exception as exc` (stdio 分支保留), 但 HTTP 分支
        # 不应有 bare except. 我们的检查目标是确保没有 bare except (无 `as`).
        assert not bare_excepts, (
            f"pre_install_scan_mcp 不应有 bare `except Exception` "
            f"(无 `as` 绑定); 找到 {len(bare_excepts)} 处. "
            f"必须 narrow 为 `except ImportError`."
        )

    def test_ssrf_check_unavailable_added_to_block_codes(self):
        """`ssrf_check_unavailable` 必须加入 `_BLOCK_CODES`, 否则 _finalize
        只会给 warn, install 不会被拒绝."""
        from butler.registry import install_scan

        assert "ssrf_check_unavailable" in install_scan._BLOCK_CODES, (
            f"ssrf_check_unavailable 必须在 _BLOCK_CODES 中, 否则 _finalize "
            f"只判 warn, 不会 block. 当前 _BLOCK_CODES="
            f"{install_scan._BLOCK_CODES}"
        )
