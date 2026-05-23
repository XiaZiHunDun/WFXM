# 语料测试模块 (`tests/corpus`)

开发对话与微信真机场景的**语料驱动回归**，与 `tests/test_gateway_*` 等产品单测互补。

**总体设计**：[`docs/plans/corpus-testing-module-design-2026-05.md`](../../docs/plans/corpus-testing-module-design-2026-05.md)

## 目录

```text
corpus/
├── registry.yaml           # 套件注册表
├── harness/                # loader、keywords、agent_loop、archive、registry
├── schemas/                # Corpus Suite v1 约定
├── suites/                 # 语料 YAML（权威路径）
├── runners/                # pytest 执行器
└── archive/runs/           # live 归档 JSONL
```

## 已注册套件

| suite_id | 条数（约） | Runner |
|----------|------------|--------|
| `dev_assistant.v1` | 35（33 单轮 + 2 多轮） | `test_agent_loop_rubric.py` + `test_v1_butler_lead.py` |
| `dev_assistant.v2` | 34 | `test_agent_loop_rubric.py` |
| `dev_assistant.v3` | 39 | `test_agent_loop_rubric.py` |
| `dev_assistant.v4` | 36 | `test_agent_loop_rubric.py` |
| `dev_assistant.v5` | 39 | `test_agent_loop_rubric.py` |
| `wechat_real.lw_real` | 55 话术目录 + 48 数据驱动 + 16 LW/DEV 手写 | `test_gateway_utterance_catalog.py` + `test_gateway_dev_conversations.py` |

**AgentLoop 语料合计**：**183 case**（171 单轮 + 12 多轮组）。规模目标见 [`docs/plans/corpus-scale-target-2026-05.md`](../../docs/plans/corpus-scale-target-2026-05.md)。

旧路径 `tests/scenarios/*.yaml` 为**符号链接**，见 [`../scenarios/README.md`](../scenarios/README.md)。

## 命令

```bash
# CI：全部语料 mock + schema（推荐）
PYTHONPATH=. pytest tests/corpus -m corpus_mock -q

# 仅 AgentLoop rubric（v1+v2+v3）
PYTHONPATH=. pytest tests/corpus/runners/test_agent_loop_rubric.py -m corpus_mock -q

# Live smoke（各套件 live_smoke_ids）
set -a && source .env && set +a
BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \
  pytest tests/corpus/runners/test_agent_loop_rubric.py -m "corpus_live and corpus_smoke" -v

# Live 全量单轮 + 写归档
BUTLER_RUN_REAL_API_SMOKE=1 CORPUS_ARCHIVE=1 PYTHONPATH=. \
  pytest tests/corpus/runners/test_agent_loop_rubric.py -m corpus_live -v

# 微信话术目录（数据驱动 48 条）
PYTHONPATH=. pytest tests/corpus/runners/test_gateway_utterance_catalog.py -q

# 微信 LW-REAL 黄金路径（手写 16 条）
PYTHONPATH=. pytest tests/test_gateway_dev_conversations.py -q
```

或使用：[`scripts/corpus-test.sh`](../../scripts/corpus-test.sh) `mock|smoke|live|archive`

## 新增套件

1. 复制 `suites/_template/` → `suites/<name>/v1/`  
2. 编辑 `corpus.yaml`，在 `registry.yaml` 注册  
3. `channel: agent_loop` 会自动被 `test_agent_loop_rubric.py` 收集  

## 问题地图

- 模板：[`docs/plans/corpus-issue-map-template-2026-05.md`](../../docs/plans/corpus-issue-map-template-2026-05.md)
- 合并地图（v1+v2+v3+LW-REAL）：[`docs/plans/corpus-issue-map-2026-05.md`](../../docs/plans/corpus-issue-map-2026-05.md)
- 汇总脚本：`python3 scripts/summarize_corpus_run.py [path/to/run.jsonl]`
