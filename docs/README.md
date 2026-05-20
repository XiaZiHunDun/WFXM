# Butler 文档索引

> 更新：2026-05-20 | 当前主线：**Butler v4**（自建 Agent Loop）  
> 仓库目录说明：[`../STRUCTURE.md`](../STRUCTURE.md)

## 推荐阅读顺序

| 文档 | 说明 |
|------|------|
| [`architecture/v4-architecture.md`](architecture/v4-architecture.md) | **当前架构**：Loop 栈、Gateway、观测、测试规模 |
| [`architecture/hermes-extraction-map.md`](architecture/hermes-extraction-map.md) | Hermes → Butler 提炼对照与验收状态 |
| [`architecture/hermes-decoupling.md`](architecture/hermes-decoupling.md) | **解耦路线图**（目标：零 Hermes 黑盒依赖）|
| [`design/design.md`](design/design.md) | 完整产品设计（记忆、Skill、编排、命令速查） |
| [`guides/manual-testing-guide.md`](guides/manual-testing-guide.md) | CLI / 微信人工测试流程 |
| [`.env.example`](../.env.example) | 环境变量与真实 API smoke 门控 |

## 版本演进（历史）

见 [`history/README.md`](history/README.md)（v1 / v3 对照文档）。

## 验证命令

```bash
cd /home/ailearn/projects/WFXM
PYTHONPATH=. pytest -q

# 可选真实 API smoke
BUTLER_RUN_REAL_API_SMOKE=1 pytest -m live_llm tests/test_real_api_smoke.py
```

## 归档代码

[`../archive/`](../archive/) — Butler v1 快照；[`../reference/`](../reference/) — Hermes 只读对照（勿改）。
