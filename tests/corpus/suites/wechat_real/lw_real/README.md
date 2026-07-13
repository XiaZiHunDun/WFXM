# wechat_real.lw_real — 微信真实语料套件

**Schema**：[`../../../schemas/gateway-utterance-v1.md`](../../../schemas/gateway-utterance-v1.md)  
**元数据**：[`meta.yaml`](meta.yaml)  
**覆盖矩阵**：[`docs/plans/corpus/wechat-real-coverage-matrix-2026-05.md`](../../../../../docs/plans/corpus/wechat-real-coverage-matrix-2026-05.md)

## 分层文件

| 层级 | 文件 | 说明 |
|------|------|------|
| L0 | `reference_utterance_catalog.yaml` | 冒烟清单（不默认 parametrize） |
| L1 单轮 | `utterance_catalog.yaml`、`reference_utterance_strict.yaml`、`production_utterance_catalog.yaml` | CI 严断言 |
| L1 多轮 | `utterance_multiturn_catalog.yaml` | 会话链 |
| L2 | `corpus.yaml` | 黄金路径 → `test_gateway_golden.py` |
| L3 | `meta.yaml` → `live_smoke_ids` | `test_gateway_live_corpus.py` |

## 一键命令

```bash
# 微信语料模块（推荐）
./scripts/corpus-test.sh gateway

# 生成物与仓库一致（CI）
./scripts/corpus-test.sh drift

# 重新生成 YAML
python3 scripts/build_reference_strict_catalog.py
python3 scripts/ingest_reference_user_corpus.py
python3 scripts/generate_production_catalog.py
```

## 新增语料

1. **手册级**：编辑 `utterance_catalog.yaml`（CAT/SMK/P1）。  
2. **参考 REAL-\***：改 `reference/用户语料/2.md` 后跑 `build_reference_strict_catalog.py`。  
3. **生产脱敏**：编辑 `production_utterance_catalog.yaml` 或跑 `generate_production_catalog.py`。  
4. **多轮**：编辑 `utterance_multiturn_catalog.yaml` 或改 build 脚本中 `build_multiturn_catalog()`。  
5. 更新 `meta.yaml` 的 `targets` / `coverage_matrix`（若规模变化）。

## 阶段 2 能力

| 能力 | 入口 |
|------|------|
| 维度覆盖门禁 | `test_gateway_module_health.py`（`coverage_matrix`） |
| 变体抽检（llm） | `test_gateway_utterance_variants.py`（默认 40 条） |
| 脚本库共享 | `harness/gateway_scripts.py` |
| production 升格 | `python3 scripts/corpus/promote_production.py PROD-001` |
| L3 live 子集 | `./scripts/corpus-test.sh gateway-live` |
| L4 运营 | [`wechat-corpus-ops`](../../../../../docs/plans/corpus/wechat-corpus-ops-2026-05.md) · `./scripts/corpus-test.sh ops` |
| 跨通道 | [`corpus-cross-channel`](../../../../../docs/plans/corpus/corpus-cross-channel-2026-05.md) · `intent_crosswalk.yaml` |

## 升格流程（production → strict）

1. 在 `production_utterance_catalog.yaml` 验证通过。  
2. 复制到 `utterance_catalog.yaml` 或 `reference_utterance_strict.yaml`，改 `id` 与 `source_file`。  
3. 从 production 文件移除或保留作归档。
