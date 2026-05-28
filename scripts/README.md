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
| `butler-pre-release-smoke.sh` | 1 gateway → 2 pytest → 3–5 微信/媒体 → 6 灵文 runtime → 7 **灵文 Lead** → 8 dev 委派 → 9 DemoPilot |
| `butler-five-reports-gate.sh` | 五报告 P5–P10 单测 + `prompt-eval.sh` + `registry verify` |
| `prompt-eval.sh` | Prompt pattern rubric + `test_five_reports_p7/p9/p10` |

## 分域冒烟（被 pre-release 或文档调用）

| 脚本 | 项目/范围 |
|------|-----------|
| `butler-wechat-memory-smoke.sh` | 记忆微信门 pytest |
| `butler-wechat-gateway-smoke.sh` | 网关核心 pytest |
| `butler-inbound-media-smoke.sh` | 入站媒体 |
| `butler-runtime-smoke.sh` | **灵文1号** runtime（factory-status、preflight 等） |
| `butler-lingwen-lead-smoke.sh` | **灵文1号** Lead 工具白名单 + `workflow_state.json` 只读断言 |
| `butler-demo-pilot-smoke.sh` | **演示试点** preflight + heartbeat + test-unit-smoke |
| `butler-dev-delegate-smoke.sh` | 委派工作流 |
| `butler-dev-tools-smoke.sh` | terminal / git / patch |
| `butler-memory-smoke.sh` | 记忆 recall 子集 |
| `butler-wechat-push-verify.sh` | 真机推送验证（可选） |

## systemd 单元

`systemd/butler-gateway.service`、`butler-runtime-lingwen.timer` 等 — 由 install 脚本链接到 `~/.config/systemd/user/`。
