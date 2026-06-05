"""R2-12 [H] mcp_merge state corruption mask — corrupted YAML 被静默吞掉.

`butler/registry/mcp_merge.py` 中 3 个函数 (`_read_server_ids`,
`_read_server_block`, `find_server_config_path`) 在 YAML parse 失败时
都直接返回空 tuple / 空 dict / `continue` — 状态损坏被静默 mask.
后果: 用户 /mcp 状态 显示某层「0 server」但其实是文件被破坏 (崩溃
中途写入 / 手动 edit 错误 / 磁盘错误). 这种状态损坏被 merge 结果
掩盖, 排障极难.

修复:
1. 区分 "file missing" (合法空) vs "parse error" (state corruption)
2. 解析失败 → log at ERROR with exc_info (保留 traceback)
3. 解析失败 → 写入模块级 diagnostics buffer, 供 /诊断 透明
4. Public reader `recent_mcp_merge_corruptions()` 暴露 corruption 列表
5. 行为不变: 仍然返回空 server list (corrupted layer 不贡献 server),
   但 corruption 被记录, 不再 silent mask

行为保证:
1) corrupted YAML → diagnostics buffer 有 entry 含 path/error/type
2) corrupted YAML → log at ERROR with exc_info
3) 缺失 mcp.yaml → 不应记为 corruption (合法)
4) 合法 YAML → diagnostics buffer 保持空
5) /mcp status 命令在 corruption 存在时, 输出应提到 corruption
6) Public reader + reset 接口可独立测试
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from butler.registry import mcp_merge
from butler.registry.mcp_merge import (
    _read_server_block,
    _read_server_ids,
    effective_mcp_servers,
    find_server_config_path,
    list_mcp_config_layers,
    recent_mcp_merge_corruptions,
    reset_mcp_merge_corruptions,
)


@pytest.fixture(autouse=True)
def _reset_corruptions():
    """Reset module-level diagnostics buffer between tests."""
    mcp_merge.reset_mcp_merge_corruptions()
    yield
    mcp_merge.reset_mcp_merge_corruptions()


@pytest.fixture
def ws_with_layers(tmp_path: Path, monkeypatch) -> Path:
    """Provision a workspace with both project + global mcp.yaml.

    Both layers exist and are valid; tests can then corrupt one layer
    and assert diagnostics behavior.
    """
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / ".butler").mkdir()
    (ws / ".butler" / "mcp.yaml").write_text(
        "version: 1\nservers:\n  project_srv:\n    transport: stdio\n"
        "    command: python3\n    args: []\n",
        encoding="utf-8",
    )
    global_cfg = tmp_path / "mcp.yaml"
    global_cfg.write_text(
        "version: 1\nservers:\n  global_srv:\n    transport: stdio\n"
        "    command: npx\n    args: []\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BUTLER_MCP_CONFIG", str(global_cfg))
    return ws


# -----------------------------------------------------------------------
# Test 1: corrupted project YAML is recorded in diagnostics
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestCorruptionRecorded:
    """corrupted YAML 必须被记录到 diagnostics buffer."""

    def test_read_server_ids_corruption_recorded(
        self, ws_with_layers: Path, caplog
    ):
        """project mcp.yaml 损坏时, _read_server_ids 记录 corruption."""
        proj_yaml = ws_with_layers / ".butler" / "mcp.yaml"
        proj_yaml.write_text("servers: [unclosed", encoding="utf-8")

        with caplog.at_level(logging.ERROR, logger="butler.registry.mcp_merge"):
            ids = _read_server_ids(proj_yaml)

        assert ids == (), (
            f"损坏 YAML 应返回空 tuple, 实际: {ids!r}"
        )
        corruptions = recent_mcp_merge_corruptions()
        assert len(corruptions) == 1, (
            f"损坏必须记入 diagnostics, 实际: {corruptions!r}"
        )
        entry = corruptions[0]
        assert entry["path"] == str(proj_yaml)
        assert entry["error"], "corruption 记录必须含 error 字符串"
        assert entry["type"], "corruption 记录必须含 exception type"
        # yaml.parser.ParserError / ScannerError / YAMLError 都表明是 YAML 损坏
        assert "YAML" in entry["type"] or "yaml" in entry["type"].lower() or "Parser" in entry["type"] or "Scanner" in entry["type"], (
            f"type 应反映 YAML 解析异常, 实际 type={entry['type']!r}"
        )

    def test_read_server_block_corruption_recorded(
        self, ws_with_layers: Path, caplog
    ):
        """project mcp.yaml 损坏时, _read_server_block 记录 corruption."""
        proj_yaml = ws_with_layers / ".butler" / "mcp.yaml"
        proj_yaml.write_text("servers:\n  demo: [broken", encoding="utf-8")

        with caplog.at_level(logging.ERROR, logger="butler.registry.mcp_merge"):
            block = _read_server_block(proj_yaml, "demo")

        assert block == {}, (
            f"损坏 YAML 应返回空 dict, 实际: {block!r}"
        )
        corruptions = recent_mcp_merge_corruptions()
        assert len(corruptions) == 1, (
            f"损坏必须记入 diagnostics, 实际: {corruptions!r}"
        )
        assert corruptions[0]["path"] == str(proj_yaml)

    def test_find_server_config_path_corruption_recorded(
        self, ws_with_layers: Path, caplog
    ):
        """project mcp.yaml 损坏时, find_server_config_path 记录 corruption
        但仍能定位到 global 路径 (因为 project 那层被 skip, global 仍能匹配)."""
        proj_yaml = ws_with_layers / ".butler" / "mcp.yaml"
        proj_yaml.write_text("servers: [unclosed", encoding="utf-8")
        # 找 'global_srv' (只在 global), corruption 不应阻塞查找
        with caplog.at_level(logging.ERROR, logger="butler.registry.mcp_merge"):
            result = find_server_config_path("global_srv", workspace=ws_with_layers)
        assert result is not None, (
            "损坏的 project layer 不应阻塞查找 global server"
        )
        corruptions = recent_mcp_merge_corruptions()
        assert any(
            str(proj_yaml) in c["path"] for c in corruptions
        ), f"project YAML 损坏未记入 diagnostics: {corruptions!r}"


# -----------------------------------------------------------------------
# Test 2: missing YAML is NOT corruption
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestMissingFileIsNotCorruption:
    """缺失 mcp.yaml 是合法空配置, 不应记入 corruption."""

    def test_missing_project_yaml_no_corruption(self, ws_with_layers: Path):
        ws_with_layers_rm = ws_with_layers  # alias
        (ws_with_layers_rm / ".butler" / "mcp.yaml").unlink()

        # 现在只有 global layer, _read_server_ids(global_path) 应不记 corruption
        global_yaml = ws_with_layers_rm.parent / "mcp.yaml"
        ids = _read_server_ids(global_yaml)
        assert ids == ("global_srv",)
        assert recent_mcp_merge_corruptions() == [], (
            f"缺失文件不应记为 corruption, 实际: {recent_mcp_merge_corruptions()!r}"
        )

    def test_missing_file_returns_empty_cleanly(self, tmp_path: Path):
        """完全不存在的路径 → 返回空, 不记 corruption."""
        missing = tmp_path / "nope.yaml"
        assert _read_server_ids(missing) == ()
        assert _read_server_block(missing, "anything") == {}
        assert recent_mcp_merge_corruptions() == []


# -----------------------------------------------------------------------
# Test 3: valid YAML is not corruption
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestValidYamlClean:
    """合法 YAML 不应污染 diagnostics buffer."""

    def test_valid_project_layer_clean(self, ws_with_layers: Path):
        ids = _read_server_ids(ws_with_layers / ".butler" / "mcp.yaml")
        assert ids == ("project_srv",)
        assert recent_mcp_merge_corruptions() == []


# -----------------------------------------------------------------------
# Test 4: ERROR log with exc_info
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestErrorLogHasExcInfo:
    """corruption 必须 log at ERROR with exc_info (保留 traceback)."""

    def test_corruption_logs_error_with_exc_info(
        self, ws_with_layers: Path, caplog
    ):
        proj_yaml = ws_with_layers / ".butler" / "mcp.yaml"
        proj_yaml.write_text("servers: [unclosed", encoding="utf-8")

        with caplog.at_level(logging.DEBUG, logger="butler.registry.mcp_merge"):
            _read_server_ids(proj_yaml)

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, (
            "corruption 必须 log at ERROR, "
            f"实际 records: {[(r.levelname, r.message) for r in caplog.records]}"
        )
        assert any(r.exc_info is not None for r in error_records), (
            "corruption 的 ERROR log 必须含 exc_info (traceback)"
        )


# -----------------------------------------------------------------------
# Test 5: effective_mcp_servers behavior under corruption
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestEffectiveUnderCorruption:
    """corruption 不应阻塞有效 server 列表, 但 corruption 必须被记下."""

    def test_effective_servers_skips_corrupted_layer_but_logs(
        self, ws_with_layers: Path, caplog
    ):
        """project layer 损坏 → effective 不含 project_srv, 但 global_srv 在;
        diagnostics 记下 project 损坏."""
        proj_yaml = ws_with_layers / ".butler" / "mcp.yaml"
        proj_yaml.write_text("servers: [unclosed", encoding="utf-8")

        with caplog.at_level(logging.ERROR, logger="butler.registry.mcp_merge"):
            effective = effective_mcp_servers(workspace=ws_with_layers)

        ids = {r.server_id for r in effective}
        assert "project_srv" not in ids, (
            "损坏 layer 不应贡献 server"
        )
        assert "global_srv" in ids, (
            "global layer 仍应贡献 server (corruption 不阻塞其他 layer)"
        )
        corruptions = recent_mcp_merge_corruptions()
        assert any(
            str(proj_yaml) in c["path"] for c in corruptions
        ), "project layer 损坏未记入 diagnostics"

    def test_list_layers_corruption_logged(
        self, ws_with_layers: Path, caplog
    ):
        """list_mcp_config_layers 也走相同读路径, 损坏必须被记下."""
        proj_yaml = ws_with_layers / ".butler" / "mcp.yaml"
        proj_yaml.write_text("servers: [unclosed", encoding="utf-8")

        with caplog.at_level(logging.ERROR, logger="butler.registry.mcp_merge"):
            layers = list_mcp_config_layers(workspace=ws_with_layers)

        # corrupted project layer 仍出现在 layers 列表里 (path 正确),
        # 但 server_ids 应为空 (无法解析)
        proj_layer = next(
            (l for l in layers if l.label == "project"), None
        )
        assert proj_layer is not None, "project layer 应仍在 layers 列表里"
        assert proj_layer.server_ids == (), (
            f"损坏 layer server_ids 应为空, 实际: {proj_layer.server_ids!r}"
        )
        corruptions = recent_mcp_merge_corruptions()
        assert any(
            str(proj_yaml) in c["path"] for c in corruptions
        )


# -----------------------------------------------------------------------
# Test 6: Public reader API
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestPublicReader:
    """Public reader / reset 必须存在并可独立测试."""

    def test_reader_returns_empty_initially(self):
        assert isinstance(recent_mcp_merge_corruptions(), list)
        assert recent_mcp_merge_corruptions() == []

    def test_reset_clears_buffer(self, ws_with_layers: Path):
        proj_yaml = ws_with_layers / ".butler" / "mcp.yaml"
        proj_yaml.write_text("servers: [unclosed", encoding="utf-8")
        _read_server_ids(proj_yaml)
        assert recent_mcp_merge_corruptions()
        reset_mcp_merge_corruptions()
        assert recent_mcp_merge_corruptions() == []

    def test_buffer_is_bounded(self, ws_with_layers: Path, monkeypatch):
        """buffer 满后按 FIFO 丢弃旧 entry (防止长会话无限增长)."""
        from butler.registry import mcp_merge as mm
        original_cap = mm._MAX_MCP_MERGE_CORRUPTION_ENTRIES
        mm._MAX_MCP_MERGE_CORRUPTION_ENTRIES = 3
        try:
            proj_yaml = ws_with_layers / ".butler" / "mcp.yaml"
            proj_yaml.write_text("servers: [unclosed", encoding="utf-8")
            for _ in range(5):
                _read_server_ids(proj_yaml)
                mm._mcp_merge_corruptions.clear()  # simulate continuous ingest
            # 单独再写 5 个不同的 path, 验证 cap 行为
            for i in range(5):
                f = ws_with_layers / f"bad_{i}.yaml"
                f.write_text("[unclosed", encoding="utf-8")
                _read_server_ids(f)
            assert len(recent_mcp_merge_corruptions()) <= 3, (
                f"buffer 满后应按 cap 截断, 实际: {len(recent_mcp_merge_corruptions())}"
            )
        finally:
            mm._MAX_MCP_MERGE_CORRUPTION_ENTRIES = original_cap
