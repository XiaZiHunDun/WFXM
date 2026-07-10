"""Sprint 10 SEC-10-2: read_document 路径遍历（缺 check_tool_path）

Sprint 10 安全审计：tools/document_reader.py:40 convert_document
直接 Path(path).expanduser().resolve()，未调 check_tool_path。
其他 IO tool（_tool_terminal/_tool_search_files/_tool_list_directory/
_tool_write_file）全部走 butler.tools.path_safety.check_tool_path，
唯独 read_document 例外。

支持 .pdf/.docx/.html/.csv/.json/.xml/.zip/.epub，prompt 注入可读
/etc/passwd、.aws/credentials、SSH 私钥、Sprint 6 path_safety 修过的
所有路径再次沦陷。

修复：tool_read_document 入口加 check_tool_path 校验，拒敏感路径 +
workspace 越界（与 _tool_write_file 同款）。
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from butler.tools.document_reader import tool_read_document


@pytest.mark.unit
def test_read_document_calls_check_tool_path(tmp_path):
    """tool_read_document 应调 check_tool_path 守门。"""
    fake_doc = tmp_path / "ok.pdf"
    fake_doc.write_text("dummy", encoding="utf-8")

    with patch("butler.tools.path_safety.check_tool_path") as mock_check:
        mock_check.return_value = type("R", (), {"allowed": True, "error": ""})()
        with patch("butler.tools.document_reader._markitdown_available", return_value=True):
            with patch("butler.tools.document_reader.convert_document", return_value={"ok": True, "text": "x"}):
                tool_read_document(path=str(fake_doc))
    # 关键：check_tool_path 必被调
    assert mock_check.called, "tool_read_document 必须调 check_tool_path"
    call_args = mock_check.call_args
    # 第一个位置参数应是 str path
    assert call_args.args[0] == str(fake_doc), f"check_tool_path 收到的 path 错：{call_args.args}"
    # for_write=False（只读）
    assert call_args.kwargs.get("for_write", False) is False, "read_document 应 for_write=False"


@pytest.mark.unit
def test_read_document_rejects_sensitive_path(tmp_path):
    """敏感路径（/etc/passwd 等）应被 check_tool_path 拒，工具返 error。"""
    with patch("butler.tools.path_safety.check_tool_path") as mock_check:
        mock_check.return_value = type("R", (), {
            "allowed": False, "error": "Access denied: sensitive path",
        })()
        result = tool_read_document(path="/etc/passwd")
    data = json.loads(result)
    assert "error" in data, f"sensitive path 应返 error，实际: {data}"
    assert "sensitive" in data["error"].lower() or "denied" in data["error"].lower(), (
        f"error 应含 sensitive/denied：{data['error']}"
    )


@pytest.mark.unit
def test_read_document_rejects_outside_workspace(tmp_path):
    """workspace 越界应被拒。"""
    with patch("butler.tools.path_safety.check_tool_path") as mock_check:
        mock_check.return_value = type("R", (), {
            "allowed": False, "error": "Access denied: path is outside workspace",
        })()
        result = tool_read_document(path="/tmp/secret.pdf")
    data = json.loads(result)
    assert "error" in data
    assert "denied" in data["error"].lower() or "outside" in data["error"].lower(), (
        f"workspace 越界应报 denied：{data['error']}"
    )


@pytest.mark.unit
def test_read_document_passes_safe_path_through(tmp_path):
    """合法路径（check 通过）应正常转交 convert_document。"""
    fake_doc = tmp_path / "ok.pdf"
    fake_doc.write_text("dummy", encoding="utf-8")

    with patch("butler.tools.path_safety.check_tool_path") as mock_check:
        mock_check.return_value = type("R", (), {"allowed": True, "error": ""})()
        with patch("butler.tools.document_reader._markitdown_available", return_value=True):
            with patch("butler.tools.document_reader.convert_document") as mock_convert:
                mock_convert.return_value = {"ok": True, "text": "converted"}
                result = tool_read_document(path=str(fake_doc))
    assert mock_convert.called, "allowed path 应转交 convert_document"
    data = json.loads(result)
    assert data.get("ok") is True
    assert data.get("text") == "converted"


@pytest.mark.unit
def test_read_document_no_path_still_returns_error():
    """空 path 仍返 error（前置检查不调 check_tool_path）。"""
    with patch("butler.tools.path_safety.check_tool_path") as mock_check:
        result = tool_read_document(path="")
    data = json.loads(result)
    assert "error" in data
    assert "path" in data["error"].lower() or "required" in data["error"].lower()
    # 空 path 不应触发 check_tool_path
    assert not mock_check.called, "空 path 应前置返 error，不调 check_tool_path"


@pytest.mark.unit
def test_read_document_no_markitdown_check_tool_path_still_called(tmp_path):
    """markitdown 不可用时，check_tool_path 也应先调（按顺序）。"""
    fake_doc = tmp_path / "ok.pdf"
    with patch("butler.tools.path_safety.check_tool_path") as mock_check:
        mock_check.return_value = type("R", (), {"allowed": True, "error": ""})()
        with patch("butler.tools.document_reader._markitdown_available", return_value=False):
            result = tool_read_document(path=str(fake_doc))
    data = json.loads(result)
    # 顺序：check_tool_path 先，markitdown 不可用 error 后
    assert mock_check.called, "check_tool_path 应在 markitdown 检查前调"
    assert "markitdown" in data.get("error", "").lower() or "not installed" in data.get("error", "").lower()


@pytest.mark.unit
def test_check_tool_path_is_called_with_resolved_path():
    """check_tool_path 应收到 string path（不是 Path 对象），与 _tool_write_file 同款。"""
    import inspect
    from butler.tools import document_reader

    src = inspect.getsource(document_reader.tool_read_document)
    # 关键检查：tool_read_document 源码应含 check_tool_path 调用
    assert "check_tool_path" in src, (
        f"tool_read_document 源码必须调 check_tool_path\n实际：\n{src}"
    )
