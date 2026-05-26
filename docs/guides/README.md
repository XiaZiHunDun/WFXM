# 指南文档索引

> 更新：2026-05-25 | 个人助手 Butler：**主场景为微信**；CLI 为本地开发与调试。  
> 文档体系：[`../DOCUMENTATION.md`](../DOCUMENTATION.md) · 发版：[`release-runbook-2026-05.md`](./release-runbook-2026-05.md) · 否决/Backlog：[`../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md`](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md)  
> 四报告 Sprint A–D 总索引：[sprint-roadmap-2026-05.md](./sprint-roadmap-2026-05.md)

| 文档 | 用途 |
|------|------|
| [release-runbook-2026-05.md](./release-runbook-2026-05.md) | **发版一条链**（preflight → smoke → 部署 → 真机） |
| [capabilities-index-2026-05.md](./capabilities-index-2026-05.md) | 已落地能力总索引（env / 守门） |
| [wechat-gateway-ops.md](./wechat-gateway-ops.md) | **生产运维**：systemd 安装、发版、日志、排障 |
| [opencode-parity.md](./opencode-parity.md) | **OpenCode 对标速查**：slash、异步委派、transcript、env 验收 |
| [external-reference-roadmap-2026-05.md](./external-reference-roadmap-2026-05.md) | **外部对标验收索引**（阶段 A/B/C 已落地；defer 见 deferred） |
| [../plans/roadmap-backlog-and-boundaries-2026-05.md](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md) | **否决 / 深化边界 / 可选 Backlog**（提需求先读） |
| [five-reports-capabilities-2026-05.md](./five-reports-capabilities-2026-05.md) | **五报告 PR-F + P5–P10** 已落地速查 |
| [phase-abc-external-reference.md](./phase-abc-external-reference.md) | **阶段 A/B/C** 合并验收（网关、安全、工程化） |
| [external-reference-deferred-2026-05.md](./external-reference-deferred-2026-05.md) | 补做项与仍 defer 项分析 |
| [phase-d-prompt-corpus.md](./phase-d-prompt-corpus.md) | **Prompt Corpus 线**：工具 DSL、/规划、transcript 事件、大文件读、task_milestone |
| [four-reports-capabilities-2026-05.md](./four-reports-capabilities-2026-05.md) | **四报告 PR1–PR6 已落地**速查（RAG / Loop / DESIGN / 实验） |
| [external-agent-reports-capabilities-2026-05.md](./external-agent-reports-capabilities-2026-05.md) | **外部五报告 PR-X + M** 速查（workflow/Loop/MCP/schema） |
| [workflow-variable-precedence.md](./workflow-variable-precedence.md) | Workflow `{{var}}` 变量 precedence |
| [sprint-roadmap-2026-05.md](./sprint-roadmap-2026-05.md) | **四报告 Sprint A–D** 总索引（Firecrawl / agency / Gemini / awesome） |
| [sprint-a-firecrawl-gemini-2026-05.md](./sprint-a-firecrawl-gemini-2026-05.md) | **Sprint A**：external_id 幂等、task stale、恢复分桶、tool masking |
| [sprint-bcd-agency-awesome-2026-05.md](./sprint-bcd-agency-awesome-2026-05.md) | **Sprint B–D**：Handoff、dev-qa-loop、MCP profiles、RAG、web_fetch、委派并发 |
| [sprint-codex-c0-2026-05.md](./sprint-codex-c0-2026-05.md) | **Sprint Codex-C0**：命令归一化、mid-turn 压缩、execpolicy、auto_review |
| [sprint-codex-c1-2026-05.md](./sprint-codex-c1-2026-05.md) | **Sprint Codex-C1**：压缩后 steer、MCP 审批、goal 预算、tool orchestrator |
| [sprint-codex-c2-2026-05.md](./sprint-codex-c2-2026-05.md) | **Sprint Codex-C2**：remote compact、transcript 记忆、user fork、thread_item 事件 |
| [../plans/codex-butler-comparison-2026-05.md](../plans/comparisons/codex-butler-comparison-2026-05.md) | Codex ↔ Butler 全量对照（C0–C2 已落地） |
| [../plans/prompts-corpus-butler-comparison-2026-05.md](../plans/comparisons/prompts-corpus-butler-comparison-2026-05.md) | Prompt Corpus ↔ Butler 对标全文 |
| [runtime-ops.md](./runtime-ops.md) | **Runtime timer**：定时任务 due、审计、批准与排障 |
| [wechat-daily-smoke-checklist.md](./wechat-daily-smoke-checklist.md) | **发版后真机冒烟**（H1–H10，约 15–25 分钟） |
| [wechat-core-scenario.md](./wechat-core-scenario.md) | 微信八步剧本详解与 FAQ |
| [owner-profile-setup.md](./owner-profile-setup.md) | Owner 画像配置 |
| [memory-ops.md](./memory-ops.md) | **记忆运维**：推荐 env、smoke/reindex、灵文检查表 |
| [dev-tools-ops.md](./dev-tools-ops.md) | **开发操作工具**：terminal / git / env 与 Runtime 分工 |
| [project-onboarding.md](./project-onboarding.md) | **项目接入**：preflight、模板、微信验收 |
| [manual-testing-guide.md](./manual-testing-guide.md) | CLI + 微信完整人工测试手册 |
| [../ops/diagnostic-thresholds.md](../ops/diagnostic-thresholds.md) | `/诊断` **运行指标**阈值（外部对标 P0） |
| [../config/reference.md](../config/reference.md) | `BUTLER_*`（含队列 mode、workflow 权限） |
| [../plans/README.md](../plans/README.md) | 规划索引（CC / 整理 / 外部对标） |
| [../plans/cc-butler-gap-analysis-2026-05.md](../plans/active/cc-butler-gap-analysis-2026-05.md) | CC↔Butler Loop 线束 |
| [../plans/reference-learning-plan-2026-05.md](../plans/archive/reference-learning-plan-2026-05.md) | 外部对标记录（**已收口**） |
| [../plans/post-consolidation-roadmap-2026-05.md](../plans/active/post-consolidation-roadmap-2026-05.md) | 产品后续规划 |
| [../reviews/project-assessment-2026-05.md](../reviews/project-assessment-2026-05.md) | 成熟度评估 |

## 脚本守门

| 脚本 | 用途 |
|------|------|
| `scripts/butler-pre-release-smoke.sh` | 发版前一键（preflight + pytest + smoke） |
| `scripts/butler-five-reports-gate.sh` | 五报告 P5–P10 守门 |
| `scripts/butler-runtime-smoke.sh` | Runtime 运维冒烟（灵文1号） |
| `scripts/butler-demo-pilot-smoke.sh` | 演示试点 E2E |
| `scripts/butler-dev-tools-smoke.sh` | 开发工具链实战冒烟 |

## 推荐顺序

1. 首次：`wechat-gateway-ops.md` → `butler wechat-setup` → 安装 systemd  
2. 日常发版：`butler-gateway-ops upgrade` → `butler-pre-release-smoke.sh` → `wechat-daily-smoke-checklist.md`（真机）  
3. 深入场景：`wechat-core-scenario.md`；改队列/workflow 前读 [`../architecture/v4-architecture.md`](../architecture/v4-architecture.md) Gateway 节
