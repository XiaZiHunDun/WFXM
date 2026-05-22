# 记忆双轨统一 — 实施方案（2026-05-22）

> **状态**：M1–M4 已完成  
> **深度分析**：[`p3-deferred-deep-dive-2026-05.md`](p3-deferred-deep-dive-2026-05.md) §1  
> **原则**：磁盘格式不变；`<memory-context>` 注入格式不变；每阶段 pytest + full smoke

---

## 1. 目标

消除 `ButlerOrchestrator.butler_memory` 与 `memory_provider._butler_global` 双实例，使：

- 工具 `butler_remember` / `butler_recall`
- 轮次预取 `prefetch_turn_memory`
- post_session（provider 缓冲 + `/new` trigger）
- `/诊断` 记忆层统计

读写 **同一组** `ButlerMemory` / `ProjectMemory` 对象。

---

## 2. 范围

| 阶段 | 本方案 | 行为变更 | 说明 |
|------|--------|----------|------|
| **M1** | ✅ 实施 | 无 | `link_orchestrator` + reload 走编排器引用 |
| **M2** | ✅ 实施 | 无（网关仍用 session_lifecycle） | `prefetch()` 委托 `prefetch_turn_memory` |
| **M3** | ✅ 实施 | `/new` 仅提炼未增量部分 | 水印 + 单 runner + 互斥锁 |
| **M4** | ✅ 实施 | 无 | 实现迁至 `memory/facade.py`，`memory_plugin` 为 re-export |

**不在本轮**：改 M1–M4 微信命令、语义索引格式、env 开关默认值。

---

## 3. M1 — 单实例绑定

### 3.1 设计

```text
ButlerOrchestrator.__init__
  → memory_provider = ButlerMemoryService()
  → provider.link_orchestrator(self)
  → provider.initialize(...)

ButlerMemoryService._reload_butler_global:
  if _orchestrator: _butler_global = orch.butler_memory
  else: 原逻辑（独立测试/工具 fallback）

ButlerMemoryService._reload_project_branch:
  if _orchestrator: _project_memory = orch._project_memory; _project_root = workspace
  else: 原逻辑

on_project_switch:
  _reload_project_memory() → _refresh_memory_provider() → reload 自动跟编排器
```

### 3.2 改动文件

| 文件 | 变更 |
|------|------|
| `butler/memory_plugin.py` | `link_orchestrator`、reload 分支 |
| `butler/orchestrator.py` | init / refresh 调用 link |
| `butler/tools/memory_tools.py` | 有 provider 时不再单独 `_reload_*`（可选：改调 `sync`） |
| `tests/test_memory_unification.py` | **新建** 单实例断言 |

### 3.3 验收

```bash
PYTHONPATH=. pytest tests/test_memory_unification.py tests/test_orchestrator.py -q
PYTHONPATH=. pytest -q
bash scripts/butler-smoke.sh --tier=full
```

断言：`id(orch.butler_memory) == id(orch.memory_provider._butler_global)`；有项目时 `id(orch._project_memory) == id(provider._project_memory)`。

---

## 4. M2 — 预取单点

### 4.1 设计

`ButlerMemoryService.prefetch(query)`：

- 已 `link_orchestrator` → `session_lifecycle.prefetch_turn_memory(orch, query)`
- 未 link → 保留原 FTS 实现（独立单测/fallback）

网关主路径不变（仍 `attach_turn_memory_prefetch`）；消除 plugin 内第二套预取逻辑的阅读/误用风险。

### 4.2 验收

- `tests/test_project_facts_prefetch.py`、`test_semantic_memory_p1.py` 仍绿
- 若存在直接调用 `provider.prefetch` 的测试，输出应与 `prefetch_turn_memory` 一致（link 后）

---

## 5. M3 — post_session 单策略（已完成）

### 5.1 设计

- **单入口**：`session_lifecycle.run_post_session_extraction`（`_POST_SESSION_LOCK` + `orchestrator._skill_manager`）
- **增量**：`record_post_session_turn` 缓冲，达 `BUTLER_POST_SESSION_BUFFER_MESSAGES`（默认 8）后台提炼并 **水印 +N 轮**
- **会话结束**：`trigger_session_end` 仅处理 `loop.messages` 中 **水印之后** 的 user/assistant；随后 `reset_post_session_watermark`
- **`/new` 清理**：`clear_session_boundary_memory` 清空缓冲 + 水印

### 5.2 行为说明（release note）

- 长对话中仍会每 8 条消息触发一次增量提炼（与原先一致）。
- `/新对话` 不再对 **已增量提炼过的轮次** 重复跑 post_session，避免双倍 LLM/写入。
- 未 link orchestrator 的独立 `ButlerMemoryService` 仍走 standalone 缓冲（测试兼容）。

### 5.3 改动文件

| 文件 | 变更 |
|------|------|
| `butler/session_lifecycle.py` | runner、水印、buffer、重写 `trigger_session_end` |
| `butler/memory_plugin.py` | `sync_turn` 委托 `record_post_session_turn` |
| `tests/test_post_session_unification.py` | M3 回归 |

## 6. M4 — Facade 瘦身（已完成）

- 实现位于 `butler/memory/facade.py`（`ButlerMemoryService` / `ButlerMemoryProvider`）
- `butler/memory_plugin.py` 仅 re-export（测试与外部 import 兼容）
- `butler.orchestrator`、`butler.tools.memory_tools` 改为 `from butler.memory.facade import …`
- `butler.memory` 包可通过 `ButlerMemoryService` 懒加载访问
- standalone post_session 改走 `run_post_session_extraction`（与 M3 单 runner 一致）

---

## 7. 回滚

- M1/M2 可单独 revert `link_orchestrator` 与 prefetch 委托，无数据迁移。
- 若 M3 已上线，回滚需检查是否有重复提炼的行（experience 去重工具不在本轮）。

---

## 8. 执行记录

| 日期 | 阶段 | 结果 |
|------|------|------|
| 2026-05-22 | 方案 | 本文档 |
| 2026-05-22 | M1 | `link_orchestrator`；reload 走编排器引用；5 项单测 |
| 2026-05-22 | M2 | `prefetch()` 委托 `prefetch_turn_memory`（link 时） |
| 2026-05-22 | M3 | 单 runner + 水印去重 + `test_post_session_unification.py` |
| 2026-05-22 | 验收 M1–M2 | pytest **1097** passed；full smoke 全绿 |
| 2026-05-22 | 验收 M3 | pytest **1101** passed；standard smoke 全绿 |
| 2026-05-22 | M4 | `memory/facade.py` + 薄 `memory_plugin` re-export |
| 2026-05-22 | 验收 M4 | pytest **1103** passed；`test_memory_facade_import.py` |
