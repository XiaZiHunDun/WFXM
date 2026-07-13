# Butler 文档索引

> 更新：**2026-07-13** | 主线：**Butler v4**（自建 Agent Loop，**仅微信**网关）  
> **新会话**：[`../AGENTS.md`](../AGENTS.md) → [`architecture/v4-architecture.md`](architecture/v4-architecture.md）  
> **文档体系**：[`DOCUMENTATION.md`](DOCUMENTATION.md)（分层、维护规则、勿从对照报告抽待办）
>
> **与 [`DOCUMENTATION.md`](DOCUMENTATION.md) 的关系**：本文是**卡片**（「我要…」问答快速链接表），适合「我想找具体某篇文档」；[`DOCUMENTATION.md`](DOCUMENTATION.md) 是**手册**（分层 + 维护规则 + 索引结构 + 变更记录），适合「我在维护文档 / 改代码时想知道动哪」。

## 协调与黑板

| 文档 | 说明 |
|------|------|
| [`.blackboard/README.md`](../.blackboard/README.md) | 异构 Agent 班次交接黑板（append-only shift card + state.md + log.md） |
| [`plans/specs/2026-07-13-wfxm-blackboard-design.md`](superpowers/specs/2026-07-13-wfxm-blackboard-design.md) | 黑板体系设计 spec（4 痛点 + 串行仲裁 + Markdown + YAML） |
| [`plans/2026-07-13-wfxm-blackboard.md`](superpowers/plans/2026-07-13-wfxm-blackboard.md) | 黑板 20 任务实施计划 |

## 快速入口

| 我要… | 读这里 |
|--------|--------|
| 改代码 / 查模块 | [`architecture/v4-architecture.md`](architecture/v4-architecture.md) |
| 查环境变量 | [`config/reference.md`](config/reference.md) + [`../.env.example`](../.env.example) |
| 配置放哪（env/yaml/secrets） | [`config/config-surfaces.md`](config/config-surfaces.md) |
| `/诊断` vs `butler doctor` vs `/doctor` | [`ops/diagnostic-entrypoints.md`](ops/diagnostic-entrypoints.md) |
| 切换项目后影响什么 | [`architecture/project-activation.md`](architecture/project-activation.md) |
| Hook/MCP/Skill 放哪 | [`architecture/extension-registry-paths.md`](architecture/extension-registry-paths.md) |
| 权限门控改哪 | [`architecture/permission-gate-stack.md`](architecture/permission-gate-stack.md) |
| **维护者 / 面试一页纸** | [`guides/maintainer-cheat-sheet-2026-07.md`](guides/maintainer-cheat-sheet-2026-07.md) |
| **看项目现状 / 已实现 / 未实现 / 依赖** | [`guides/capabilities-index-2026-05.md`](guides/capabilities-index-2026-05.md) |
| **发版一条链** | [`guides/release-runbook-2026-05.md`](guides/release-runbook-2026-05.md) |
| 微信发版 / 运维 | [`guides/wechat-gateway-ops.md`](guides/wechat-gateway-ops.md) → [`guides/wechat-daily-smoke-checklist.md`](guides/wechat-daily-smoke-checklist.md) |
| 看 CC 能力是否已有 | [`plans/cc-butler-gap-analysis-2026-05.md`](plans/active/cc-butler-gap-analysis-2026-05.md) |
| 看规划与命名 | [`plans/README.md`](plans/README.md) |
| **否决 / 未做 / Backlog（统一）** | [`plans/roadmap-backlog-and-boundaries-2026-05.md`](plans/decisions/roadmap-backlog-and-boundaries-2026-05.md) |
| **理论—实现差距（G1–G4）** | [`plans/decisions/theory-implementation-gap-register-2026-06.md`](plans/decisions/theory-implementation-gap-register-2026-06.md) |
| **Phase 4/9 运营与收口** | [`guides/phase4-ops-runbook.md`](guides/phase4-ops-runbook.md) · [`plans/active/post-consolidation-roadmap-2026-05.md`](plans/active/post-consolidation-roadmap-2026-05.md) §9 |
| 四报告已落地 / 18 项不做 | [`guides/four-reports-capabilities-2026-05.md`](guides/four-reports-capabilities-2026-05.md) · [`plans/four-reports-out-of-scope-2026-05.md`](plans/decisions/four-reports-out-of-scope-2026-05.md) |
| 五报告已落地 / S1–S11 | [`guides/five-reports-capabilities-2026-05.md`](guides/five-reports-capabilities-2026-05.md) · [`plans/five-reports-not-done-2026-05.md`](plans/decisions/five-reports-not-done-2026-05.md) |
| 外部 Agent 路线图（PR-X 已落地） | [`plans/external-agent-reports-improvement-roadmap-2026-05.md`](plans/roadmaps/external-agent-reports-improvement-roadmap-2026-05.md) |
| Codex 对标 Sprint C0–C2 | [`guides/sprint-codex-c0-2026-05.md`](guides/sprint-codex-c0-2026-05.md) · [C1](guides/sprint-codex-c1-2026-05.md) · [C2](guides/sprint-codex-c2-2026-05.md) |
| 目录与命令 | [`../STRUCTURE.md`](../STRUCTURE.md) |

## 架构与设计

| 文档 | 说明 |
|------|------|
| [`architecture/v4-architecture.md`](architecture/v4-architecture.md) | **当前架构**：Loop、Gateway、CC 线束 + 外部对标落地 |
| [`design/design.md`](design/design.md) | 产品设计摘要；§9 对照表（附录可能滞后，勿作实现 SSOT） |
| [`architecture/project-lead-decision.md`](architecture/project-lead-decision.md) | 莎丽门户 + 厂长主控 |
| [`architecture/project-runtime-automation.md`](architecture/project-runtime-automation.md) | Runtime 定时任务 |
| [`architecture/wechat-inbound-media.md`](architecture/wechat-inbound-media.md) | 入站图片 VLM + 语音转写 |
| [`architecture/layered-model-config.md`](architecture/layered-model-config.md) | 分层模型配置 |
| [`architecture/hermes-decoupling.md`](architecture/hermes-decoupling.md) | Hermes 解耦（已完成） |
| [`architecture/hermes-extraction-map.md`](architecture/hermes-extraction-map.md) | Hermes → Butler 提炼对照 |

## 运维与测试

| 文档 | 说明 |
|------|------|
| [`guides/README.md`](guides/README.md) | **指南总索引**（冒烟、Runtime、接入） |
| [`guides/capabilities-index-2026-05.md`](guides/capabilities-index-2026-05.md) | 项目状态总览（已实现 / 未实现 / 依赖） |
| [`guides/dependency-policy-2026-05.md`](guides/dependency-policy-2026-05.md) | 依赖分层与引入策略（core / extras / 明确不引入） |
| [`guides/wechat-gateway-ops.md`](guides/wechat-gateway-ops.md) | systemd 安装、发版、日志 |
| [`guides/wechat-daily-smoke-checklist.md`](guides/wechat-daily-smoke-checklist.md) | 发版真机 H1–H10 |
| [`guides/wechat-core-scenario.md`](guides/wechat-core-scenario.md) | 微信八步剧本 |
| [`guides/manual-testing-guide.md`](guides/manual-testing-guide.md) | CLI + 微信人工测试 |
| [`guides/runtime-ops.md`](guides/runtime-ops.md) | Runtime timer |
| [`guides/phase4-ops-runbook.md`](guides/phase4-ops-runbook.md) | Phase 4 运营巩固 + 灵文样板 |
| [`guides/memory-ops.md`](guides/memory-ops.md) | 记忆运维（含 SSOT ↔ SQLite 索引关系） |
| [`guides/maintainer-cheat-sheet-2026-07.md`](guides/maintainer-cheat-sheet-2026-07.md) | 维护者速查与面试手册 |
| [`guides/project-onboarding.md`](guides/project-onboarding.md) | 项目接入 preflight |
| [`ops/diagnostic-thresholds.md`](ops/diagnostic-thresholds.md) | `/诊断` 运行指标阈值说明 |
| [`../tests/README.md`](../tests/README.md) | pytest 分层与守门 |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | 贡献、Hooks、出站、语料 |

## 规划与评估

| 文档 | 说明 |
|------|------|
| [`DOCUMENTATION.md`](DOCUMENTATION.md) | **文档体系**（L0–L5 分层、维护规则、语料专项） |
| [`plans/README.md`](plans/README.md) | **规划索引**（CC / 整理 / 外部对标 命名对照） |
| [`plans/roadmap-backlog-and-boundaries-2026-05.md`](plans/decisions/roadmap-backlog-and-boundaries-2026-05.md) | **否决 / Backlog 决策入口** |
| [`plans/cc-butler-gap-analysis-2026-05.md`](plans/active/cc-butler-gap-analysis-2026-05.md) | Claude Code ↔ Butler（**主对照**） |
| [`plans/reference-learning-plan-2026-05.md`](plans/archive/reference-learning-plan-2026-05.md) | 外部对标（Prometheus/OpenClaw/Dify）— **已收口** |
| [`plans/four-reports-improvement-roadmap-2026-05.md`](plans/roadmaps/four-reports-improvement-roadmap-2026-05.md) | 四份报告合并路线图（**已收口** §9） |
| [`guides/four-reports-capabilities-2026-05.md`](guides/four-reports-capabilities-2026-05.md) | 四报告能力速查（env / CLI / 测试） |
| [`plans/openclaw-learning-plan-2026-05.md`](plans/comparisons/openclaw-learning-plan-2026-05.md) | OpenClaw 对标 OC-P0–P2（前置压缩、Gateway、doctor）— **已落地** |
| [`plans/comparisons/hermes-agent-dependency-and-extraction-report-2026-05.md`](plans/comparisons/hermes-agent-dependency-and-extraction-report-2026-05.md) | Hermes 依赖/边界对照报告（**非待办**） |
| [`plans/post-consolidation-roadmap-2026-05.md`](plans/active/post-consolidation-roadmap-2026-05.md) | 运营与多项目后续 |
| [`plans/consolidation-2026-05.md`](plans/archive/consolidation-2026-05.md) | 仓库整理（已完成） |
| [`reviews/project-deep-audit-2026-06.md`](reviews/project-deep-audit-2026-06.md) | 成熟度评估 |

## 语料与微信测试（专项）

与 Loop 对标正交；改 `tests/corpus/` 或网关路由时读 [`DOCUMENTATION.md`](DOCUMENTATION.md) §5。

| 文档 | 说明 |
|------|------|
| [`plans/corpus-testing-module-design-2026-05.md`](plans/corpus/corpus-testing-module-design-2026-05.md) | 语料模块设计 |
| [`plans/wechat-real-coverage-matrix-2026-05.md`](plans/corpus/wechat-real-coverage-matrix-2026-05.md) | 真机覆盖矩阵 |
| [`guides/project-intro-for-utterance-corpus.md`](guides/project-intro-for-utterance-corpus.md) | 语料项目介绍 |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | `corpus-test.sh` 门禁 |

## 配置模板

| 文档 | 说明 |
|------|------|
| [`config/reference.md`](config/reference.md) | `BUTLER_*` 速查 |
| [`templates/permissions.yaml.example`](templates/permissions.yaml.example) | 项目 `.butler/permissions.yaml` 模板（含 `workflow_steps`） |

## 历史与外部对照

| 路径 | 说明 |
|------|------|
| [`history/README.md`](history/README.md) | v0.5–v3 文档（勿作实现依据） |
| [`../archive/`](../archive/) | v1 归档标签 `archive/butler-v1-20260522` |
| [`../reference/`](../reference/) | 外部标本（**gitignore**，主公维护） |

## 验证命令

```bash
cd /path/to/WFXM
PYTHONPATH=. pytest -q    # 默认 1200+ passed（排除 live_llm；corpus 按需）

# 守门子集
PYTHONPATH=. pytest tests/ops/test_runtime_metrics.py tests/gateway/test_message_queue.py \
  tests/test_p2_workflow_permissions.py tests/test_cc_p3_p4_features.py -q

# 微信网关 live（发版前可选）
BUTLER_RUN_REAL_API_SMOKE=1 pytest -m live_llm tests/gateway/test_wechat_gateway_live_smoke.py -v
```

```bash
bash scripts/butler-gateway-ops.sh status
bash scripts/butler-pre-release-smoke.sh
```
