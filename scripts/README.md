# Butler 运维脚本索引

> **更新**：2026-07-17 | **主线**：Butler v4  
> **入口**：[`../AGENTS.md`](../AGENTS.md) → 本文（按需）

## 脚本命名规范

| 前缀 | 含义 | 示例 |
|------|------|------|
| `butler-` | 核心运维脚本 | `butler-smoke.sh`、`butler-gateway-ops.sh` |
| `butler-pytest-` | pytest 门禁脚本 | `butler-pytest-fast-gate.sh` |
| `butler-layer-` | 层依赖检查 | `butler-layer-import-gate.sh` |
| `butler-cc-` | CC 线束相关 | `butler-cc-harness-gate.sh` |
| `butler-eval-` | 评估相关 | `butler-eval-weekly.sh` |
| `butler-wechat-` | 微信网关相关 | `butler-wechat-gateway-smoke.sh` |
| `butler-memory-` | 记忆相关 | `butler-memory-smoke.sh` |
| `butler-dev-` | 开发相关 | `butler-dev-delegate-smoke.sh` |
| `butler-extension-` | 扩展相关 | `butler-extension-verify.sh` |
| `butler-b9-` | B9 学习系统 | `butler-b9-release-gate.sh` |
| `butler-runtime-` | Runtime 相关 | `butler-runtime-smoke.sh` |
| `butler-cost-` | 成本相关 | `butler-cost-calibration.sh` |
| `p3i-` / `p3j-` | Phase 3 检查脚本 | `p3i-lazy-import-report.sh` |
| `install-butler-` | 安装脚本 | `install-butler-gateway-service.sh` |
| `check-` | 检查脚本 | `check-dead-env.sh` |

---

## 快速入口

| 我要… | 运行这个 |
|--------|----------|
| 本地快速门禁（3–5分钟） | `butler-pytest-fast-gate.sh` |
| 层依赖检查 | `butler-layer-import-gate.sh` |
| Lazy Import 报告 | `p3i-lazy-import-report.sh` |
| 环境变量卫生检查 | `p3j-env-hygiene-gate.sh` |
| 发版前冒烟 | `butler-pre-release-smoke.sh` |
| 微信网关状态 | `butler-gateway-ops.sh status` |
| CC 线束门禁 | `butler-cc-harness-gate.sh` |
| 五报告门禁 | `butler-five-reports-gate.sh` |
| 运营节奏（每周/每季） | `butler-ops-cadence.sh --weekly` |

---

## 门禁脚本（改代码前必跑）

| 脚本 | 用途 | 耗时 |
|------|------|------|
| `butler-pytest-fast-gate.sh` | 本地/PR 快速门禁（smoke + attach + CC harness + mypy） | 3–5 分钟 |
| `butler-mypy-strict-gate.sh` | mypy 严格模式检查（826 主模块） | 1–2 分钟 |
| `p3j-env-hygiene-gate.sh` | reference ↔ .env.example ↔ butler/ readers 同步检查 | < 30秒 |
| `p3j-env-audit.sh` | code/reference/example 差集检查（P3-J） | < 30秒 |
| `p3i-lazy-import-report.sh` | 函数内 from butler.* 预算检查（P3-I） | < 30秒 |
| `butler-layer-import-gate.sh` | 九层依赖矩阵检查（ENG-15，1200+ 文件） | 2–3 分钟 |
| `butler-cc-harness-gate.sh` | CC 线束检查（改 core/context/gateway 队列与压缩时） | 1–2 分钟 |
| `butler-five-reports-gate.sh` | 五报告门禁（P5–P10） | 1–2 分钟 |
| `butler-domain-pytest.sh` | 按域运行 pytest（gateway/ops/dev_engine/memory/core） | 2–5 分钟 |
| `butler-p1c-gate.sh` | P1-C 门禁 | < 1分钟 |
| `butler-p0a-exception-gate.sh` | P0-A 异常门禁 | < 1分钟 |
| `butler-p0b-degradation-gate.sh` | P0-B 降级门禁 | < 1分钟 |
| `butler-eng-domain-gate.sh` | 工程域门禁 | < 1分钟 |

---

## 冒烟测试

| 脚本 | 用途 |
|------|------|
| `butler-smoke.sh` | 基础冒烟测试 |
| `butler-runtime-smoke.sh` | Runtime 冒烟测试 |
| `butler-memory-smoke.sh` | 记忆系统冒烟测试 |
| `butler-wechat-gateway-smoke.sh` | 微信网关冒烟测试 |
| `butler-wechat-attach-smoke.sh` | 微信附件冒烟测试 |
| `butler-inbound-media-smoke.sh` | 入站媒体冒烟测试 |
| `butler-delegate-deep-smoke.sh` | 委派深度冒烟测试 |
| `butler-dev-delegate-smoke.sh` | 开发委派冒烟测试 |
| `butler-phase4-smoke.sh` | Phase 4 冒烟测试 |
| `butler-phase5-smoke.sh` | Phase 5 冒烟测试 |
| `butler-dot-lite-smoke.sh` | Dot Lite 冒烟测试 |
| `butler-reasoning-trace-smoke.sh` | 推理追踪冒烟测试 |
| `butler-compaction-live-test.sh` | 压缩现场测试 |
| `butler-context-compaction-smoke.sh` | 上下文压缩冒烟测试 |

---

## 微信网关运维

| 脚本 | 用途 |
|------|------|
| `butler-gateway-ops.sh` | 网关运维（status/restart/logs） |
| `butler-wechat-gateway-smoke.sh` | 网关冒烟测试 |
| `butler-wechat-owner-sim.sh` | 主人微信模拟 |
| `butler-wechat-dev-assistant-sim.sh` | 开发助手微信模拟 |
| `butler-wechat-core-sim.sh` | 微信核心场景模拟 |
| `butler-wechat-remote-dev-sim.sh` | 远程开发微信模拟 |
| `butler-wechat-lead-readonly-sim.sh` | 只读领导微信模拟 |
| `butler-wechat-dev-flywheel-sim.sh` | 开发飞轮微信模拟 |
| `butler-wechat-dual-playbook-probe.sh` | 双重剧本探测 |
| `butler-wechat-memory-smoke.sh` | 微信记忆冒烟测试 |
| `butler-wechat-push-verify.sh` | 微信推送验证 |
| `butler-wechat-manual-flywheel-probe.sh` | 手动飞轮探测 |
| `butler-wechat-attach-probe.sh` | 附件探测 |

---

## 记忆系统

| 脚本 | 用途 |
|------|------|
| `butler-memory-smoke.sh` | 记忆系统冒烟测试 |
| `butler-memory-metrics-smoke.sh` | 记忆指标冒烟测试 |
| `butler-memory-reindex.sh` | 记忆重新索引 |
| `butler-memory-phase-a.sh` | 记忆 Phase A |
| `butler-memory-phase-b.sh` | 记忆 Phase B |
| `butler-memory-phase-c.sh` | 记忆 Phase C |
| `butler-memory-monthly-probe.sh` | 记忆月度探测 |
| `butler-experience-mining-smoke.sh` | 经验挖掘冒烟测试 |

---

## B9 学习系统

| 脚本 | 用途 |
|------|------|
| `butler-b9-release-gate.sh` | B9 发布门禁 |
| `butler-b9-weekly-gate-followup.sh` | B9 周门禁跟进 |
| `butler-b9-weekly-learning.sh` | B9 周学习 |
| `butler-b9-export-curriculum.sh` | 导出课程 |
| `butler-delegate-failure-review.sh` | 委派失败审查 |
| `butler-delegate-failure-promote.sh` | 委派失败升级 |
| `butler-delegate-failure-promote-demo.sh` | 委派失败升级演示 |

---

## 编码严格模式

| 脚本 | 用途 |
|------|------|
| `butler-coding-strict-opt-in.sh` | 编码严格模式 opt-in |
| `butler-coding-strict-pilot.sh` | 编码严格模式试点 |
| `butler-coding-strict-pilot-smoke.sh` | 编码严格模式试点冒烟 |
| `butler-coding-strict-pilot-multi.sh` | 编码严格模式多类别试点 |
| `butler-tcr-strict-readiness.sh` | TCR 严格模式就绪检查 |
| `butler-tcr-strict-apply.sh` | TCR 严格模式应用 |

---

## 评估与基准

| 脚本 | 用途 |
|------|------|
| `butler-eval-weekly.sh` | 每周评估 |
| `butler-eval-release.sh` | 发版评估 |
| `butler-eval-regression.sh` | 回归评估 |
| `butler-eval-b9-live.sh` | B9 现场评估 |
| `butler-eval-b9-probe-model.sh` | B9 模型探测 |
| `butler-eval-b9-tuning.sh` | B9 调优评估 |
| `butler-eval-llm-benchmark.sh` | LLM 基准测试 |
| `butler-eval-wechat-corpus.sh` | 微信语料评估 |
| `butler-eval-assistant-health.sh` | 助手健康评估 |
| `butler-eval-experiment.sh` | 实验评估 |
| `butler-agent-eval-weekly.sh` | Agent 每周评估 |
| `butler-head-to-head.sh` | 对标测试 |
| `butler-head-to-head-t1.sh` ~ `t5.sh` | 对标测试 T1–T5 |
| `butler-capability-baseline.sh` | 能力基线测试 |

---

## 扩展管理

| 脚本 | 用途 |
|------|------|
| `butler-extension-verify.sh` | 扩展验证 |
| `butler-extension-wechat-sim.sh` | 微信扩展模拟 |
| `butler-extension-ext1-preflight.sh` | 扩展1预检 |
| `butler-extension-ext2-preflight.sh` | 扩展2预检 |
| `butler-extension-ext4-preflight.sh` | 扩展4预检 |
| `butler-extension-ext4-integrate.sh` | 扩展4集成 |
| `butler-extension-ext5-preflight.sh` | 扩展5预检 |
| `butler-extension-ext5-verify.sh` | 扩展5验证 |
| `butler-extension-ext5-integrate.sh` | 扩展5集成 |
| `butler-extension-ext5-gate.sh` | 扩展5门禁 |
| `butler-ext5-pdf-ingest-sim.sh` | 扩展5 PDF 摄入模拟 |
| `butler-ext5-wechat-phrases-card.sh` | 扩展5微信短语卡片 |

---

## 灵文项目

| 脚本 | 用途 |
|------|------|
| `butler-lingwen-lead-smoke.sh` | 灵文领导冒烟测试 |
| `butler-lingwen-skills-install.sh` | 灵文技能安装 |
| `butler-lingwen-live-capture-checklist.sh` | 灵文现场捕获检查 |
| `butler-lingwen1-prod-sample.sh` | 灵文1号生产抽样 |
| `butler-lingwen1-edit-capture.sh` | 灵文1号编辑捕获 |
| `butler-lingwen1-delegate-drill.sh` | 灵文1号委派演练 |
| `butler-lingwen1-capture-probe.sh` | 灵文1号捕获探测 |

---

## 安装与部署

| 脚本 | 用途 |
|------|------|
| `install-butler-gateway-service.sh` | 安装网关服务 |
| `install-butler-runtime-timer.sh` | 安装 Runtime 定时器 |
| `install-butler-morning-brief-timer.sh` | 安装早报定时器 |
| `install-butler-eval-sync-timer.sh` | 安装评估同步定时器 |
| `install-butler-b9-weekly-timer.sh` | 安装 B9 周定时器 |
| `install-butler-logrotate.sh` | 安装日志轮转 |
| `install-butler-ops-bundle.sh` | 安装运维包 |
| `install-butler-ops-cadence-timer.sh` | 安装运维节奏定时器 |
| `butler-deploy.sh` | 部署脚本 |
| `deploy-new-env.sh` | 部署新环境 |
| `setup-butler-config.sh` | 设置 Butler 配置 |

---

## 运营与监控

| 脚本 | 用途 |
|------|------|
| `butler-ops-cadence.sh` | 运营节奏（--weekly/--quarterly） |
| `butler-g1-checklist.sh` | G1 检查清单 |
| `butler-g1-04-weekly-checkin.sh` | G1-04 周检查 |
| `butler-g1-04-closure-check.sh` | G1-04 结案检查 |
| `butler-g1-04-closure-apply.sh` | G1-04 结案应用 |
| `butler-g1-04-closure-run-if-ready.sh` | G1-04 就绪时结案 |
| `butler-gap-observability.sh` | 差距可观测性 |
| `butler-trust-p2-gate.sh` | 信任 P2 门禁 |
| `butler-owner-ux-p3-gate.sh` | 主人 UX P3 门禁 |
| `butler-owner-ux-p4-gate.sh` | 主人 UX P4 门禁 |
| `butler-owner-ux-p4b-wechat-sim.sh` | 主人 UX P4B 微信模拟 |
| `butler-owner-ux-p4c-gate.sh` | 主人 UX P4C 门禁 |
| `butler-owner-ux-p5-gate.sh` | 主人 UX P5 门禁 |
| `butler-owner-pmf-report.sh` | 主人 PMF 报告 |
| `butler-owner-week1-ops-sim.sh` | 主人第一周运营模拟 |
| `butler-delegation-boundary-smoke.sh` | 委派边界冒烟测试 |
| `butler-dev-flywheel-monthly.sh` | 开发飞轮月度 |
| `butler-dev-live-flywheel-checklist.sh` | 开发现场飞轮检查 |
| `butler-p1-live-probe.sh` | P1 现场探测 |
| `butler-prod-delta-observe.sh` | 生产增量观测 |
| `butler-prod-playbook-seed.sh` | 生产剧本种子 |
| `butler-morning-brief-push.sh` | 早报推送 |
| `butler-observation-migrate.sh` | 观测迁移 |
| `butler-observability-provision.sh` | 可观测性配置 |

---

## 检查与审计

| 脚本 | 用途 |
|------|------|
| `check-dead-env.sh` | 检查死环境变量 |
| `check-env-reference-sync.sh` | 检查环境变量与参考同步 |
| `check-schema-drift.sh` | 检查 Schema 漂移 |
| `butler-complexity-report.sh` | 复杂度报告 |
| `butler-secrets-contract-check.sh` | 密钥契约检查 |
| `butler-trajectory-compliance-gate.sh` | 轨迹合规门禁 |
| `butler-p3h-rollout-verify.sh` | P3-H 部署验证 |
| `butler-dev-prod-evidence-checklist.sh` | 开发生产证据检查 |
| `butler-wechat-real-device-matrix-2026-07.md` | 微信真机矩阵 |

---

## 数据管理

| 脚本 | 用途 |
|------|------|
| `backup-butler-data.sh` | 备份 Butler 数据 |
| `restore-butler-data.sh` | 恢复 Butler 数据 |
| `butler-wechat-dataset-sync.sh` | 微信数据集同步 |
| `butler-ingest-pilot.sh` | 摄入试点 |

---

## 测试工具

| 脚本 | 用途 |
|------|------|
| `ci-pytest-gate.sh` | CI pytest 门禁 |
| `ci-ruff-gate.sh` | CI ruff 门禁 |
| `butler-pytest-bisect.sh` | pytest 二分查找 |
| `corpus-test.sh` | 语料测试 |
| `project-health-check.sh` | 项目健康检查 |
| `project-health-report.sh` | 项目健康报告 |
| `repo-cleanup-audit.sh` | 仓库清理审计 |

---

## 辅助脚本

| 脚本 | 用途 |
|------|------|
| `run-test-layer.sh` | 运行层测试 |
| `docs-lint.sh` | 文档 lint |
| `butler-web-search-route-sim.sh` | 网络搜索路由模拟 |
| `butler-web-search-probe.sh` | 网络搜索探测 |
| `butler-firecrawl-api-key-sync.sh` | Firecrawl API 密钥同步 |
| `butler-github-token-sync.sh` | GitHub 令牌同步 |
| `butler-github-openapi-spec-install.sh` | GitHub OpenAPI 规范安装 |
| `butler-todoist-token-sync.sh` | Todoist 令牌同步 |
| `butler-todoist-token-rotate.sh` | Todoist 令牌轮换 |
| `sync-project-skills.sh` | 同步项目技能 |
| `sync-lingwen-project-skills.sh` | 同步灵文项目技能 |
| `prompt-eval.sh` | 提示词评估 |
| `docs-restructure-plans.sh` | 文档重构计划 |
| `builtin-tool-orthogonality-lint.sh` | 内置工具正交性 lint |

---

## 参考

- [`../AGENTS.md`](../AGENTS.md) — Agent 工作说明（改代码前必读）
- [`../docs/README.md`](../docs/README.md) — 文档索引
- [`../docs/DOCUMENTATION.md`](../docs/DOCUMENTATION.md) — 文档体系与维护规则