"""Sprint 8 audit fix: SEC-2 — /批准一次 指纹校验 fallback 绕过

Sprint 8 审计 SEC-2：`butler/permissions/approvals.py:124-126`
当 fingerprint 不匹配时，fallback 到 pending 字典本身 → 实际等于
"任何字符串都批准"。删除 fallback；不匹配必须拒绝。
"""

from __future__ import annotations

import json
from pathlib import Path

from butler.permissions.approvals import (
    ApprovalRequest,
    grant_once,
    save_pending,
)


def _patched_io(tmp_path, monkeypatch):
    """把 approvals_path 接到 tmp_path 下；_save 顺手 mkdir 父目录。"""
    monkeypatch.setattr(
        "butler.permissions.approvals.approvals_path",
        lambda sk: tmp_path / sk / "approvals.json",
    )

    def _save(sk, data):
        path: Path = tmp_path / sk / "approvals.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    monkeypatch.setattr("butler.permissions.approvals._save", _save)


def test_grant_once_rejects_fingerprint_mismatch(tmp_path, monkeypatch):
    """指纹不匹配必须被拒绝 — Sprint 8 SEC-2 复检测试。"""
    _patched_io(tmp_path, monkeypatch)

    req = ApprovalRequest(permission="rule", tool="write_file", pattern="secret.txt")
    save_pending("wx:mismatch", req)

    result = grant_once("wx:mismatch", fingerprint="deliberately_wrong_fp")

    assert result is not None, "必须返回错误信息而不是 None（成功）"
    assert "已批准" not in result, f"不应批准，但返回了 {result!r}"
    assert "不匹配" in result or "过期" in result or "不存在" in result, (
        f"应明确拒绝，实际返回 {result!r}"
    )


def test_grant_once_accepts_matching_fingerprint(tmp_path, monkeypatch):
    """正常匹配路径仍应批准 — 防止 fix 改坏主路径。"""
    _patched_io(tmp_path, monkeypatch)

    req = ApprovalRequest(permission="rule", tool="write_file", pattern="ok.txt")
    fp = save_pending("wx:match", req)
    assert fp

    result = grant_once("wx:match", fingerprint=fp)

    assert result is not None and "已批准" in result, (
        f"匹配应批准，实际返回 {result!r}"
    )
