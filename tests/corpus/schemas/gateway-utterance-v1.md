# Gateway 话术语料约定 v1 (`gateway-utterance-v1`)

> 适用于 `wechat_real.lw_real` 下各 `*_catalog.yaml` 与 `utterance_catalog.yaml`。  
> 机器校验：`tests/corpus/harness/gateway_catalog.py`、`tests/corpus/runners/test_gateway_scripted.py`。

## 分层（tier / quality / runner）

| 层级 | 文件 | `runner` | CI 默认执行 |
|------|------|----------|-------------|
| **L0** smoke | `reference_utterance_catalog.yaml` | `reference_smoke` | 仅 schema + 库存测试 |
| **L1** strict 单轮 | `utterance_catalog.yaml`、`reference_utterance_strict.yaml`、`production_utterance_catalog.yaml` | 缺省或 `production` | `test_gateway_utterance_catalog.py` |
| **L1** multiturn | `utterance_multiturn_catalog.yaml` | — | `test_gateway_multiturn_catalog.py` |
| **L2** golden | `corpus.yaml` → `lingwen_real_dialogue` | `legacy` | `test_gateway_dev_conversations.py` |
| **L3** live | `meta.live_smoke_ids` 引用 catalog id | — | 可选 `corpus_live`（待接） |

- `quality: strict` — 具名 `script` + 严 `expect`（`uses_delegate`、`file_exists` 等）。
- `quality: smoke` — 宽覆盖清单，仅保证在册与去重。

## 单条 utterance 字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | ✅ | 套件内唯一，如 `CAT-01`、`REF-STRICT-*`、`PROD-*` |
| `user` | ✅ | 用户原话（微信口语） |
| `kind` | ✅ | `command` \| `detail` \| `llm`（`multi` 仅 catalog 索引） |
| `fixture` | | `lingwen` \| `dual` \| `lingwen_workflow`，默认 `lingwen` |
| `script` | llm 时 | 见 `test_gateway_utterance_catalog._script_profiles()` |
| `setup` | | 会话/磁盘前置，如 `cached_report_delete`、`prior_delegate_create_hello` |
| `expect` | ✅ | 见下表 |
| `tier` | | `handbook` \| `reference` \| `production` |
| `quality` | | `strict` \| `smoke` |
| `runner` | | `legacy` \| `reference_smoke` \| `production` |
| `variants` | | 口语变体列表；阶段 2 对 `kind: llm` 抽检（见 `test_gateway_utterance_variants.py`） |
| `source_file` | | 溯源，如 `reference/用户语料/2.md` |

### `expect` 常用键

| 键 | 说明 |
|----|------|
| `response_contains` / `response_contains_any` | 回复子串 |
| `response_excludes` | 禁止出现 |
| `response_max_lines` | 行数上限 |
| `no_llm` | 命令/详细路由不得调 LLM |
| `uses_delegate` | 必须调用 `delegate_task` |
| `tools_include` / `tools_exclude` | 工具名 |
| `no_write_tools` | 不得 write/delegate |
| `file_exists` / `file_missing` | 项目内路径 |

## 多轮 `multiturn_catalog[]`

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | ✅ | 如 `MT-01` |
| `description` | | 场景说明 |
| `fixture` | | 同单轮 |
| `setup` | | 链级前置 |
| `turns` | ✅ | 有序轮次列表 |

每轮 `turns[]` 项：同单条字段（`user`、`kind`、`script`、`expect`、`setup`），可选 `session_key`（如 `wechat:u2`）。

## 生成脚本

| 脚本 | 输出 |
|------|------|
| `scripts/build_reference_strict_catalog.py` | `reference_utterance_strict.yaml`、`utterance_multiturn_catalog.yaml` |
| `scripts/ingest_reference_user_corpus.py` | `reference_utterance_catalog.yaml` |
| `scripts/generate_production_catalog.py` | `production_utterance_catalog.yaml` |

CI 应用 `scripts/corpus/check_corpus_drift.sh` 防止生成物与仓库不一致。
