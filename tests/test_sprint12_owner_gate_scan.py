"""Sprint 12 SEC-12-1: AST 静态扫描 owner gate

扫描 butler/gateway/ 下所有 `def handle_*command(`` 和 `def _cmd_*(ctx)`` 函数，
检查函数体内是否调用了 is_gateway_owner(...) 或 _require_owner(...)。

Sprint 11 审计：6 个新模块复现 owner-gate 漏洞（SEC-11-1..7）。Sprint 12 用
静态扫描阻断同类问题在新代码中复现。

豁免机制：在函数 docstring 或前 3 行注释中含 `# owner-gate-opt-out: <理由>`
可豁免（用于真正 public handler 如 /help、/总览）。

Hard fail 策略：pytest 失败即阻断 CI。

测试本身也算一个测试（self-test）：验证扫描器能区分有 gate / 无 gate / opt-out。
"""

from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

import pytest

GATEWAY_ROOT = Path(__file__).resolve().parents[1] / "butler" / "gateway"
HANDLER_PATTERN = re.compile(r"^(handle_[a-z_]+command|_cmd_[a-z_]+)$")
OPT_OUT_MARKER = re.compile(r"owner-gate-opt-out\s*:")
GATE_CALL_NAMES = frozenset({"is_gateway_owner", "_require_owner"})


def _function_calls_name(func: ast.FunctionDef, name: str) -> bool:
    """True if `func` body (or nested FunctionDef) calls a top-level `name`."""
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            func_node = node.func
            if isinstance(func_node, ast.Name) and func_node.id == name:
                return True
            if (
                isinstance(func_node, ast.Attribute)
                and isinstance(func_node.value, ast.Name)
                and func_node.value.id == name
            ):
                return True
    return False


def _has_opt_out_marker(func: ast.FunctionDef) -> bool:
    """True if docstring or leading 3 lines contain owner-gate-opt-out: <reason>."""
    if (
        func.body
        and isinstance(func.body[0], ast.Expr)
        and isinstance(func.body[0].value, ast.Constant)
        and isinstance(func.body[0].value.value, str)
        and OPT_OUT_MARKER.search(func.body[0].value.value)
    ):
        return True
    # Walk leading statements (skip docstring Expr) for inline comment-like strings
    for stmt in func.body[:4]:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            if isinstance(stmt.value.value, str) and OPT_OUT_MARKER.search(stmt.value.value):
                return True
    return False


def _is_handler(func: ast.FunctionDef) -> bool:
    return bool(HANDLER_PATTERN.match(func.name)) and isinstance(func, ast.FunctionDef)


def scan_owner_gate_gaps() -> list[tuple[Path, str, int, str]]:
    """Return list of (file, func_name, lineno, reason) for handlers missing gate."""
    gaps: list[tuple[Path, str, int, str]] = []
    for py in sorted(GATEWAY_ROOT.rglob("*.py")):
        if py.name == "__init__.py":
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or not _is_handler(node):
                continue
            has_gate = any(
                _function_calls_name(node, n) for n in GATE_CALL_NAMES
            )
            if has_gate or _has_opt_out_marker(node):
                continue
            gaps.append(
                (
                    py,
                    node.name,
                    node.lineno,
                    "no is_gateway_owner/_require_owner call; "
                    "add gate or # owner-gate-opt-out: <reason>",
                )
            )
    return gaps


def _format_gap(gap: tuple[Path, str, int, str]) -> str:
    rel = gap[0].relative_to(Path.cwd())
    return f"  {rel}:{gap[2]} {gap[1]}() — {gap[3]}"


@pytest.mark.security
def test_all_gateway_handlers_have_owner_gate_or_opt_out():
    """Sprint 12 SEC-12-1: 所有 handler 必须有 owner gate 或 opt-out 标注。

    Hard fail: 任何缺 gate 且无 opt-out 的 handler 都阻断 CI。
    """
    gaps = scan_owner_gate_gaps()
    if gaps:
        msg = textwrap.dedent(
            f"""
            Sprint 12 owner-gate static scan found {len(gaps)} unguarded handler(s):

            {chr(10).join(_format_gap(g) for g in gaps)}

            Fix options:
              1) Add is_gateway_owner() / _require_owner() check at function top
              2) Add docstring or leading-line comment with owner-gate-opt-out: <reason>
                 (e.g. for truly public handlers like /help, /总览)
            """
        ).strip()
        pytest.fail(msg)


class TestScannerSelfTest:
    """Self-test: 验证扫描器能正确区分 3 类情况。"""

    def test_detects_unguarded_handler(self, tmp_path: Path, monkeypatch):
        target = tmp_path / "mod.py"
        target.write_text(
            textwrap.dedent(
                """
                def handle_x_command(arg):
                    return f"echo: {arg}"
                """
            ).strip()
        )
        # Redirect scan to tmp_path
        monkeypatch.setattr(
            "tests.test_sprint12_owner_gate_scan.GATEWAY_ROOT", tmp_path
        )
        gaps = scan_owner_gate_gaps()
        names = [g[1] for g in gaps]
        assert "handle_x_command" in names, (
            f"未加 gate 的 handler 应被检出，实际: {names}"
        )

    def test_passes_handler_with_is_gateway_owner(
        self, tmp_path: Path, monkeypatch
    ):
        target = tmp_path / "mod.py"
        target.write_text(
            textwrap.dedent(
                """
                from butler.gateway.owner_gate import is_gateway_owner

                def handle_y_command(arg, *, platform=""):
                    if not is_gateway_owner(platform=platform):
                        return "denied"
                    return f"ok: {arg}"
                """
            ).strip()
        )
        monkeypatch.setattr(
            "tests.test_sprint12_owner_gate_scan.GATEWAY_ROOT", tmp_path
        )
        gaps = scan_owner_gate_gaps()
        names = [g[1] for g in gaps]
        assert "handle_y_command" not in names, (
            f"加 is_gateway_owner 的 handler 不应被误报，实际: {names}"
        )

    def test_passes_handler_with_require_owner_helper(
        self, tmp_path: Path, monkeypatch
    ):
        target = tmp_path / "mod.py"
        target.write_text(
            textwrap.dedent(
                """
                def _require_owner(platform, external_id, session_key):
                    return None

                def _cmd_z(ctx):
                    if (gate := _require_owner(ctx.platform, ctx.external_id, ctx.session_key)):
                        return gate
                    return "ok"
                """
            ).strip()
        )
        monkeypatch.setattr(
            "tests.test_sprint12_owner_gate_scan.GATEWAY_ROOT", tmp_path
        )
        gaps = scan_owner_gate_gaps()
        names = [g[1] for g in gaps]
        assert "_cmd_z" not in names, (
            f"调 _require_owner helper 的 handler 不应被误报，实际: {names}"
        )

    def test_passes_handler_with_opt_out_marker(
        self, tmp_path: Path, monkeypatch
    ):
        target = tmp_path / "mod.py"
        target.write_text(
            textwrap.dedent(
                '''
                def handle_public_command(arg):
                    """Public echo helper.

                    owner-gate-opt-out: public read-only echo, no owner data exposed
                    """
                    return f"echo: {arg}"
                '''
            ).strip()
        )
        monkeypatch.setattr(
            "tests.test_sprint12_owner_gate_scan.GATEWAY_ROOT", tmp_path
        )
        gaps = scan_owner_gate_gaps()
        names = [g[1] for g in gaps]
        assert "handle_public_command" not in names, (
            f"opt-out 标注的 handler 不应被误报，实际: {names}"
        )

    def test_detects_cmd_handlers_too(self, tmp_path: Path, monkeypatch):
        target = tmp_path / "mod.py"
        target.write_text(
            textwrap.dedent(
                """
                def _cmd_a(ctx):
                    return "a"

                def _cmd_b(ctx):
                    if True:
                        return "b"
                """
            ).strip()
        )
        monkeypatch.setattr(
            "tests.test_sprint12_owner_gate_scan.GATEWAY_ROOT", tmp_path
        )
        gaps = scan_owner_gate_gaps()
        names = sorted(g[1] for g in gaps)
        assert names == ["_cmd_a", "_cmd_b"], (
            f"_cmd_* handler 应被全部检出，实际: {names}"
        )
