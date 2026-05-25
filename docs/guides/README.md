# 指南文档索引

> 更新：2026-05-25 | 个人助手 Butler：**主场景为微信**；CLI 为本地开发与调试。

| 文档 | 用途 |
|------|------|
| [wechat-gateway-ops.md](./wechat-gateway-ops.md) | **生产运维**：systemd 安装、发版、日志、排障 |
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
| [../plans/cc-butler-gap-analysis-2026-05.md](../plans/cc-butler-gap-analysis-2026-05.md) | CC↔Butler Loop 线束 |
| [../plans/reference-learning-plan-2026-05.md](../plans/reference-learning-plan-2026-05.md) | 外部对标记录（**已收口**） |
| [../plans/post-consolidation-roadmap-2026-05.md](../plans/post-consolidation-roadmap-2026-05.md) | 产品后续规划 |
| [../reviews/project-assessment-2026-05.md](../reviews/project-assessment-2026-05.md) | 成熟度评估 |

## 脚本守门

| 脚本 | 用途 |
|------|------|
| `scripts/butler-pre-release-smoke.sh` | 发版前一键（preflight + pytest + smoke） |
| `scripts/butler-runtime-smoke.sh` | Runtime 运维冒烟（灵文1号） |
| `scripts/butler-demo-pilot-smoke.sh` | 演示试点 E2E |
| `scripts/butler-dev-tools-smoke.sh` | 开发工具链实战冒烟 |

## 推荐顺序

1. 首次：`wechat-gateway-ops.md` → `butler wechat-setup` → 安装 systemd  
2. 日常发版：`butler-gateway-ops upgrade` → `butler-pre-release-smoke.sh` → `wechat-daily-smoke-checklist.md`（真机）  
3. 深入场景：`wechat-core-scenario.md`；改队列/workflow 前读 [`../architecture/v4-architecture.md`](../architecture/v4-architecture.md) Gateway 节
