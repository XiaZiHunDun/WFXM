"""Sprint 16 TST-11-9: butler.mcp.{client_http,client_stdio,server_stdio} 0% 覆盖.

bug: 三文件 0 测试:
  - butler/mcp/client_http.py (79 行): connect_http + call_http_tool
  - butler/mcp/client_stdio.py (100 行): _build_stdio_env + _resolve_cwd +
                                          connect_stdio + call_stdio_tool +
                                          json_dumps_result
  - butler/mcp/server_stdio.py (56 行): run_stdio_server + _dispatch_builtin

修复: 直接补单测覆盖各分支, 不改实现。
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from butler.mcp import client_http, client_stdio, server_stdio
from butler.mcp.client_http import call_http_tool
from butler.mcp.client_stdio import (
    _PROTECTED_ENV_KEYS,
    _build_stdio_env,
    _resolve_cwd,
    call_stdio_tool,
    json_dumps_result,
)
from butler.mcp.server_stdio import _EXPOSED, _dispatch_builtin
from butler.mcp.types import McpServerConfig


# ── client_stdio._build_stdio_env ──


class TestBuildStdioEnv:
    def test_returns_base_env_when_config_env_empty(self):
        """config.env == {} → 返回 base env (来自 safe_subprocess_env)。"""
        cfg = McpServerConfig(server_id="s", transport="stdio", env={})
        env = _build_stdio_env(cfg)
        # base 至少含 PATH
        assert "PATH" in env

    def test_config_env_overrides_base(self):
        """config.env 提供普通 key → 覆盖 base。"""
        cfg = McpServerConfig(
            server_id="s", transport="stdio",
            env={"MY_VAR": "my_value", "OTHER": "x"},
        )
        env = _build_stdio_env(cfg)
        assert env["MY_VAR"] == "my_value"
        assert env["OTHER"] == "x"

    def test_protected_keys_blocked(self, caplog):
        """config.env 提供 PATH/HOME/LD_PRELOAD 等 → 跳过 + warning。"""
        cfg = McpServerConfig(
            server_id="s", transport="stdio",
            env={
                "PATH": "/malicious/path",
                "HOME": "/tmp/evil",
                "LD_PRELOAD": "/lib/evil.so",
                "LD_LIBRARY_PATH": "/lib/evil",
                "PYTHONPATH": "/tmp/evil",
                "USER": "attacker",
                "SHELL": "/bin/bash",
                "LOGNAME": "attacker",
                "LANG": "C",
            },
        )
        with caplog.at_level("WARNING"):
            env = _build_stdio_env(cfg)
        # base env 的 PATH 应保留 (非 override)
        assert env.get("PATH") != "/malicious/path", (
            "PATH 应被阻止, 不应被 config.env 覆盖"
        )
        assert env.get("HOME") != "/tmp/evil", "HOME 应被阻止"
        assert "LD_PRELOAD" not in env, "LD_PRELOAD 应被阻止"
        assert "LD_LIBRARY_PATH" not in env, "LD_LIBRARY_PATH 应被阻止"
        assert "PYTHONPATH" not in env, "PYTHONPATH 应被阻止"
        # LANG 是 base 已有的, base 没 override
        assert "LANG" in env

        # 至少 1 个 warning 应被记录
        assert any(
            "protected key" in r.message.lower()
            for r in caplog.records
        ), f"expected protected key warning, got: {[r.message for r in caplog.records]}"

    def test_none_values_skipped(self):
        """config.env 值是 None → 跳过 (不写入 base)。"""
        cfg = McpServerConfig(
            server_id="s", transport="stdio",
            env={"GOOD": "ok", "NONE_VAL": None},
        )
        env = _build_stdio_env(cfg)
        assert env["GOOD"] == "ok"
        assert "NONE_VAL" not in env

    def test_case_insensitive_protection(self, caplog):
        """protected key 大小写不敏感 (Path / path / PATH 都应被阻止)。"""
        cfg = McpServerConfig(
            server_id="s", transport="stdio",
            env={"path": "/evil", "Path": "/evil2"},
        )
        with caplog.at_level("WARNING"):
            env = _build_stdio_env(cfg)
        # base PATH 应保留
        assert env.get("PATH") != "/evil" and env.get("PATH") != "/evil2"

    def test_non_string_keys_coerced(self):
        """config.env key 是 int/Path 等 → 强制 str。"""
        cfg = McpServerConfig(
            server_id="s", transport="stdio",
            env={42: "numeric_key"},
        )
        env = _build_stdio_env(cfg)
        assert env["42"] == "numeric_key"


# ── client_stdio._resolve_cwd ──


class TestResolveCwd:
    def test_config_cwd_wins(self, tmp_path: Path):
        """config.cwd 存在 → 返回 expanduser 后的绝对路径。"""
        cfg = McpServerConfig(server_id="s", transport="stdio", cwd="~/custom")
        cwd = _resolve_cwd(cfg, workspace=tmp_path)
        assert cwd is not None
        assert "custom" in cwd
        assert "~" not in cwd

    def test_workspace_used_when_no_config_cwd(self, tmp_path: Path):
        """config.cwd 为空 + workspace 是 dir → 返回 workspace。"""
        cfg = McpServerConfig(server_id="s", transport="stdio", cwd="")
        cwd = _resolve_cwd(cfg, workspace=tmp_path)
        assert cwd == str(tmp_path)

    def test_none_when_no_cwd_no_workspace(self):
        """config.cwd 空 + workspace=None → None。"""
        cfg = McpServerConfig(server_id="s", transport="stdio", cwd="")
        cwd = _resolve_cwd(cfg, workspace=None)
        assert cwd is None

    def test_workspace_must_be_dir(self, tmp_path: Path):
        """workspace 路径不存在 (不是 dir) → 忽略, 返回 None (若 cwd 也无)。"""
        cfg = McpServerConfig(server_id="s", transport="stdio", cwd="")
        nonexistent = tmp_path / "nope"
        cwd = _resolve_cwd(cfg, workspace=nonexistent)
        assert cwd is None


# ── client_stdio.json_dumps_result ──


class TestJsonDumpsResult:
    def test_dict_passthrough_via_str(self):
        """非 model_dump 对象 → str() fallback。"""
        result = {"raw": "value", "n": 42}
        out = json_dumps_result(result)
        assert out == str(result)

    def test_object_with_model_dump(self):
        """有 .model_dump() 的对象 → JSON dump。"""
        result = MagicMock()  # noqa: magicmock-no-spec — mocks pydantic-like obj with .model_dump()
        result.model_dump.return_value = {"a": 1, "b": "x"}
        out = json_dumps_result(result)
        parsed = json.loads(out)
        assert parsed == {"a": 1, "b": "x"}
        assert result.model_dump.called

    def test_model_dump_exception_falls_back_to_str(self):
        """model_dump() 抛异常 → str() fallback。"""
        result = MagicMock()  # noqa: magicmock-no-spec — mocks pydantic-like obj with .model_dump()
        result.model_dump.side_effect = RuntimeError("kaboom")
        out = json_dumps_result(result)
        # str(MagicMock) 包含 repr, 至少非空
        assert out
        # 不应抛

    def test_ensure_ascii_false(self):
        """非 ASCII 字符不被转义 (ensure_ascii=False)。"""
        result = MagicMock()  # noqa: magicmock-no-spec — mocks pydantic-like obj with .model_dump()
        result.model_dump.return_value = {"name": "中文"}
        out = json_dumps_result(result)
        assert "中文" in out, f"non-ASCII not preserved: {out!r}"


# ── client_*.call_*_tool ──


class TestCallToolContentExtraction:
    def test_call_stdio_tool_concatenates_text_parts(self):
        """call_stdio_tool: result.content 含多个 text 块 → 用 \\n 连接。"""
        session = MagicMock()  # noqa: magicmock-no-spec — MCP ClientSession 复杂多接口
        text_block_a = MagicMock()  # noqa: magicmock-no-spec — MCP text block (use mcp.types.TextContent in future)
        text_block_a.text = "alpha"
        text_block_b = MagicMock()  # noqa: magicmock-no-spec — MCP text block (use mcp.types.TextContent in future)
        text_block_b.text = "beta"
        result = MagicMock()  # noqa: magicmock-no-spec — MCP CallToolResult (use mcp.types in future)
        result.content = [text_block_a, text_block_b]
        session.call_tool = AsyncMock(return_value=result)

        import asyncio
        out = asyncio.run(call_stdio_tool(session, "tool", {"x": 1}))
        assert out == "alpha\nbeta"

    def test_call_stdio_tool_falls_back_to_str(self):
        """call_stdio_tool: content 空 → json_dumps_result。"""
        session = MagicMock()  # noqa: magicmock-no-spec — MCP ClientSession 复杂多接口
        result = MagicMock()  # noqa: magicmock-no-spec — MCP CallToolResult (use mcp.types in future)
        result.content = None
        session.call_tool = AsyncMock(return_value=result)

        import asyncio
        out = asyncio.run(call_stdio_tool(session, "tool", {}))
        # json_dumps_result 走 str() 路径
        assert out

    def test_call_stdio_tool_handles_block_without_text(self):
        """call_stdio_tool: content 块无 .text 属性 → str(content) 兜底。"""
        session = MagicMock()  # noqa: magicmock-no-spec — MCP ClientSession 复杂多接口
        block = MagicMock(spec=[])  # 没有 .text 属性
        result = MagicMock()  # noqa: magicmock-no-spec — MCP CallToolResult (use mcp.types in future)
        result.content = [block]
        session.call_tool = AsyncMock(return_value=result)

        import asyncio
        out = asyncio.run(call_stdio_tool(session, "tool", {}))
        # str(block) 至少非空
        assert out

    def test_call_http_tool_concatenates_text_parts(self):
        """call_http_tool: 同上, 用 \\n 拼接。"""
        session = MagicMock()  # noqa: magicmock-no-spec — MCP ClientSession 复杂多接口
        text_block_a = MagicMock()  # noqa: magicmock-no-spec — MCP text block (use mcp.types.TextContent in future)
        text_block_a.text = "http_alpha"
        text_block_b = MagicMock()  # noqa: magicmock-no-spec — MCP text block (use mcp.types.TextContent in future)
        text_block_b.text = "http_beta"
        result = MagicMock()  # noqa: magicmock-no-spec — MCP CallToolResult (use mcp.types in future)
        result.content = [text_block_a, text_block_b]
        session.call_tool = AsyncMock(return_value=result)

        import asyncio
        out = asyncio.run(call_http_tool(session, "tool", {}))
        assert out == "http_alpha\nhttp_beta"

    def test_call_http_tool_falls_back_to_json_dumps(self):
        """call_http_tool: content 空 → json_dumps_result 走 str() 路径。"""
        session = MagicMock()  # noqa: magicmock-no-spec — MCP ClientSession 复杂多接口
        result = MagicMock()  # noqa: magicmock-no-spec — MCP CallToolResult (use mcp.types in future)
        result.content = []
        session.call_tool = AsyncMock(return_value=result)

        import asyncio
        out = asyncio.run(call_http_tool(session, "tool", {}))
        assert out


# ── client_http.connect_http (仅错误路径, 真实连接需要 MCP SDK + HTTP server) ──


class TestConnectHttpErrorPaths:
    def test_invalid_url_raises_value_error(self):
        """validate_http_url 返回错误 → connect_http 抛 ValueError。"""
        cfg = McpServerConfig(
            server_id="s", transport="http",
            url="ftp://not-http.example.com",
        )
        with pytest.raises(ValueError, match="unsupported scheme"):
            import asyncio
            asyncio.run(client_http.connect_http(cfg))

    def test_missing_url_raises_value_error(self):
        """url 为空 → validate_http_url 返回 'unsupported scheme' (空 scheme 先于 host 检查) → ValueError。"""
        cfg = McpServerConfig(server_id="s", transport="http", url="")
        # validate_http_url 先查 scheme 再查 host, 空 url 在 scheme 检查就被拒
        with pytest.raises(ValueError, match="unsupported scheme"):
            import asyncio
            asyncio.run(client_http.connect_http(cfg))


# ── server_stdio._dispatch_builtin ──


class TestDispatchBuiltin:
    def test_not_exposed_tool_returns_error_json(self):
        """_EXPOSED 之外的工具名 → 返回 ``{"ok": False, "error": ...}`` JSON。"""
        out = _dispatch_builtin("nonexistent_tool", {"x": 1})
        parsed = json.loads(out)
        assert parsed["ok"] is False
        assert "tool not exposed" in parsed["error"]

    def test_exposed_tool_invokes_dispatch_tool(self):
        """_EXPOSED 之内的工具名 → 调用 dispatch_tool。"""
        with patch("butler.tools.registry.dispatch_tool", return_value="dispatched!") as mock:
            out = _dispatch_builtin("read_file", {"path": "/tmp/x"})
        assert out == "dispatched!"
        mock.assert_called_once()
        call_args = mock.call_args
        assert call_args[0][0] == "read_file"
        assert call_args[0][1] == {"path": "/tmp/x"}

    @pytest.mark.parametrize("tool_name", _EXPOSED)
    def test_all_exposed_tools_dispatched(self, tool_name: str):
        """_EXPOSED 列表中的所有 4 个工具都应被正确 dispatch。"""
        with patch("butler.tools.registry.dispatch_tool", return_value=f"out_{tool_name}") as mock:
            out = _dispatch_builtin(tool_name, {})
        assert out == f"out_{tool_name}"
        mock.assert_called_once_with(tool_name, {})


# ── 静态契约 ──


class TestStaticContract:
    def test_client_stdio_exports_required_symbols(self):
        """client_stdio 应导出: connect_stdio, call_stdio_tool, json_dumps_result, _build_stdio_env, _resolve_cwd。"""
        for name in (
            "connect_stdio", "call_stdio_tool", "json_dumps_result",
            "_build_stdio_env", "_resolve_cwd", "_PROTECTED_ENV_KEYS",
        ):
            assert hasattr(client_stdio, name), (
                f"client_stdio 应导出 {name}"
            )

    def test_client_http_exports_required_symbols(self):
        """client_http 应导出: connect_http, call_http_tool。"""
        for name in ("connect_http", "call_http_tool"):
            assert hasattr(client_http, name), (
                f"client_http 应导出 {name}"
            )

    def test_server_stdio_exposes_four_tools(self):
        """server_stdio._EXPOSED 应恰好 4 个工具。"""
        assert len(_EXPOSED) == 4, (
            f"_EXPOSED 应有 4 个工具, 实际 {len(_EXPOSED)}: {_EXPOSED}"
        )
        assert "read_file" in _EXPOSED
        assert "list_directory" in _EXPOSED
        assert "search_files" in _EXPOSED
        assert "session_todos_list" in _EXPOSED

    def test_protected_env_keys_includes_known_dangerous(self):
        """_PROTECTED_ENV_KEYS 必须包含已知的危险 key。"""
        required = {
            "PATH", "HOME", "USER", "SHELL", "LOGNAME", "LANG",
            "LD_PRELOAD", "LD_LIBRARY_PATH", "PYTHONPATH",
        }
        assert required.issubset(_PROTECTED_ENV_KEYS), (
            f"_PROTECTED_ENV_KEYS 缺: {required - _PROTECTED_ENV_KEYS}"
        )
