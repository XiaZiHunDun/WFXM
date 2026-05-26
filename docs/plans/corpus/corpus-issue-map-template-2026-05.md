# 语料 Live 问题地图 — YYYY-MM

> 数据来源：`tests/corpus/archive/runs/<run_id>.jsonl`（`CORPUS_ARCHIVE=1`）  
> 设计：[`corpus-testing-module-design-2026-05.md`](corpus-testing-module-design-2026-05.md)

## 跑批信息

| 字段 | 值 |
|------|-----|
| run_id | |
| 日期 | |
| 模型 | MiniMax-M2.7 |
| 套件 | dev_assistant.v2, v3, … |

## 汇总（按 fail_type × dimension）

| dimension | keyword_miss | tool_limit | empty_reply | wrong_intent | unsafe_ok | gateway_* | 合计 |
|-----------|--------------|------------|-------------|--------------|-----------|-----------|------|
| conversational | | | | | | | |
| product_butler | | | | | | | |
| … | | | | | | | |

## 代表失败用例（优先 P0）

| case_id | fail_type | 现象 | 初步归因 | 优化项 |
|---------|-----------|------|----------|--------|
| | | | | |

## 宏观优化 backlog

1. **P0** — 
2. **P1** — 
3. **P2** — 

## 微信 Gateway（`wechat_real.lw_real`）

> 自动生成草稿：`python3 scripts/corpus/summarize_runs.py --write docs/plans/corpus-issue-map-gateway-YYYY-MM.md`  
> 运营手册：[`wechat-corpus-ops-2026-05.md`](wechat-corpus-ops-2026-05.md)

| 指标 | 值 |
|------|-----|
| production 池 | |
| 本月升格 | |
| live 通过率 | |
| mock gateway | `./scripts/corpus-test.sh gateway` |

### Gateway 失败代表用例

| case_id | fail_type | 现象 | 归因 | 优化 |
|---------|-----------|------|------|------|
| | | | | |

## 下一轮语料扩充

- 待补维度：
- 待补真实话术来源：
- production 回流（脱敏）：
