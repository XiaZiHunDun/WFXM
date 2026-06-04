"""Sprint 23 TST-10-6: MagicMock spec= 策略执行 (audit 暂缓项).

`tests/` 中 564 处 `MagicMock()` 无 `spec=` 参数. 这导致:
1. **静默通过错 API 调用**: `mock.foo()` 即使真实对象无 `.foo`,
   MagicMock 自动创建一个新的 mock. 测试通过, 实际生产崩.
2. **IDE 失明**: mypy/pyright 看到 `MagicMock()` 返 `Any`,
   后续 `.bar().baz()` 都是 `Any` — 类型检查器无法帮我们.
3. **重构脆弱**: 真实类型改了方法名, mock 测试不报.

`MagicMock(spec=ClassName)` (或 `spec_set=`) 让 mock 严格模拟
目标类型的属性集, attribute error 真实抛出.

修复策略 (本 sprint 范围, 全量改 564 处风险过大):
- 写一个 AST 扫描器 `_policies/scan_magicmock_spec.py` (cli + 库)
- 写本测试, 验证扫描器: 能找出未 spec= 的 MagicMock, 不误报
- 提供 `--report` 模式输出违规列表 (基线 + 增量 diff 用)
- 提供豁免机制 `# noqa: magicmock-no-spec` 注释

行为保证 (本测试):
1) 扫描器在含 MagicMock() 的代码中找出 violation
2) 扫描器放过 MagicMock(spec=X) / MagicMock(spec_set=Y) / MagicMock(wraps=Z)
3) 豁免注释 `# noqa: magicmock-no-spec` 跳过该行
4) 报告数据结构稳定 (path, lineno, func_name, snippet)
"""

from __future__ import annotations

import importlib
import pathlib
import subprocess
import sys

import pytest

# ---------- import scanner from butler.tests_policies ----------

_POLICIES_PKG = "butler.tests_policies"
_SCANNER_MOD = "butler.tests_policies.scan_magicmock_spec"


def _import_scanner():
    """Import the scanner module. Skip test if not yet implemented (TDD red phase)."""
    try:
        return importlib.import_module(_SCANNER_MOD)
    except ImportError:
        return None


# ---------- helpers ----------

@pytest.fixture
def sample_violating_file(tmp_path: pathlib.Path) -> pathlib.Path:
    """临时写一个含 MagicMock() 违规的文件."""
    p = tmp_path / "violating.py"
    p.write_text(
        "from unittest.mock import MagicMock\n"
        "\n"
        "def test_x():\n"
        "    m1 = MagicMock()          # violation\n"
        "    m2 = MagicMock(spec=[])   # ok\n"
        "    m3 = MagicMock(spec=int) # ok\n"
        "    m4 = MagicMock(wraps=42) # ok\n"
        "    m5 = MagicMock(name='x') # violation (name only)\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def sample_clean_file(tmp_path: pathlib.Path) -> pathlib.Path:
    """临时写一个完全合规的文件."""
    p = tmp_path / "clean.py"
    p.write_text(
        "from unittest.mock import MagicMock\n"
        "\n"
        "def test_x():\n"
        "    m1 = MagicMock(spec=int)\n"
        "    m2 = MagicMock(spec_set=str)\n"
        "    m3 = MagicMock(wraps=42)\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def sample_exempted_file(tmp_path: pathlib.Path) -> pathlib.Path:
    """临时写一个豁免的文件."""
    p = tmp_path / "exempted.py"
    p.write_text(
        "from unittest.mock import MagicMock\n"
        "\n"
        "def test_x():\n"
        "    m1 = MagicMock()  # noqa: magicmock-no-spec\n"
        "    m2 = MagicMock()  # noqa: magicmock-no-spec\n",
        encoding="utf-8",
    )
    return p


# ---------- TDD tests ----------

@pytest.mark.unit
class TestScanMagicMockSpec:
    """扫描器必须: 检测未 spec= / 放过 spec= / 尊重豁免."""

    def test_scanner_module_exists(self):
        """`_policies/scan_magicmock_spec.py` 必须在 butler.tests_policies pkg 下."""
        scanner = _import_scanner()
        if scanner is None:
            pytest.skip(
                f"TDD red phase: {_SCANNER_MOD} 还没实现, "
                f"先实现扫描器"
            )
        assert hasattr(scanner, "scan_file"), (
            "scanner 必须有 scan_file(path) -> list[Violation]"
        )
        assert hasattr(scanner, "scan_paths"), (
            "scanner 必须有 scan_paths(paths) -> list[Violation]"
        )
        assert hasattr(scanner, "Violation"), (
            "scanner 必须有 Violation dataclass / NamedTuple"
        )

    def test_violation_attributes(self, sample_violating_file):
        """Violation 必须有 path / lineno / func_name / snippet 字段."""
        scanner = _import_scanner()
        if scanner is None:
            pytest.skip("TDD red phase: 扫描器未实现")
        vs = scanner.scan_file(sample_violating_file)
        assert vs, "应至少找到 2 处违规 (m1, m5)"
        v = vs[0]
        assert hasattr(v, "path")
        assert hasattr(v, "lineno")
        assert hasattr(v, "func_name")
        assert hasattr(v, "snippet")
        # path 是 pathlib.Path
        assert v.path == sample_violating_file
        # lineno 是 int > 0
        assert isinstance(v.lineno, int) and v.lineno > 0
        # func_name 是 test_x
        assert v.func_name == "test_x"
        # snippet 含 MagicMock
        assert "MagicMock" in v.snippet

    def test_clean_file_has_no_violations(self, sample_clean_file):
        """全 spec= 的文件 → 0 违规."""
        scanner = _import_scanner()
        if scanner is None:
            pytest.skip("TDD red phase: 扫描器未实现")
        vs = scanner.scan_file(sample_clean_file)
        assert vs == [], (
            f"clean.py 应 0 违规, 实际: {vs}"
        )

    def test_violating_file_finds_two_violations(self, sample_violating_file):
        """含 2 处未 spec= (m1, m5) → 找到 2 个 Violation, 跳过 3 个 (m2/m3/m4)."""
        scanner = _import_scanner()
        if scanner is None:
            pytest.skip("TDD red phase: 扫描器未实现")
        vs = scanner.scan_file(sample_violating_file)
        assert len(vs) == 2, (
            f"应 2 违规 (m1, m5), 实际: {[(v.lineno, v.snippet) for v in vs]}"
        )

    def test_exemption_comment_skips_violation(self, sample_exempted_file):
        """`# noqa: magicmock-no-spec` 豁免该行."""
        scanner = _import_scanner()
        if scanner is None:
            pytest.skip("TDD red phase: 扫描器未实现")
        vs = scanner.scan_file(sample_exempted_file)
        assert vs == [], (
            f"豁免注释应跳过所有违规, 实际: {[(v.lineno, v.snippet) for v in vs]}"
        )

    def test_partial_exemption_keeps_other_violations(self, tmp_path):
        """只豁免 m1, m2 仍报."""
        scanner = _import_scanner()
        if scanner is None:
            pytest.skip("TDD red phase: 扫描器未实现")
        p = tmp_path / "partial.py"
        p.write_text(
            "from unittest.mock import MagicMock\n"
            "\n"
            "def test_x():\n"
            "    m1 = MagicMock()  # noqa: magicmock-no-spec\n"
            "    m2 = MagicMock()\n",
            encoding="utf-8",
        )
        vs = scanner.scan_file(p)
        assert len(vs) == 1, (
            f"应只剩 m2 违规, 实际: {[(v.lineno, v.snippet) for v in vs]}"
        )

    def test_scan_paths_handles_directory(self, tmp_path):
        """scan_paths 能扫整个目录."""
        scanner = _import_scanner()
        if scanner is None:
            pytest.skip("TDD red phase: 扫描器未实现")
        # 写 2 文件: 1 clean, 1 violating
        (tmp_path / "a.py").write_text(
            "from unittest.mock import MagicMock\n"
            "m = MagicMock(spec=int)\n",
            encoding="utf-8",
        )
        (tmp_path / "b.py").write_text(
            "from unittest.mock import MagicMock\n"
            "m = MagicMock()\n",
            encoding="utf-8",
        )
        vs = scanner.scan_paths([tmp_path])
        assert len(vs) == 1, f"应 1 违规 (b.py), 实际: {len(vs)}"
        assert vs[0].path.name == "b.py"


@pytest.mark.unit
class TestScanCli:
    """CLI: `python -m butler.tests_policies.scan_magicmock_spec <path>`."""

    def test_cli_exit_nonzero_on_violations(self, sample_violating_file):
        """含违规 → exit code != 0 (CI 失败信号)."""
        scanner = _import_scanner()
        if scanner is None:
            pytest.skip("TDD red phase: 扫描器未实现")
        result = subprocess.run(
            [sys.executable, "-m", _SCANNER_MOD, str(sample_violating_file)],
            capture_output=True, text=True,
        )
        assert result.returncode != 0, (
            f"含违规应非 0 exit, 实际 {result.returncode}. "
            f"stdout: {result.stdout!r}, stderr: {result.stderr!r}"
        )

    def test_cli_exit_zero_on_clean(self, sample_clean_file):
        """clean → exit code 0."""
        scanner = _import_scanner()
        if scanner is None:
            pytest.skip("TDD red phase: 扫描器未实现")
        result = subprocess.run(
            [sys.executable, "-m", _SCANNER_MOD, str(sample_clean_file)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"clean 应 0 exit, 实际 {result.returncode}. "
            f"stdout: {result.stdout!r}"
        )

    def test_cli_report_flag(self, sample_violating_file):
        """`--report` 输出人类可读列表."""
        scanner = _import_scanner()
        if scanner is None:
            pytest.skip("TDD red phase: 扫描器未实现")
        result = subprocess.run(
            [sys.executable, "-m", _SCANNER_MOD, str(sample_violating_file), "--report"],
            capture_output=True, text=True,
        )
        assert "MagicMock" in result.stdout or "magicmock" in result.stdout.lower()


# ---------- baseline / regression gate ----------

# Sprint 23 TST-10-6 治理策略 (audit 暂缓项):
# - 全量 614 处 MagicMock() 无 spec= 一次改完风险过大 (跨多模块, 一改全跑测试)
# - 改为: 1) 扫描器落地, 2) 记录 baseline, 3) 不增量 (新加 MagicMock() 必加 spec=)
# - 后续 sprint 每次清理 1-2 个文件
# 该 baseline 由 Sprint 23-1 init 写入; 后续如 < baseline 表示已清理, > baseline 失败.
# 调整时同时清理对应文件 + 更新此数.
# 历史:
#   614 (init)
# → 611 (test_wechat_ilink_inbound: 3 处 _fake_create_task 改 spec=asyncio.Future)
# → 601 (test_workflow_runner: 10 处 WorkflowRunner(orchestrator=MagicMock()) 加 noqa)
# → 584 (test_sprint16_tst11_9_mcp_client_server: 17 处 MCP 加 noqa)
# → 558 (test_sprint16_tst11_10_wechat_ssrf: 26 处 httpx Response/AsyncClient
#        /Session/raise_for_status 加 noqa)
_BASELINE_VIOLATIONS = 558


@pytest.mark.unit
class TestBaselineGate:
    """`tests/` 中 MagicMock() 无 spec= 的违规数必须 ≤ baseline (无增量)."""

    def test_total_violations_not_growing(self):
        """扫描 `tests/` 目录, 违规数 ≤ baseline. 增量失败."""
        scanner = _import_scanner()
        if scanner is None:
            pytest.skip("TDD red phase: 扫描器未实现")
        tests_dir = pathlib.Path(__file__).parent
        vs = scanner.scan_paths([tests_dir])
        # 排除本测试文件自身 (含 scanner 演示 + 注释豁免占位)
        vs = [v for v in vs if v.path.name != pathlib.Path(__file__).name]
        actual = len(vs)
        assert actual <= _BASELINE_VIOLATIONS, (
            f"MagicMock() 违规数从 baseline {_BASELINE_VIOLATIONS} 增到 {actual} "
            f"(+{actual - _BASELINE_VIOLATIONS}). 新增的 MagicMock 调用必须加 spec= "
            f"或用 `# noqa: magicmock-no-spec` 豁免.\n"
            f"前 5 处新违规:\n"
            + "\n".join(v.format_report() for v in vs[:5])
        )

    def test_scanner_files_themselves_clean(self):
        """扫描器自身代码 + 本测试文件不污染 baseline (已用 noqa 豁免)."""
        scanner = _import_scanner()
        if scanner is None:
            pytest.skip("TDD red phase: 扫描器未实现")
        # 直接检查本文件 (测试自身有 1 处显式豁免示范, 用 patch.object 句式)
        vs = scanner.scan_file(pathlib.Path(__file__))
        # 本测试文件可能含 noqa 豁免后仍 0 违规, 也可能根本没 MagicMock
        # 关键是策略文件本身不应有 0 豁免的 MagicMock()
        bad = [v for v in vs if "noqa" not in v.snippet]
        assert bad == [], (
            f"扫描器自身测试文件不应有未豁免的 MagicMock():\n"
            + "\n".join(v.format_report() for v in bad)
        )
