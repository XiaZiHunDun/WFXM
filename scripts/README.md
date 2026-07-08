# scripts/ 索引

> 日常只记四条：`butler-gateway-ops.sh`、`butler-smoke.sh`、`butler-pre-release-smoke.sh`（= `--tier=full`）、`sync-lingwen-project-skills.sh`（灵文）。  
> 整理方案：[`docs/plans/archive/consolidation-2026-05.md`](../docs/plans/archive/consolidation-2026-05.md)

## 部署与数据管理

| 脚本 | 用途 |
|------|------|
| `deploy-new-env.sh` | **新环境一键部署**（Python 检查 → venv → 依赖 → 配置 → doctor） |
| `backup-butler-data.sh` | 备份 `~/.butler/` 运行时数据 |
| `restore-butler-data.sh` | 从备份恢复数据（自动安全备份已有数据） |

## 安装与 systemd

| 脚本 | 用途 |
|------|------|
| `install-butler-gateway-service.sh` | 微信网关用户 systemd 服务 |
| `install-butler-ops-bundle.sh` | runtime timer + push-drain + logrotate 一键 |
| `install-butler-runtime-timer.sh` | 灵文 runtime 定时器 |
| `install-butler-push-drain.sh` | 推送队列重试 timer |
| `install-butler-b9-weekly-timer.sh` | B9 周循环 + SWE 门控全量（周日 03:30） |
| `install-butler-ops-cadence-timer.sh` | G1-04 周报（周日 05:00）+ 季度 capability（季初 05:30） |
| `install-butler-logrotate.sh` | 日志轮转 |
| `setup-butler-config.sh` | 生成 `~/.butler/config.yaml` |
| `lib/butler-gateway-preflight.sh` | 网关启动前检查（被 ops 调用） |
| `lib/butler-source-env.sh` | 安全 `source .env`（`set -u` 下兼容 `${VAR:-}`） |

## 日常运维

| 脚本 | 用途 |
|------|------|
| `butler-gateway-ops.sh` | **主入口**：status / restart / logs / preflight / upgrade |
| `butler-memory-reindex.sh` | 重建语义向量索引 |
| `butler-runtime-run.sh` | 手动跑单个 runtime job |
| `butler-runtime-due.sh` | 执行到期 cron 任务 |
| `sync-lingwen-project-skills.sh` | `projects/LingWen1/skills/` → `.butler/skills/` |

## 发版守门

| 脚本 | 步骤 |
|------|------|
| `project-health-check.sh` | **统一体检**：语法/导入/配置对齐/核心测试（`quick`）+ 语料与五报告守门（`full`） |
| `project-health-report.sh` | 基于 `project-health-check.sh` 产出带时间戳的体检报告（`logs/maintenance/`） |
| `repo-cleanup-audit.sh` | 仓库清理审计：结构漂移、tracked 大文件、git 工作区变更概览 |
| `butler-smoke.sh` | `--tier=quick`（preflight + 快测）/ `standard`（+ 域冒烟）/ `full`（= pre-release） |
| `butler-phase4-smoke.sh` | **Phase 4 守门**：standard/full + Lead + runtime + 媒体 + 回归门 |
| `butler-phase5-smoke.sh` | **Phase 5 守门**：B9 + 多项目 C + 双 Lead smoke |
| `butler-eval-llm-benchmark.sh` | **O9** B9 LLM delegate 基准（oracle / live） |
| `butler-b9-weekly-gate-followup.sh` | B9 周循环 + SWE 双周门控通过后自动全量 LIVE |
| `sync-project-skills.sh` | 任意项目 `skills/` → `.butler/skills/` |
| `butler-memory-metrics-smoke.sh` | **D2-4/D2-5** 记忆效果度量接线测试 |
| `butler-pre-release-smoke.sh` | 1 gateway → **1b P3-H verify** → 2 pytest → **2b orthogonality** → 3–5 微信/媒体 → 6 灵文 runtime → 7 **灵文 Lead** → 8 dev 委派 → 9 DemoPilot → 10 B9 → 11–13 路由/owner sim |
| `butler-five-reports-gate.sh` | 五报告 P5–P10 + PR-F 单测 + `prompt-eval.sh` + `registry verify` |
| `butler-extension-ext1-preflight.sh` | EXT-1 Firecrawl MCP 就绪检查（Node/npx/配置） |
| `p3i-lazy-import-report.sh` | P3-I：函数内 `from butler.*` 懒 import 报告 vs `LAZY_IMPORT_BUDGET` |
| `p3j-env-hygiene-gate.sh` | P3-J：`check-env-reference-sync` + `check-dead-env` + audit strict + schema PoC |
| `p3j-env-audit.sh` | P3-J：code/reference/example 差集审计（默认 report；`P3J_AUDIT_STRICT=1` fail） |
| `p3j-env-schema-poc.py` | P3-J：静态 code keys vs reference diff（`P3J_SCHEMA_STRICT=1` 可 fail） |
| `check-dead-env.sh` | `reference.md` 中 `BUTLER_*` 须在 `butler/` 有 reader（脚本/测试 key 白名单） |
| `check-env-reference-sync.sh` | `reference.md` 主表 ↔ `.env.example` 键对齐（含 `*` 前缀行） |
| `prompt-eval.sh` | Prompt pattern rubric + `test_five_reports_p7/p9/p10` |

## 分域冒烟（被 pre-release 或文档调用）

| 脚本 | 项目/范围 |
|------|-----------|
| `butler-wechat-memory-smoke.sh` | 记忆微信门 pytest |
| `butler-memory-monthly-probe.sh` | M1–M7 月度探针（`--log` / `--manual`） |
| `butler-wechat-gateway-smoke.sh` | 网关核心 pytest |
| `butler-inbound-media-smoke.sh` | 入站媒体 |
| `butler-runtime-smoke.sh` | **灵文1号** runtime（factory-status、preflight 等） |
| `butler-lingwen-lead-smoke.sh` | **灵文1号** Lead 工具白名单 + `workflow_state.json` 只读断言 |
| `butler-demo-pilot-smoke.sh` | **演示试点** preflight + heartbeat + test-unit-smoke |
| `butler-dev-delegate-smoke.sh` | 委派工作流 |
| `butler-dev-tools-smoke.sh` | terminal / git / patch |
| `butler-memory-smoke.sh` | 记忆 recall 子集 |
| `butler-wechat-push-verify.sh` | 真机推送验证（可选） |

## Eval / B9 评测族

| 脚本 | 用途 |
|------|------|
| `butler-eval-b9-live.sh` | B9 LIVE 合成编码评测 |
| `butler-eval-b9-tuning.sh` | B9 调参 / tier 探测 |
| `butler-eval-b9-probe-model.sh` | B9 模型探针 |
| `butler-b9-release-gate.sh` | B9 发版门控 |
| `butler-b9-weekly-learning.sh` | B9 周循环修学 |
| `butler-b9-weekly-gate-followup.sh` | B9 周门控通过后自动全量 LIVE |
| `butler-b9-export-curriculum.sh` | B9 课程导出 |
| `butler-eval-swebench-live.sh` | SWE-bench live 子集 |
| `butler-eval-swebench-live-full.sh` | SWE-bench 全量 |
| `butler-eval-llm-benchmark.sh` | O9 B9 LLM delegate 基准 |
| `butler-eval-weekly.sh` | 周度 eval 汇总 |
| `butler-eval-regression.sh` | eval 回归 |
| `butler-eval-release.sh` | 发版 preset（tcr + regression + wechat_corpus） |
| `butler-eval-experiment.sh` | 实验 harness |
| `butler-eval-wechat-corpus.sh` | 微信语料 eval |
| `butler-eval-assistant-health.sh` | 助手健康度 |
| `butler-cc-harness-gate.sh` | CC 线束守门 |

## 测试域

| 脚本 | 用途 |
|------|------|
| `butler-domain-pytest.sh` | 按域跑 pytest：`gateway` / `ops` / `dev_engine` / `memory` / `core` / `all` |
| `ci-ruff-gate.sh` | CI 与 `project-health-check` 对齐的 Ruff 子集（`E,F`） |

## 微信 handler 模拟 / Dev 飞轮

| 脚本 | 用途 |
|------|------|
| `butler-wechat-dev-flywheel-sim.sh` | Dev 飞轮 handler 话术 sim（覆写 `dev-flywheel-{date}.md`） |
| `butler-wechat-dev-delegate-sim.sh` | Dev 委派多场景 sim（`--track lingwen`） |
| `butler-wechat-dev-assistant-sim.sh` | **开发助手十项** handler sim（2026-07） |
| `butler-wechat-lead-readonly-sim.sh` | Lead 只读厂情门控 sim |
| `butler-wechat-owner-sim.sh` | Owner 话术 sim |
| `butler-wechat-core-sim.sh` | 核心对话 sim |
| `butler-web-search-route-sim.sh` | 联网搜索路由 sim |
| `butler-extension-wechat-sim.sh` | 扩展能力微信 sim |
| `butler-dev-delegate-smoke.sh` | Dev 委派 pytest 守门 |
| `butler-dev-tools-smoke.sh` | terminal / git / patch |
| `butler-dev-live-flywheel-checklist.sh` | Dev 飞轮 LIVE 清单 |
| `butler-dev-prod-evidence-checklist.sh` | 生产委派证据清单 |
| `butler-dev-delegate-experience-probe.sh` | 委派经验探针 |

## Head-to-head（Dev vs CC CLI）

| 脚本 | 用途 |
|------|------|
| `butler-head-to-head.sh` | T1–T5 全量头对头 |
| `butler-head-to-head-t1.sh` … `t5.sh` | 单题包装（fixture `tests/fixtures/head_to_head_t*`） |

实现：`butler/ops/head_to_head*.py`；记录见 `projects/LingWen1/docs/dev-cc-head-to-head.md`。

## G1 / Ops follow-up / 观测

| 脚本 | 用途 |
|------|------|
| `butler-g1-04-weekly-checkin.sh` | G1-04 窗内周打卡（`--log` → pilot-log） |
| `butler-g1-04-closure-check.sh` | G1-04 窗满结案检查 |
| `butler-g1-checklist.sh` | G1 清单 |
| `butler-g1-04-closure-run-if-ready.sh` | 窗满则尝试闭合 |
| `butler-g1-04-closure-apply.sh` | G1-04 闭合应用 |
| `butler-gap-observability.sh` | 差距登记册观测 |
| `butler-prod-delta-observe.sh` | 生产 delta 观测 |
| `butler-p1-live-probe.sh` | P1 live 探针 |

## Extension / MCP 预检

| 脚本 | 用途 |
|------|------|
| `butler-extension-ext1-preflight.sh` | EXT-1 Firecrawl MCP |
| `butler-extension-ext2-preflight.sh` | EXT-2 OpenAPI HTTP |
| `butler-extension-ext4-preflight.sh` | EXT-4 第二 OpenAPI |
| `butler-extension-ext4-integrate.sh` | EXT-4 集成 |
| `butler-extension-ext4-gate.sh` | EXT-4 pytest 守门（PROD-P2-04） |
| `butler-extension-ext5-preflight.sh` | EXT-5 MarkItDown MCP |
| `butler-extension-ext5-integrate.sh` | EXT-5 集成 |
| `butler-extension-ext5-gate.sh` | EXT-5 pytest 守门 |
| `butler-extension-verify.sh` | 扩展 verify 汇总 |
| `butler-secrets-contract-check.sh` | 密钥契约检查 |

## 日常四条（速记）

| 脚本 | 用途 |
|------|------|
| `butler-gateway-ops.sh` | 网关 status / restart / logs |
| `butler-smoke.sh` | quick / standard / full 分层冒烟 |
| `butler-pre-release-smoke.sh` | 发版全量守门 |
| `sync-lingwen-project-skills.sh` | 灵文 Skill 同步 |

## systemd 单元

`systemd/butler-gateway.service`、`butler-runtime-lingwen.timer` 等 — 由 install 脚本链接到 `~/.config/systemd/user/`。

**systemd + `.env` PATH**：若 `.env` 含 `PATH=…:$PATH`，在 timer/gateway 下 `$PATH` 可能为空或字面量，导致 **127** 或 MCP **`spawn sh ENOENT`**；gateway 经 `scripts/butler-gateway-exec.sh` 启动；bash 类 oneshot 经 `scripts/lib/butler-systemd-wrap.sh`（见 `butler-eval-sync` / `butler-b9-weekly-gate` / `butler-morning-brief` unit）。
