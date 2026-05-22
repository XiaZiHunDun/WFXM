# Butler 文档索引

> 更新：2026-05-20 | 当前主线：**Butler v4**（自建 Agent Loop，**仅微信**网关）  
> 仓库目录：[`../STRUCTURE.md`](../STRUCTURE.md) · 指南：[`guides/README.md`](guides/README.md)

## 推荐阅读顺序

| 文档 | 说明 |
|------|------|
| [`architecture/v4-architecture.md`](architecture/v4-architecture.md) | **当前架构**：Loop 栈、Gateway、观测、测试规模 |
| [`architecture/hermes-extraction-map.md`](architecture/hermes-extraction-map.md) | Hermes → Butler 提炼对照与验收状态 |
| [`architecture/hermes-decoupling.md`](architecture/hermes-decoupling.md) | **解耦路线图**（目标：零 Hermes 黑盒依赖）|
| [`architecture/project-lead-decision.md`](architecture/project-lead-decision.md) | **项目 Lead 架构决策**（莎丽门户 + 厂长主控，分阶段）|
| [`architecture/project-runtime-automation.md`](architecture/project-runtime-automation.md) | **阶段 3** 定时脚本 / 运行时推送 |
| [`guides/runtime-ops.md`](guides/runtime-ops.md) | **Runtime timer** 安装、due、审计与排障 |
| [`architecture/wechat-inbound-media.md`](architecture/wechat-inbound-media.md) | **微信入站图片/语音** MiniMax VLM + 语音转写（已实施 P1+P2） |
| [`architecture/layered-model-config.md`](architecture/layered-model-config.md) | **分层模型配置** 设计 vs 实现对照 + 完善路线（M1–M5） |
| [`design/design.md`](design/design.md) | 完整产品设计（记忆、Skill、编排、命令速查） |
| [`guides/README.md`](guides/README.md) | 微信运维 / 冒烟 / 人工测试索引 |
| [`guides/wechat-gateway-ops.md`](guides/wechat-gateway-ops.md) | **微信网关 systemd 运维**（安装、发版、排障） |
| [`guides/wechat-daily-smoke-checklist.md`](guides/wechat-daily-smoke-checklist.md) | 发版后真机冒烟检查表 |
| [`guides/wechat-core-scenario.md`](guides/wechat-core-scenario.md) | 微信核心场景八步剧本 |
| [`guides/manual-testing-guide.md`](guides/manual-testing-guide.md) | CLI / 微信完整人工测试 |
| [`.env.example`](../.env.example) | 环境变量与真实 API smoke 门控 |

## 版本演进（历史）

见 [`history/README.md`](history/README.md)（v1 / v3 对照文档）。

## 验证命令

```bash
cd /home/ailearn/projects/WFXM
PYTHONPATH=. pytest -q    # ~1121 passed

# 微信网关 live（发版前可选）
BUTLER_RUN_REAL_API_SMOKE=1 pytest -m live_llm tests/test_wechat_gateway_live_smoke.py -v

# 其它 Provider smoke
BUTLER_RUN_REAL_API_SMOKE=1 pytest -m live_llm tests/test_real_api_smoke.py
```

网关运维：`bash scripts/butler-gateway-ops.sh status`

## 归档代码

[`../archive/`](../archive/) — Butler v1 快照；[`../reference/`](../reference/) — Hermes 只读对照（勿改）。
