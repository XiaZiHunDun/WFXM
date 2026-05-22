# scripts/ 索引

> 日常只记三条：`butler-gateway-ops.sh`、`butler-pre-release-smoke.sh`、`sync-lingwen-project-skills.sh`（灵文）。  
> 整理方案：[`docs/plans/consolidation-2026-05.md`](../docs/plans/consolidation-2026-05.md)

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
| `butler-pre-release-smoke.sh` | 1 gateway preflight → 2 全量 pytest → 3–5 微信/媒体 → 6 灵文 runtime → 7 dev 委派 → 8 DemoPilot |

## 分域冒烟（被 pre-release 或文档调用）

| 脚本 | 项目/范围 |
|------|-----------|
| `butler-wechat-memory-smoke.sh` | 记忆微信门 pytest |
| `butler-wechat-gateway-smoke.sh` | 网关核心 pytest |
| `butler-inbound-media-smoke.sh` | 入站媒体 |
| `butler-runtime-smoke.sh` | **灵文1号** runtime（factory-status、preflight 等） |
| `butler-demo-pilot-smoke.sh` | **演示试点** preflight + heartbeat + test-unit-smoke |
| `butler-dev-delegate-smoke.sh` | 委派工作流 |
| `butler-dev-tools-smoke.sh` | terminal / git / patch |
| `butler-memory-smoke.sh` | 记忆 recall 子集 |
| `butler-wechat-push-verify.sh` | 真机推送验证（可选） |

## systemd 单元

`systemd/butler-gateway.service`、`butler-runtime-lingwen.timer` 等 — 由 install 脚本链接到 `~/.config/systemd/user/`。
