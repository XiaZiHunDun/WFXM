# 语料测试模块 (`tests/corpus`)

开发对话与微信真机场景的**语料驱动回归**，与 `tests/test_gateway_*` 等产品单测互补。

**总体设计**：[`docs/plans/corpus/corpus-testing-module-design-2026-05.md`](../../docs/plans/corpus/corpus-testing-module-design-2026-05.md)

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
| `wechat_real.lw_real` | 分层见 [`suites/wechat_real/lw_real/meta.yaml`](suites/wechat_real/lw_real/meta.yaml) | 见下 |

### 微信真实语料（`wechat_real.lw_real`）

| 层级 | 文件 / 入口 | Runner |
|------|-------------|--------|
| L0 smoke | `reference_utterance_catalog.yaml` | 库存校验 |
| L1 单轮 | 手册 + strict + production | `test_gateway_utterance_catalog.py` |
| L1 变体 | strict 的 `variants` 抽检（llm） | `test_gateway_utterance_variants.py` |
| L1 多轮 | `utterance_multiturn_catalog.yaml` | `test_gateway_multiturn_catalog.py` |
| L2 golden | `corpus.yaml` | `test_gateway_golden.py`（实现仍在 `test_gateway_dev_conversations.py`） |
| L3 live | `meta.live_smoke_ids` | `test_gateway_live_corpus.py`（手动 / nightly） |
| 模块健康 | `meta.yaml` targets | `test_gateway_module_health.py` |

**一键**：`./scripts/corpus-test.sh gateway`（schema + L1 + L2）

**AgentLoop 语料合计**：**183 case**（171 单轮 + 12 多轮组）。规模目标见 [`docs/plans/corpus/corpus-scale-target-2026-05.md`](../../docs/plans/corpus/corpus-scale-target-2026-05.md)。

旧路径 `tests/scenarios/*.yaml` 为**符号链接**，见 [`../scenarios/README.md`](../scenarios/README.md)。

## 命令

```bash
# CI：AgentLoop mock + 语料 schema（不含微信 L1 全量）
PYTHONPATH=. pytest tests/corpus -m "corpus and corpus_mock" -q

# 微信真实语料完整门禁（改 gateway 语料后跑，含变体抽检）
./scripts/corpus-test.sh gateway

# 仅检查生成物未漂移（CI corpus-drift job 同款）
./scripts/corpus-test.sh drift

# 微信 L3 live 子集（需 .env + MINIMAX_API_KEY）
./scripts/corpus-test.sh gateway-live

# 运营快照（production 池 + live 归档统计）
./scripts/corpus-test.sh ops

# 运营门禁 + mock 全量
./scripts/corpus-test.sh gateway-ops

# 阶段 5：AgentLoop + Gateway 统一 mock + intent 交叉门禁
./scripts/corpus-test.sh unified

# PR 改 message_handler / corpus 时（自动检测 diff）
./scripts/corpus-test.sh pr-gate

# 仅 AgentLoop rubric（v1+v2+v3）
PYTHONPATH=. pytest tests/corpus/runners/test_agent_loop_rubric.py -m corpus_mock -q

# Live smoke（各套件 live_smoke_ids）
set -a && source .env && set +a
BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \
  pytest tests/corpus/runners/test_agent_loop_rubric.py -m "corpus_live and corpus_smoke" -v

# Live 全量单轮 + 写归档
BUTLER_RUN_REAL_API_SMOKE=1 CORPUS_ARCHIVE=1 PYTHONPATH=. \
  pytest tests/corpus/runners/test_agent_loop_rubric.py -m corpus_live -v

# 微信话术：主目录 + 严断言参考（CI 默认，~186 条）
PYTHONPATH=. pytest tests/corpus/runners/test_gateway_utterance_catalog.py -q

# 多轮链路（22 条，其中 6 条 ≥5 轮）
PYTHONPATH=. pytest tests/corpus/runners/test_gateway_multiturn_catalog.py -q

# 参考语料全量冒烟（仅清单校验，不参与默认 parametrize）
PYTHONPATH=. pytest tests/corpus/runners/test_gateway_utterance_catalog.py -k reference_smoke -q

# 生成/更新语料文件
python3 scripts/build_reference_strict_catalog.py   # 2.md → strict + multiturn
python3 scripts/generate_production_catalog.py      # 30 条生产脱敏话术
python3 scripts/ingest_reference_user_corpus.py    # 1–5.md → smoke 清单

# 微信 LW-REAL 黄金路径（手写 16 条）
PYTHONPATH=. pytest tests/test_gateway_dev_conversations.py -q
```

或使用：[`scripts/corpus-test.sh`](../../scripts/corpus-test.sh) `mock|smoke|live|archive`

## 新增套件

1. 复制 `suites/_template/` → `suites/<name>/v1/`  
2. 编辑 `corpus.yaml`，在 `registry.yaml` 注册  
3. `channel: agent_loop` 会自动被 `test_agent_loop_rubric.py` 收集  

## 问题地图

- 模板：[`docs/plans/corpus/corpus-issue-map-template-2026-05.md`](../../docs/plans/corpus/corpus-issue-map-template-2026-05.md)
- 合并地图（v1+v2+v3+LW-REAL）：[`docs/plans/corpus/corpus-issue-map-2026-05.md`](../../docs/plans/corpus/corpus-issue-map-2026-05.md)
- 汇总脚本：`python3 scripts/corpus/summarize_runs.py [--write docs/plans/corpus/corpus-issue-map-gateway-latest.md]`
