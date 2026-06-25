# Observation Store 与 PreRead 排序（2026-06）

> **SSOT 实现**：`butler/memory/observation_store.py`、`butler/memory/observer_queue.py`、`butler/core/preread_context.py`  
> **产品 Backlog**：[PROD-P2-02](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md#prod-p2-02observation-store-收口)

## 存储位置

| 产物 | 路径 | 说明 |
|------|------|------|
| SQLite 主库 | `<workspace>/.butler/observations.db` | PostToolUse 路径观察（当前 SSOT） |
| 遗留 TSV | `<workspace>/.butler/observations.tsv` | 早期试用格式；**一次性**迁入 DB 后重命名为 `observations.tsv.migrated` |

迁移：

```bash
# 项目 workspace 下（DB 空且 TSV 存在时自动导入）
butler memory observations --workspace /path/to/project --migrate

# 或脚本
bash scripts/butler-observation-migrate.sh --workspace /path/to/project
```

## 写入开关

| 变量 | 默认 | 作用 |
|------|------|------|
| `BUTLER_MEMORY_OBSERVER_QUEUE` | `0` | `1` 时 PostToolUse → 内存队列 → flush 到 `observations.db` |
| `BUTLER_OBSERVATION_TTL_DAYS` | `90` | 超期行 prune |
| `BUTLER_MEMORY_OBSERVATION_MAX_ROWS` | `0` | 全局行数上限（`0`=关） |
| `BUTLER_PREREAD` | 见 `reference.md` | PreRead 注入 `read_file` 前路径历史块 |

## PreRead 排序权重（当前）

**仅时间最近优先**，无工具类型 / 成功率 / 频次加权。

1. **路径匹配**（`list_for_path`）：`file_path` 与行内 `path` 双向子串匹配（`LIKE '%path%'`）。
2. **排序**：`ORDER BY timestamp DESC, row_id DESC`。
3. **截断**：默认 `limit=3`（`build_preread_block`）。
4. **展示顺序**：查询结果 **reverse** 为时间升序，PreRead 块自上而下为「较早 → 较近」。
5. **去重**：同 `(session_key, tool, path, content_hash)` 仅保留最新一行（`INSERT OR REPLACE` + 唯一索引）。

### 未来可扩展（未实现）

| 信号 | 状态 |
|------|------|
| 工具类型权重（如 `read_file` > `grep`） | Backlog |
| `ok=0` 降权或标注 | Backlog |
| 同路径访问频次 | Backlog |

变更排序逻辑时须同步本页与 `tests/test_observation_store.py`。

## 诊断与只读导出

- **微信**：`/诊断 详细` → 「Observation Store」段（行数、工具 Top、时间窗、PreRead 说明）。
- **CLI**：

```bash
butler memory observations --project LingWen1
butler memory observations --workspace /path/to/ws --json
```

## 相关测试

```bash
PYTHONPATH=. pytest tests/test_observation_store.py tests/test_observation_migrate.py -q
```
