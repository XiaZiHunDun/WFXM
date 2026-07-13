# LingWen1 docs 归档总索引

> **统一规则**：所有一次性产物（验收戳、对比报告、单次 fixture 样本、阶段调试稿）
> 迁入此目录，保留历史便于回溯。**勿**从归档内容复活待办或推断当前模块路径。

## 子目录

| 子目录 | 内容 | SSOT 替代 |
|--------|------|-----------|
| [`dev-flywheel/`](dev-flywheel/) | dev 飞轮调试稿（handler sim / CLI verify 中间稿，2026-06-23 整理） | 上级 [`../pilot-log.md`](../pilot-log.md)（gitignored） |
| [`2026-05-06-acceptance/`](2026-05-06-acceptance/) | P0/P1 阶段验收报告、单次审计、CC vs Cursor 对比（2026-05–06） | 上级 [`../pilot-log.md`](../pilot-log.md)（gitignored）· [`../../../docs/plans/archive/consolidation-2026-05.md`](../../../docs/plans/archive/consolidation-2026-05.md) · [`../../../docs/plans/decisions/dev-capability-ceiling-vs-cc-cli-2026-06.md`](../../../docs/plans/decisions/dev-capability-ceiling-vs-cc-cli-2026-06.md) |
| [`ext5-fixture/`](ext5-fixture/) | EXT-5 MarkItDown MCP 验收 fixture 样本（一次性） | [`../../../tests/corpus/suites/ext5/`](../../../tests/corpus/suites/ext5/) |

## 子目录文件清单

### `dev-flywheel/`

- `README.md` — 归档说明（指向 SSOT）
- `dev-flywheel-role-debug.md` — role=dev 委派调试
- `dev-flywheel-role-debug2.md` — 同上，第二轮
- `dev-flywheel-cli-verify.md` — CLI verify 对齐笔记
- `dev-flywheel-role-sim-2026-06-23.md` — sim 会话记录

### `2026-05-06-acceptance/`

- `lead-phase1-check.md` — 2026-05-22 P0 阶段验收戳
- `consolidation-audit-2026-06-23.md` — 2026-06-23 全仓审计（一次性）
- `dev-cc-head-to-head.md` — CC vs Cursor 一次性对比
- `dev-flywheel-2026-06-23.md` — 2026-06-23 dev 飞轮验收戳（仅一行）
- `紫罗兰-42 验收报告.md` — 2026-06-23 紫罗兰-42 测试代号单次验收

### `ext5-fixture/`

- `ext5-fixture-sample.md` — MarkItDown MCP golden smoke 样本
- `ext5-fixture-sample.txt` — 同上，文本版

## 何时新增归档子目录

- 单次验收报告（带日期戳）→ `YYYY-MM-acceptance/` 或合并到 `2026-MM-acceptance/`
- 阶段性调试稿（handler sim、CLI verify 等）→ 按主题（如 `dev-flywheel/`）
- 单次 fixture 样本 → 按主题（如 `ext5-fixture/`）

**禁止**把活跃 SSOT、长期维护文档、配置文件移入 archive。