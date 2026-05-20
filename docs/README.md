# Butler 文档索引

> 更新：2026-05-20 | 当前主线：**Butler v4**（自建 Agent Loop）

## 推荐阅读顺序

| 文档 | 说明 |
|------|------|
| [`v4-architecture.md`](v4-architecture.md) | **当前架构**：Loop 栈、Gateway、观测、测试规模 |
| [`hermes-extraction-map.md`](hermes-extraction-map.md) | Hermes → Butler 提炼对照与验收状态 |
| [`design.md`](design.md) | 完整产品设计（记忆、Skill、编排、命令速查） |
| [`manual-testing-guide.md`](manual-testing-guide.md) | CLI / 微信人工测试流程 |
| [`.env.example`](../.env.example) | 环境变量与真实 API smoke 门控 |

## 版本演进（历史参考）

| 文档 | 说明 |
|------|------|
| [`v1-vs-v3-comparison.md`](v1-vs-v3-comparison.md) | v1 自研 vs v3 嵌入式 Hermes |
| [`v3-architecture-comparison.md`](v3-architecture-comparison.md) | v3 架构快照（**已 superseded**，见 v4） |

## 验证命令

```bash
# 默认全量单测（733 passed，排除 8 项 live_llm）
cd /home/ailearn/projects/WFXM
PYTHONPATH=. pytest -q

# 可选：真实 API smoke（需 API Key + BUTLER_RUN_REAL_API_SMOKE=1）
BUTLER_RUN_REAL_API_SMOKE=1 pytest -m live_llm tests/test_real_api_smoke.py
```

## 归档

- `archive/butler-v1/` — v1 代码与旧版 `docs/`，仅供对照，非当前实现。
