# 开发助手语料 v3 — 索引与测试说明

> **生成方案**：[`dev-assistant-corpus-v3-generation-scheme-2026-05.md`](dev-assistant-corpus-v3-generation-scheme-2026-05.md)  
> **语料**：[`tests/corpus/suites/dev_assistant/v3/corpus.yaml`](../../tests/corpus/suites/dev_assistant/v3/corpus.yaml)  
> **测试**：[`tests/corpus/runners/test_agent_loop_rubric.py`](../../tests/corpus/runners/test_agent_loop_rubric.py)

---

## 规模

| 类型 | 数量 | ID |
|------|------|-----|
| 单轮 | 36 | DA3-01 … DA3-36 |
| 多轮 | 3×3 轮 | DA3-MT01 … DA3-MT03 |
| **合计** | **39** | |

---

## 分簇（12 维 × 3）

| 维度 | ID | 侧重点 |
|------|-----|--------|
| conversational | 01～03 | 先澄清、改口、要思路 |
| code_review | 04～06 | 竞态、注入、单测污染 |
| performance | 07～09 | P99、大列表、pprof |
| observability | 10～12 | OOM、trace、PromQL |
| api_design | 13～15 | 兼容、版本、Webhook 幂等 |
| data_engineering | 16～18 | Airflow、Spark、CDC |
| incident_ops | 19～21 | 连接打满、回滚、5xx |
| git_advanced | 22～24 | rebase、cherry-pick、submodule |
| messaging | 25～27 | Kafka、Rabbit、MQTT |
| graphql_api | 28～30 | N+1、cursor、extensions |
| product_butler | 31～33 | LingWen1、委派进度、简短/详细 |
| safety_bounds | 34～36 | 拒删库、拒直改 prod、拒泄密钥 |

---

## 命令

```bash
# Mock（CI）
PYTHONPATH=. pytest tests/corpus/runners/test_agent_loop_rubric.py -k dev_assistant.v3 -m corpus_mock -q

# Live smoke（6 单轮）
set -a && source .env && set +a
BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \
  pytest -m corpus_live tests/corpus/runners/test_agent_loop_rubric.py -k dev_assistant.v3::TestCorpusV3LiveMiniMax::test_live_smoke_subset -v

# Live 全量 36 单轮
BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \
  pytest -m corpus_live tests/corpus/runners/test_agent_loop_rubric.py -k dev_assistant.v3::TestCorpusV3LiveMiniMax::test_live_single_turn_full -v

# Live 多轮 3 组
BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \
  pytest -m corpus_live tests/corpus/runners/test_agent_loop_rubric.py -k dev_assistant.v3::TestCorpusV3LiveMiniMax::test_live_multi_turn -v
```

---

## live_smoke 抽样（6）

DA3-01（对话控制）、07（性能）、19（事故）、28（GraphQL）、31（Butler 项目句）、34（安全边界）。

---

## 建议的 live 归档字段

跑完一轮后填入 `docs/plans/corpus-live-run-YYYY-MM.md`：

`id | dimension | status | fail_type | note`

`fail_type` 枚举：`keyword_miss` | `tool_limit` | `empty_reply` | `wrong_intent` | `unsafe_ok`（该拒未拒）

---

## 与 v2 合并统计

三套 mock 通过后，再**统一**跑 v2+v3 live，做问题地图；勿在 live 失败时逐条收紧断言，先归档再定优化方案。
