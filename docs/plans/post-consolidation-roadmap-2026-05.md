# Butler 后续规划（整理完成后）

> **状态**：活跃规划（2026-05-22）  
> **前置**：[`consolidation-2026-05.md`](consolidation-2026-05.md) P0–P2 已完成；**`reference/` 仍由主公维护，不在此规划改动范围内。**  
> **基线**：pytest **1110 passed**；`bash scripts/butler-smoke.sh --tier=full` 全绿。  
> **P3 未做项深度分析**：[`p3-deferred-deep-dive-2026-05.md`](p3-deferred-deep-dive-2026-05.md)  
> **记忆 M1–M2**：[`memory-unification-implementation-2026-05.md`](memory-unification-implementation-2026-05.md)

---

## 1. 当前站位

| 维度 | 结论 |
|------|------|
| 平台 v4 | 微信网关 + 自建 Agent Loop + 项目/Lead/runtime 已落地 |
| 灵文1号 | **通过、可运营**（见 [`projects/LingWen1/docs/pilot-log.md`](../../projects/LingWen1/docs/pilot-log.md)） |
| Lead / 记忆 / 开发工具 | 阶段 0–3、记忆 P0–P2、dev-ops P0–P1 已验收 |
| 第二样板 | `演示试点`（DemoPilot，`knowledge-light` / software 模板） |
| 仓库整理 | 脉络清晰；v1 在标签 `archive/butler-v1-20260522` |

**整理阶段刻意不做**：大改 Loop/网关架构、动 `reference/`、改 `novel-factory/` 领域脚本逻辑。

---

## 2. 轨道与优先级

### 轨道 A — 运营巩固（建议先做）

| ID | 项 | 验收 |
|----|-----|------|
| A1 | 首周观察 `consistency-weekly` 微信摘要 + 推送限流 | 日志/真机记录 |
| A2 | 入站媒体真机（M-img / M-voice） | [`wechat-daily-smoke-checklist.md`](../guides/wechat-daily-smoke-checklist.md) 补勾 |
| A3 | mutating runtime 批准链走一遍（`publish-archive` 等，验完即关） | audit + 微信确认 |
| A4 | 发版节奏：`--tier=standard` 日常；`--tier=full` 发版 | 团队约定 |

### 轨道 B — 灵文单项目样板（项目层 P0 余量）

| ID | 项 | 验收 |
|----|-----|------|
| B1 | **维护态 / 新书态** 双剧本写入 `pilot-setup.md`（与 Lead Skill 一致） | 文档 + 微信各测一句 |
| B2 | 微信「测试」闭环：runtime 只读 job 或委派 dev `pytest` | Lead 不亲自 `terminal` |
| B3 | Lead 触发 `publish-preflight` 等只读 job 场景复验 | runtime audit |
| B4 | 试点文档收口（验收步骤集中在 `pilot-setup.md`） | 无散落重复清单 |

### 轨道 C — 多项目与接入（中期）

| ID | 项 | 验收 |
|----|-----|------|
| C1 | Git `butler project register` + 外部 repo 试点 | preflight 无 FAIL + 微信 `/切换` |
| C2 | 默认项目：`BUTLER_DEFAULT_PROJECT` vs per-chat 绑定策略文档化 | `/诊断` 可读 |
| C3 | Lead 配置化：多项目 `lead: true` + `*-project-lead` Skill | 第二 Lead 项目 smoke |
| C4 | 新建选 `pack` 模板，避免复制灵文整包 | `/项目 新建` + archetype |

### 轨道 D — 配置与体验（按需）

| ID | 项 | 验收 |
|----|-----|------|
| D0 | **记忆双轨合并** M1–M4 ✅（见 [`memory-unification-implementation-2026-05.md`](memory-unification-implementation-2026-05.md)） | facade + 单实例 + 去重 post_session |
| D0b | **`/health` 诊断格式化抽取** ✅（[`health-report-refactor-2026-05.md`](health-report-refactor-2026-05.md)） | `ops/health_report.py` |
| D0c | **微信 `/steer`** ✅（[`wechat-steer-implementation-2026-05.md`](wechat-steer-implementation-2026-05.md)） | 按 session 分桶 + sessionless |
| D1 | 代码层读 `config.yaml` 稳定项（runtime/记忆开关等） | env 仅密钥 |
| D2 | 识图 P3：无 OpenAI 时 MiniMax VLM / 本地 OCR | [`wechat-inbound-media.md`](../architecture/wechat-inbound-media.md) |
| D3 | 主机工具远期：`terminal` 白名单调 Claude Code 等 | ADR 修订后实施 |

### 轨道 E — 明确不做

- 外部云记忆（Honcho/Mem0）为默认 — 见 [`memory-roadmap.md`](../architecture/memory-roadmap.md)
- 全书正文向量索引
- 平台 7×24 无人值守跑完全厂 25 步
- 每项目独立微信 Bot
- 修改 `reference/` 目录策略

---

## 3. 推荐实施顺序

```text
A（运营巩固）→ B（灵文样板）→ C.1（Git 试点）→ C.2–C.4（多项目）→ D（按需）
```

与 [`project-layer-wechat-plan.md`](../architecture/project-layer-wechat-plan.md) §7 对照：preflight、archetype、微信 `/项目` 已落地；**剩余主要是 §5 灵文余量 + §6 多项目 + Git 试点**。

---

## 4. 文档与工程小债

| 项 | 说明 |
|----|------|
| pytest 基线 | 全仓统一 **1110**（含 steer session 测） |
| 发版冒烟 | 9 步 `butler-pre-release-smoke.sh`；日常可用 `butler-smoke.sh` |
| v1 源码 | `git archive archive/butler-v1-20260522 archive/butler-v1` |

---

## 5. 相关文档

- [`reviews/project-assessment-2026-05.md`](../reviews/project-assessment-2026-05.md)  
- [`guides/project-onboarding.md`](../guides/project-onboarding.md)  
- [`architecture/project-lead-decision.md`](../architecture/project-lead-decision.md)  
- [`projects/LingWen1/docs/pilot-setup.md`](../../projects/LingWen1/docs/pilot-setup.md)
