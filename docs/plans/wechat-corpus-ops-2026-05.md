# 微信真实语料 — 运营闭环（阶段 4）

> 套件：`wechat_real.lw_real`  
> 设计：[`corpus-testing-module-design-2026-05.md`](corpus-testing-module-design-2026-05.md)

## 1. 流程总览

```text
真机/内测脱敏话术
    → append_production.py（L4 池）
    → mock CI（gateway 全量）
    → 稳定 2 周 + live 抽检通过
    → promote_production.py（升格 strict）
    → 更新 coverage_matrix / issue map
```

## 2. 命令

| 步骤 | 命令 |
|------|------|
| 新增脱敏句 | `python3 scripts/corpus/append_production.py --user "…" --kind llm --script … --expect-json '…'` |
| 升格 strict | `python3 scripts/corpus/promote_production.py PROD-001` |
| 运营快照 | `python3 scripts/corpus/summarize_runs.py` |
| 写 issue 草稿 | `python3 scripts/corpus/summarize_runs.py --write docs/plans/corpus-issue-map-gateway-YYYY-MM.md` |
| Live + 归档 | `CORPUS_ARCHIVE=1 ./scripts/corpus-test.sh gateway-live` |
| Mock 门禁 | `./scripts/corpus-test.sh gateway` |

## 3. 月度指标（建议）

| 指标 | 目标 | 数据来源 |
|------|------|----------|
| production 池规模 | ≥30，每月 +3～5 | `production_utterance_catalog.yaml` |
| 本月升格数 | ≥2 | `REF-PROMO-*` / `promoted_from` |
| live 通过率 | ≥80% | `archive/runs/*.jsonl` |
| mock 回归 | 100% | `./scripts/corpus-test.sh gateway` |

## 4. Live 归档

设置环境变量后跑 live：

```bash
export CORPUS_ARCHIVE=1
export CORPUS_RUN_ID=2026-05-gateway-live-1
./scripts/corpus-test.sh gateway-live
python3 scripts/corpus/summarize_runs.py --suite wechat_real.lw_real
```

归档字段见 `tests/corpus/harness/archive.py`。

## 5. 与问题地图

1. 跑 `summarize_runs.py --write docs/plans/corpus-issue-map-gateway-YYYY-MM.md`  
2. 合并 AgentLoop 地图：[`corpus-issue-map-template-2026-05.md`](corpus-issue-map-template-2026-05.md)  
3. 在「宏观 backlog」登记 P0/P1（路由、委派、报告缓存等）

## 6. 升格准则

- mock +（可选）live 通过  
- 具名 `script` + 严 `expect`（非 `generic_ack`）  
- `source_file` 可追溯  
- 升格后跑 `./scripts/corpus-test.sh gateway` 与 `drift`（若动生成脚本）
