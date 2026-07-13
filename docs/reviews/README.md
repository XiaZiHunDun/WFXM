# 阶段性评估索引

> 多次 subagent-driven 深度审计（安全 / 性能 / 可靠性 / 测试覆盖 / 死代码）。
> **非实现规范** — 这些报告找问题、记结论；当前状态以 [`docs/architecture/v4-architecture.md`](../architecture/v4-architecture.md) 与代码为准。

## 主报告

| 文档 | 范围 | 说明 |
|------|------|------|
| [`project-deep-audit-2026-06.md`](project-deep-audit-2026-06.md) | Butler v4 全栈（Sprint 7 启动） | 主报告 + 8 轮 subagent 检查汇总 |

## Sprint 续审（基线累积）

| 文档 | 范围 | 上游基线 |
|------|------|----------|
| [`project-deep-audit-2026-06-r1to8.md`](project-deep-audit-2026-06-r1to8.md) | R1–R8 子报告合并（2026-06-05 收口） | 主报告 R1-R8 |
| [`project-deep-audit-2026-06-sprint8.md`](project-deep-audit-2026-06-sprint8.md) | Sprint 8 续审 | 主报告 + Sprint 7 修复 10 项后 |
| [`project-deep-audit-2026-06-sprint9.md`](project-deep-audit-2026-06-sprint9.md) | Sprint 9 续审（5 CRITICAL 复检） | Sprint 8 修复 6 项后 |
| [`project-deep-audit-2026-06-sprint10.md`](project-deep-audit-2026-06-sprint10.md) | Sprint 10 续审（450 Python + 274 test） | Sprint 9 修复 5 CRITICAL 后 |
| [`project-deep-audit-2026-06-sprint11.md`](project-deep-audit-2026-06-sprint11.md) | Sprint 11 续审（最新基线） | Sprint 10 修复 5 CRITICAL 后 |

## 流程

每轮 4 个并行 subagent（security / performance / reliability / test+dead code）→ 主线程独立 grep/sed 复检 CRITICAL 项 → 仅记录确认问题。

## 相关

- 文档体系：[`../DOCUMENTATION.md`](../DOCUMENTATION.md) §1 L5 历史层级说明（reviews 在 L3–L4 之间）
- 当前架构：[`../architecture/v4-architecture.md`](../architecture/v4-architecture.md)