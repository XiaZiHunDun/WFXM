# ADR — 多项目记忆作用域（L3/L4 编码经验层）

> **状态**：已采纳（2026-06-13）| **阶段**：P0 数据模型落地中  
> **理论 SSOT**：[`v4-memory-theory.md`](../../architecture/v4-memory-theory.md)（M8 扩展）  
> **实现 SSOT**：`butler/memory/memory_scope.py`、`butler/dev_engine/coding_knowledge.py`  
> **边界**：不合并 Owner 叙事经验（`experience.db`）与编码 pattern；不引入 SQL 会话库 / Redis

---

## 1. 问题

- Lead 侧记忆已有 **Tenant / Project 双域**（MT3）。
- Dev 委派侧 **`~/.butler/coding_experiences.json` 为租户级全局池**，`process_task()` 仅关键词检索，**不按 project 过滤**。
- 灵文 `B9_EX_prod_lingwen_*` 与通用 `B9_EX_*` 同池竞争；多项目扩展时存在 **跨项目污染** 风险。

## 2. 决策

在 M8 上扩展两层编码经验：

| 层 | 名称 | SSOT | 消费者 |
|----|------|------|--------|
| **L3** | Project Dev Experience | `{workspace}/.butler/memory/coding_experiences.json` | `delegate_task` dev（本项目优先） |
| **L4** | Tenant Dev Corpus | `~/.butler/coding_experiences.json` | B9 课表、已晋升 global/stack 模式 |

**不合并物理文件**；通过 `MemoryScope` + 检索路由统一行为。

### 2.1 MemoryScope 字段

| 字段 | 取值 | 含义 |
|------|------|------|
| `level` | `tenant` \| `project` | 条目主存储域 |
| `project_id` | 项目注册名 | `private` 时必填 |
| `visibility` | `private` \| `global` \| `stack` | 委派检索可见性 |
| `stack_tags` | 如 `python`, `novel-factory` | `stack` 可见性匹配 |
| `source` | `b9`, `prod_failure`, `mining`, `promoted`, `manual` | 审计 / 晋升 |

### 2.2 委派 dev 检索顺序（P2 接线）

1. L3 本项目 `coding_experiences.json`
2. L4 租户库中 `visibility∈{global, stack∩project.tags}`
3. L5 Observation（workspace 已有）
4. Skills：project → tenant catalog

**禁止**：其他项目 `private` 条目；默认不向 Lead 注入 L3/L4 pattern。

### 2.3 写入与晋升

| 事件 | 默认写入 | visibility |
|------|----------|------------|
| 项目 prod 失败 | L3 | `private` |
| B9 oracle / 周循环 | L4 | `global` |
| 经验挖掘 | 待审 → L3 | 批准后可选 promote → L4 |
| 跨项目复用 | — | 须 **显式 promote** 为 `global` 或 `stack` |

## 3. 实施阶段

| 阶段 | 内容 | 状态 |
|------|------|------|
| **P0** | `MemoryScope` + `CodingExperience.scope` + JSON 序列化 + legacy backfill | ✅ |
| **P1** | `ExperienceLibrary.load_merged_for_project()` | ✅ |
| **P2** | `delegate_phases` 传入 `project_id` / `stack_tags`；`search` 硬过滤 | ✅ |
| **P3** | prod 失败写 L3；`b9_lessons` 带 `project` | ✅ |
| **P4** | `/诊断` + `butler memory diagnose --project` | ✅ |
| **P5** | 灵文 private 条目迁 L3 或保持 L4+scope | 待办 |

## 4. 守门

```bash
PYTHONPATH=. pytest tests/test_memory_scope_diagnostics.py tests/test_memory_scope.py tests/test_production_failure_experience.py -q
butler memory diagnose --project 灵文1号
```

## 5. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-06-13 | 初版 ADR；主公认可六层模型与晋升路径 |
