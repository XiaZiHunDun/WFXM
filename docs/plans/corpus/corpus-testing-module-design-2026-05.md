# 语料测试模块 — 总体设计方案

> **状态**：设计稿（2026-05-23）  
> **目标**：把分散在 `tests/test_dev_assistant_corpus*.py`、`tests/scenarios/*.yaml`、`tests/corpus_harness.py` 的语料评测，收敛为 **`tests/corpus/` 独立模块**，支持持续扩充、统一 live 归档、宏观问题地图。  
> **原则**：语料（数据）与执行器（代码）分离；mock 验管道、live 验模型；失败先归档再改产品。

---

## 一、为什么要独立成模块

| 现状问题 | 模块化后 |
|----------|----------|
| v1/v2/v3 各一份 `test_*.py`，逻辑重复 | 一套 **Suite Runner**，按注册表加载 |
| YAML 在 `tests/scenarios/`，与 gateway 场景混放 | `suites/<name>/corpus.yaml` 按套件归档 |
| live 结果散落在对话记录里 | `archive/runs/` 标准化 JSON/MD |
| 文档在 `docs/plans/*-analysis*.md` 分散 | 每套件 `README.md` + 总览 `tests/corpus/README.md` |
| 与产品单测（gateway、memory）耦合认知 | CI 可只跑 `pytest tests/corpus -m corpus` |

语料测试的定位：**回归「正常中文开发对话」的质量与路由**，不是替代 `test_gateway_*` 的协议单测，而是与其 **互补合并分析**。

---

## 二、目录结构（目标态）

```text
tests/corpus/
├── README.md                 # 模块入口：命令、分层、如何加套件
├── __init__.py
├── conftest.py               # 语料专用 fixture、marker 注册、suite 参数化
├── registry.yaml             # 套件清单（id → 路径 → runner → markers）
│
├── harness/                  # 共享执行库（从 tests/corpus_harness.py 迁入）
│   ├── __init__.py           # 对外 re-export 稳定 API
│   ├── loader.py             # load_corpus、校验 schema
│   ├── keywords.py           # assert_keywords、build_canonical_answer
│   ├── agent_loop.py         # make_live_loop、DEFAULT_LIVE_PROMPT
│   └── archive.py            # 写 live run 报告
│
├── schemas/
│   └── corpus-suite-v1.yaml  # meta/case 字段约定（见第三节）
│
├── suites/
│   ├── dev_assistant/        # 开发助手问答（AgentLoop + rubric）
│   │   ├── README.md
│   │   ├── v1/
│   │   │   ├── corpus.yaml   # 自 tests/scenarios/dev_assistant_corpus.yaml 迁入
│   │   │   └── meta.yaml     # 条数、维度、live_smoke、文档链接
│   │   ├── v2/
│   │   └── v3/
│   │
│   ├── wechat_real/          # 微信真机衍射（Gateway + mock LLM 脚本）
│   │   ├── README.md
│   │   └── lw_real/
│   │       ├── corpus.yaml   # 自 wechat_dev_conversations.yaml
│   │       └── fixtures/     # 项目模板、期望文件内容
│   │
│   └── _template/              # 新套件复制用
│       ├── corpus.yaml
│       ├── meta.yaml
│       └── README.md
│
├── runners/                  # 按 channel 分的 pytest 实现
│   ├── test_agent_loop_rubric.py   # 通用：单轮/多轮/mock/live
│   └── test_gateway_scripted.py    # 通用：LW-REAL 类场景
│
└── archive/
    ├── README.md             # 如何填 run 报告
    └── runs/
        └── .gitkeep
        # 示例：2026-05-23-v2-v3-minimax.jsonl
```

**文档**（保持 `docs/plans/`，链接到模块）：

- 生成方案：`dev-assistant-corpus-v3-generation-scheme-2026-05.md`
- 单次 live 归档：`corpus-live-run-YYYY-MM-DD.md`（或由 `archive.py` 生成）
- 宏观问题地图：`corpus-issue-map-YYYY-MM.md`（人工归纳，引用 archive）

---

## 三、语料数据模型（Corpus Suite v1）

### 3.1 套件级 `meta`

```yaml
meta:
  suite_id: dev_assistant.v3      # 全局唯一，用于 registry 与 archive
  version: "2026-05-23-v3"
  title: 开发助手语料 v3
  channel: agent_loop             # agent_loop | gateway_wechat | cli（扩展）
  live_provider: minimax
  live_model: MiniMax-M2.7
  dimensions: [conversational, ...]  # 用于统计与问题地图
  generation_doc: docs/plans/corpus/dev-assistant-corpus-v3-generation-scheme-2026-05.md
```

### 3.2 用例级 `cases[]`

**单轮：**

```yaml
- id: DA3-01
  dimension: conversational
  title: 先梳理步骤不写代码
  user: |
    用户原话（口语化）
  # Rubric（至少一组）
  must_contain: [可选，硬词≤1]
  must_contain_any: [同义词组1]
  must_contain_any2: [同义词组2]
  must_not_contain: [可选，安全/风格]
  # 分析用（不参与 assert，供归档）
  tags:
    intent: clarify          # clarify | implement | diagnose | compare | delegate
    difficulty: L2
    expected_route: lead     # lead | delegate | tool（Butler 专用）
```

**多轮：**

```yaml
- id: DA3-MT01
  dimension: multi_turn
  title: ...
  turns:
    - user: ...
      must_contain_any: [...]
```

**Gateway  scripted（wechat_real）：**

```yaml
- id: LW-REAL-01
  dimension: delegation
  user: 用户微信原话
  expect:
    tools_called: [write_file]
    report_success: true
    reply_contains_any: [完成, 已]
  setup: lingwen1_minimal   # conftest 中的项目 fixture 名
```

> v1 仅规范 **agent_loop rubric** 与 **gateway expect** 两套；CLI 语料后续增加 `channel: cli`。

### 3.3 `live_smoke_ids`

每套件 5～8 条代表性 ID；CI 不跑全量 live，发版前人工或 nightly 跑全量。

### 3.4 Schema 校验（L0）

`harness/loader.py` 在收集阶段校验：

- `suite_id`、`cases[].id` 唯一
- 单轮不得有 `turns`；多轮必须有 ≥2 `turns`
- `must_contain_any` 编号连续（any、any2、any3…）
- YAML 危险字符（`%`、`反引号`）规范（引号或 `|` 块）

失败在 `TestCorpusSchema` 一层报出，不进入 mock/live。

---

## 四、执行器（Runner）设计

### 4.1 通道对照

| channel | 执行环境 | 通过条件 | 现有套件 |
|---------|----------|----------|----------|
| `agent_loop` | `AgentLoop` + MiniMax/mock | `status==completed` + rubric | dev_assistant v1/v2/v3 |
| `gateway_wechat` | `ButlerMessageHandler` + mock LLM 脚本 | 工具/报告/回复关键词 | LW-REAL |
| `cli`（预留） | `cli_harness` | 输出片段匹配 | — |

### 4.2 测试分层（统一 marker）

在 `pyproject.toml` 增加（与现有 `live_llm` 并存）：

| Marker | 含义 | 默认 CI |
|--------|------|---------|
| `corpus` | 所有语料模块测试 | ✅ 跑 |
| `corpus_mock` | mock / schema / gateway 脚本 | ✅ 跑 |
| `corpus_live` | 真实 LLM（继承 `live_llm`） | ❌ 跳过 |
| `corpus_smoke` | live 子集 | ❌ 跳过 |

约定：`corpus_live` 隐式依赖 `BUTLER_RUN_REAL_API_SMOKE=1`（复用 `test_real_api_smoke._require_smoke_enabled`）。

### 4.3 通用 AgentLoop Runner（消灭三份重复 test 文件）

```text
registry.yaml
    └── suite_id: dev_assistant.v3
            path: suites/dev_assistant/v3/corpus.yaml
            runner: agent_loop_rubric
            pytest_class: TestAgentLoopRubricSuite  # 参数化 suite_id
```

一个测试类流程：

```text
load corpus → schema test
→ parametrize case_id (single)
→ mock: build_canonical_answer → assert_keywords
→ live (optional): make_live_loop → run → assert status + keywords
→ parametrize mt_id (multi)
```

套件差异仅 **YAML 路径** 与 **meta**，不再复制 `test_dev_assistant_corpus_v2.py` 全文。

### 4.4 Gateway Runner

`test_gateway_scripted.py` 读取 `wechat_real/lw_real/corpus.yaml`，复用 `test_gateway_dev_conversations.py` 中的 setup fixture 表（`lingwen1_minimal` 等），将 **场景 ID → 断言** 数据化。

---

## 五、工作流程（与你认可的宏观路线对齐）

```mermaid
flowchart LR
  A[槽位表 / 生成方案] --> B[编写 corpus.yaml]
  B --> C[L0 schema pytest]
  C --> D[L1 corpus_mock 全量]
  D --> E[L2 corpus_live 一轮]
  E --> F[archive/runs 归档]
  F --> G[问题地图 按维度/失败类型]
  G --> H[产品优化方案]
  H --> B
```

### 5.1 扩充语料

1. 复制 `suites/_template/`  
2. 填 `meta.suite_id`、`cases`（参考 v3 生成方案五元组）  
3. 在 `registry.yaml` 注册  
4. 只跑新套件：`pytest tests/corpus -k dev_assistant.v4`

### 5.2 Live 归档字段（`archive.py` 输出 JSONL）

每行一条：

```json
{
  "run_id": "2026-05-23T12:00:00Z",
  "suite_id": "dev_assistant.v3",
  "case_id": "DA3-18",
  "dimension": "data_engineering",
  "status": "failed",
  "loop_status": "tool_limit",
  "fail_type": "tool_limit",
  "note": "未完成最终回复",
  "model": "MiniMax-M2.7",
  "response_excerpt": "前 500 字"
}
```

`fail_type` 枚举（问题地图用）：

| 类型 | 含义 |
|------|------|
| `keyword_miss` | rubric 未命中 |
| `tool_limit` | AgentLoop 工具轮次用尽 |
| `empty_reply` | 无 final_response |
| `wrong_intent` | 答非所问（人工标） |
| `unsafe_ok` | 该拒绝却给出危险操作 |
| `gateway_tool` | 未调期望工具 |
| `gateway_report` | 委派报告不符 |

### 5.3 问题地图（宏观优化输入）

按 **维度 × fail_type** 聚合计数，例如：

- `product_butler` + `wrong_intent` → 调 Lead 提示/路由  
- `devops` + `tool_limit` → 提高 `max_iterations` 或拆任务  
- `safety_bounds` + `unsafe_ok` → 安全策略 P0  

**不在 live 失败时立即改 yaml 收紧**；先累计 2 轮 live 再调 rubric。

---

## 六、CI 与本地命令

```bash
# 模块全部 mock（秒级，进 CI）
PYTHONPATH=. pytest tests/corpus -m "corpus and corpus_mock" -q

# 某一套件
PYTHONPATH=. pytest tests/corpus -k "dev_assistant.v3" -q

# Live smoke（6～8 条/套件）
set -a && source .env && set +a
BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \
  pytest tests/corpus -m "corpus_live and corpus_smoke" -v

# Live 全量 + 写归档（发版前 / 每周）
BUTLER_RUN_REAL_API_SMOKE=1 CORPUS_ARCHIVE=1 PYTHONPATH=. \
  pytest tests/corpus -m corpus_live -v
```

可选包装脚本：`scripts/corpus-test.sh smoke|full|archive`（实现阶段再加）。

---

## 七、与现有三套的关系

| 现路径 | 目标路径 | runner |
|--------|----------|--------|
| `tests/scenarios/dev_assistant_corpus.yaml` | `suites/dev_assistant/v1/corpus.yaml` | agent_loop_rubric |
| `tests/scenarios/dev_assistant_corpus_v2.yaml` | `suites/dev_assistant/v2/corpus.yaml` | 同上 |
| `tests/scenarios/dev_assistant_corpus_v3.yaml` | `suites/dev_assistant/v3/corpus.yaml` | 同上 |
| `tests/scenarios/wechat_dev_conversations.yaml` | `suites/wechat_real/lw_real/corpus.yaml` | gateway_scripted |
| `tests/corpus_harness.py` | `tests/corpus/harness/` | — |
| `tests/test_dev_assistant_corpus*.py` | `runners/test_agent_loop_rubric.py` | 合并参数化 |
| `tests/test_gateway_dev_conversations.py` | `runners/test_gateway_scripted.py` | 逻辑迁移 |

**统计（当前未迁移前）**：

| 套件 | 条数 | 通道 |
|------|------|------|
| dev_assistant v1 | 12～35（工作区） | agent_loop |
| dev_assistant v2 | 34 | agent_loop |
| dev_assistant v3 | 39 | agent_loop |
| LW-REAL | 16 | gateway_wechat |

合计约 **100+** 条语料场景（含多轮轮次）。

---

## 八、迁移计划（分阶段，降低风险）

### Phase 0 — 文档与骨架 ✅

- [x] 本设计文档  
- [x] `tests/corpus/README.md`、`registry.yaml`、`schemas/`、`_template/`  
- [x] `harness/` 从 `corpus_harness.py` **re-export**

### Phase 1 — 注册表 + 通用 Runner ✅

- [x] `runners/test_agent_loop_rubric.py` 读 registry（v1/v2/v3 参数化）  
- [x] `runners/test_v1_butler_lead.py`（DA-01 委派）  
- [x] 旧 `test_dev_assistant_corpus*.py` → `pytest.skip` 占位

### Phase 2 — 全量迁移 v1/v2/v3 YAML ✅

- [x] `suites/dev_assistant/v{1,2,3}/corpus.yaml`  
- [x] CI 推荐：`pytest tests/corpus -m corpus_mock`  
- [x] `tests/scenarios/` 符号链接 + README

### Phase 3 — LW-REAL ✅（YAML 迁入；实现仍在 gateway 测试）

- [x] `suites/wechat_real/lw_real/corpus.yaml`  
- [x] `runners/test_gateway_scripted.py`（schema）  
- [ ] 将 `test_gateway_dev_conversations.py` 逐步数据驱动（可选后续）

### Phase 3b — 微信真实语料模块（分层门禁）✅

- [x] `schemas/gateway-utterance-v1.md` — L0～L3 字段约定  
- [x] `suites/wechat_real/lw_real/meta.yaml` — targets + coverage_matrix  
- [x] `registry.yaml` — `runner_modules` / `catalog_tiers` / `runner_roles`  
- [x] `harness/gateway_meta.py` + `runners/test_gateway_module_health.py`  
- [x] `./scripts/corpus-test.sh gateway` — L0 health + L1 单轮/多轮 + L2 黄金路径  
- [x] `./scripts/corpus-test.sh drift` — 生成脚本与 YAML 一致  
- [x] `suites/wechat_real/lw_real/README.md` + `wechat-real-coverage-matrix-2026-05.md`  
- [x] L3 live：`live_smoke_ids` → `test_gateway_live_corpus.py`（`./scripts/corpus-test.sh gateway-live`）

### Phase 3b-3 — 执行层收敛（L2 golden + L3 live）✅

- [x] `test_gateway_golden.py` — `corpus.yaml` 索引校验 + 收集 `dev_conversations` 实现  
- [x] `test_gateway_live_corpus.py` — `meta.live_smoke_ids` 驱动真 API 抽检  
- [x] `harness/gateway_golden.py`、`harness/gateway_live.py`  
- [x] `corpus-test.sh gateway` 改走 golden runner；新增 `gateway-live`

### Phase 3b-2 — 质量门禁与覆盖矩阵 ✅

- [x] `validate_coverage_matrix()` — 每维度 ≥2 strict 或 ≥1 多轮  
- [x] `test_gateway_utterance_variants.py` — llm 变体抽检（≤40）  
- [x] `harness/gateway_scripts.py` — mock script 单点维护  
- [x] CI job `corpus-drift` — 生成脚本与 YAML 一致  
- [x] `scripts/corpus/promote_production.py` — production → strict 升格

### Phase 4 — 归档与问题地图 ✅（基础）

- [x] live runner 集成 `CORPUS_ARCHIVE=1` → `archive/runs/`  
- [x] `docs/plans/corpus/corpus-issue-map-template-2026-05.md`  
- [x] `scripts/corpus-test.sh`  
- [ ] optional：GitHub Action nightly live smoke

### Phase 4b — 微信 production 运营闭环 ✅

- [x] `docs/plans/corpus/wechat-corpus-ops-2026-05.md` — 回流 / 升格 / 月度指标  
- [x] `scripts/corpus/append_production.py` — 脱敏句入池  
- [x] `scripts/corpus/promote_production.py` — 升格 + `promotion_history`  
- [x] `scripts/corpus/summarize_runs.py` — 归档 → issue map 草稿  
- [x] `harness/gateway_ops.py` + `test_gateway_production_ops.py`  
- [x] `./scripts/corpus-test.sh ops` / `gateway-ops`

### Phase 5 — AgentLoop ↔ Gateway 协同 ✅

- [x] `schemas/corpus-intent-v1.md` + `intent_crosswalk.yaml`  
- [x] `harness/corpus_intent.py` + `test_corpus_cross_channel.py`  
- [x] `scripts/corpus/build_intent_crosswalk.py`  
- [x] `./scripts/corpus-test.sh unified` / `pr-gate`  
- [x] [`corpus-cross-channel-2026-05.md`](corpus-cross-channel-2026-05.md)

---

## 九、新套件 checklist（给后续扩充）

- [ ] `meta.suite_id` 唯一  
- [ ] `registry.yaml` 已注册  
- [ ] `dimensions` 与问题地图维度一致  
- [ ] mock 全绿  
- [ ] `live_smoke_ids` 覆盖主要维度  
- [ ] `suites/<x>/README.md` 说明来源（真实对话 / 合成）  
- [ ] 生成方案文档链接（若有）  

---

## 十、决策记录

| 决策 | 理由 |
|------|------|
| 语料放 `tests/corpus/suites/` 而非 `butler/` 包内 | 评测数据非运行时配置；避免打进 wheel |
| 不删 rubric 逐条断言 | mock 保管道；live 保回归；宽松 any 组降漂移 |
| 保留 `live_llm` marker | 与全库 real API smoke 一致，CI `addopts` 已排除 |
| 新增 `corpus_*` marker | 可单独订阅语料 job，不与 120+ 产品单测混跑 |
| 问题地图与语料解耦 | 地图是分析产物，不塞进 yaml |

---

## 十一、下一步建议

1. **确认目录名**：`tests/corpus/` vs `tests/eval_corpus/`（推荐前者，简短）。  
2. **执行 Phase 0～1**：我可以按本设计落地骨架 + v3 走 registry runner。  
3. **统一跑一轮 live**：v2+v3 归档后写首份 `corpus-issue-map-2026-05.md`。  

如无异议，默认按 **Phase 0 + Phase 1（v3 试点）** 实施迁移。
