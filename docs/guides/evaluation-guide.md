# Butler v4 评测体系使用指南

> 如何评估 Butler 的质量：多维评分、基准数据集、LangFuse 集成。  
> 理论依据：父理论 [`v4-theoretical-baseline.md`](../architecture/v4-theoretical-baseline.md) §2.7（OA1-OA3 / OT1-OT2）。

## 架构概览

```
┌──────────────────────────────────────────────┐
│  pytest 测试框架（验证正确性 — CI）           │
│  L1 语料 Mock / L2 Metrics / L3 Bench / L4   │
└───────────────┬──────────────────────────────┘
                │ eval_bridge
                ▼
┌──────────────────────────────────────────────┐
│  LangFuse（质量观测 — 运行时）               │
│  Trace / Score / Dataset / Annotation Queue  │
└──────────────────────────────────────────────┘
```

两套体系**互补不替代**：

| 维度 | pytest | LangFuse |
|------|--------|----------|
| 目的 | pass/fail 正确性 | 质量趋势观测 |
| 时机 | CI / 本地开发 | 生产运行时 |
| 数据 | 预定义 fixture | 真实用户交互 |
| 输出 | 测试报告 | 仪表盘 + 评分 |

## 前置条件

### LangFuse 服务

```bash
cd ~/gongju/langfuse && ./ops.sh up
```

详见 [langfuse-deployment.md](langfuse-deployment.md)（Butler 连接；栈在 `~/gongju/langfuse`）。

### Butler 配置

```bash
BUTLER_LANGFUSE_ENABLED=1
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-butler-dev
LANGFUSE_SECRET_KEY=sk-butler-dev
```

## 评测维度

Butler 使用四维评分体系（`butler/ops/eval_scoring.py`）：

### 1. 意图准确率（Intent Accuracy）

衡量 Butler 是否理解用户的真实意图。

```python
from butler.ops.eval_scoring import score_intent

result = score_intent(
    expected_intent="project_switch",
    actual_intent="project_switch",
    intent_keywords=["切换", "项目"],
)
# result.score → 1.0
```

评分规则：
- 精确匹配意图 → 1.0
- 部分包含 → 0.8
- 关键词命中 → 按比例
- 无匹配 → 0.0

### 2. 工具选择（Tool Selection）

衡量 Butler 是否选择了正确的工具。

```python
from butler.ops.eval_scoring import score_tool_selection

result = score_tool_selection(
    expected_tools=["read_file", "write_file"],
    actual_tools=["read_file", "write_file", "list_directory"],
)
# result.score → 0.9 (recall=1.0, -0.1 penalty for extra tool)
```

评分规则：
- 召回率（预期工具是否使用）为主
- 额外工具每个扣 0.1
- 无工具预期 + 无工具使用 → 1.0

### 3. 回复质量（Response Quality）

衡量回复是否有用、准确、简洁。

```python
from butler.ops.eval_scoring import score_response_quality

result = score_response_quality(
    response_text="创建项目 test 成功，已切换到该项目",
    expected_contains=["创建", "切换"],
    max_lines=5,
)
# result.score → 1.0
```

子项评分：
- `expected_contains`：必须包含的关键词
- `expected_contains_any`：至少包含一个
- `max_lines`：回复长度限制
- 连贯性：非空、有意义内容

### 4. 记忆有效性（Memory Effectiveness）

衡量记忆系统的运行时表现。

```python
from butler.ops.eval_scoring import score_memory_effectiveness

result = score_memory_effectiveness(
    write_survival_rate=0.9,    # S_w: 写入存活率
    first_turn_hit_rate=0.8,    # H_1: 首轮命中率
    decay_error_rate=0.05,      # E_d: 衰减误杀率
)
# result.score → 加权平均
```

三个核心指标（来自 `memory_metrics.py`）：
- **S_w**（Write Survival Rate）：写入的记忆能否被召回？权重 0.4
- **H_1**（First-turn Hit Rate）：首轮预取是否命中？权重 0.4
- **E_d**（Decay Error Rate）：衰减是否误杀重要记忆？权重 0.2（越低越好）

## 评测数据集

### 微信对话数据集

从现有语料目录（`tests/corpus/suites/wechat_real/`）转换为 LangFuse Dataset：

```python
from butler.ops.wechat_dataset import load_and_push_wechat_dataset

summary = load_and_push_wechat_dataset()
# 创建两个 dataset:
#   butler-wechat-single-turn  — 单轮话术
#   butler-wechat-multi-turn   — 多轮对话
```

数据来源：
- `utterance_catalog.yaml`：64+ 条单轮话术
- `production_utterance_catalog.yaml`：生产真实对话
- `utterance_multiturn_catalog.yaml`：22+ 条多轮对话

### 记忆基准数据集

从 MB1-MB7 基准转换为 LangFuse Dataset：

```python
from butler.ops.memory_eval import run_and_push_memory_eval

summary = run_and_push_memory_eval(butler_home)
# 创建 dataset: butler-memory-benchmark
# 推送 7 个 MB 项 + 评分
```

### 开发基准数据集

从 B1-B7 DevEngine 基准推送评分：

```python
from butler.ops.eval_bridge import dev_benchmark_to_scores, push_scores

scores = dev_benchmark_to_scores(report)
push_scores(scores)
```

## 评测桥接（eval_bridge）

桥接层（`butler/ops/eval_bridge.py`）是 pytest ↔ LangFuse 的连接器：

### 推送评分

```python
from butler.ops.eval_bridge import EvalScore, push_scores

scores = [
    EvalScore(name="intent_accuracy", value=0.95, category="wechat"),
    EvalScore(name="tool_selection", value=0.88, category="wechat"),
]
report = push_scores(scores)
```

### 推送数据集项

```python
from butler.ops.eval_bridge import DatasetItem, push_dataset_items, create_dataset

create_dataset("my-eval-set", "Custom evaluation dataset")
items = [
    DatasetItem(
        input={"user_message": "你好"},
        expected_output={"intent": "greeting"},
    ),
]
push_dataset_items("my-eval-set", items)
```

### 转换器

| 函数 | 输入 | 输出 |
|------|------|------|
| `dev_benchmark_to_scores()` | B1-B7 BenchmarkReport | EvalScore[] |
| `memory_benchmark_to_scores()` | MB1-MB7 BenchmarkReport | EvalScore[] |
| `memory_metrics_to_scores()` | SessionMemoryMetrics | EvalScore[] |
| `corpus_run_to_scores()` | 语料跑批结果 | EvalScore[] |

## 组合评分

使用 `score_turn()` 一次性评估单轮交互：

```python
from butler.ops.eval_scoring import score_turn

result = score_turn(
    expected_intent="project_create",
    actual_intent="project_create",
    response_text="已创建项目 test，包含 3 个文件",
    expected_tools=["write_file"],
    actual_tools=["write_file", "list_directory"],
    expected_contains=["创建", "项目"],
    include_memory=True,
    memory_s_w=0.9,
    memory_h_1=0.85,
    memory_e_d=0.02,
)

print(result.overall)           # 0.0 - 1.0
print(result.by_dimension())    # {"intent_accuracy": ..., "tool_selection": ..., ...}

# 推送到 LangFuse
eval_scores = result.to_eval_scores(trace_id="trace-xxx")
push_scores(eval_scores)
```

## 添加新评测 case

### 添加单轮微信话术

在 `tests/corpus/suites/wechat_real/lw_real/utterance_catalog.yaml` 中添加：

```yaml
  - id: CAT-NEW
    user: "新的测试话术"
    category: your_category
    kind: llm  # or command
    expect:
      response_contains: [关键词1, 关键词2]
      tools: [tool_name]
```

### 添加记忆基准

在 `butler/memory/memory_benchmark.py` 中添加新的 `_run_mbN_*` 函数，并注册到 `_ALL_BENCHMARKS`。

### 添加开发基准

在 `butler/dev_engine/dev_benchmark.py` 中添加新的 benchmark task。

## 查看评测结果

### LangFuse 仪表盘

1. 访问 `http://localhost:3000`
2. 进入 "Butler v4" 项目
3. **Traces** → 查看每轮对话的详细追踪
4. **Scores** → 查看评分趋势
5. **Datasets** → 查看结构化评测集
6. **Dashboard** → 总览质量指标

### pytest 报告

```bash
# 微信语料
PYTHONPATH=. pytest tests/corpus/runners/ -q

# 记忆基准
PYTHONPATH=. pytest tests/test_memory_theory_verification.py -q

# 开发基准
PYTHONPATH=. pytest tests/test_dev_engine_theory.py -q

# 评测桥接
PYTHONPATH=. pytest tests/test_eval_bridge.py tests/test_wechat_dataset.py tests/test_memory_eval.py tests/test_dev_eval.py tests/test_delegate_failure_capture.py tests/test_eval_experiment.py tests/test_swebench_live_eval.py tests/test_delegate_judge.py tests/test_tool_routing.py tests/test_assistant_health.py tests/test_wechat_corpus_eval.py tests/test_eval_scoring.py -q
```

## 生产委派失败采集（阶段 2）

开发委派失败或 verify 未通过时，自动写入 LangFuse Dataset `butler-delegate-failures`，并在 trace 上打 `delegate_failure=0` 分。本地审计：`~/.butler/audit/delegate_failures.jsonl`。

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES` | LangFuse 开启时生效 | `1` = 仅 dev 失败；`all` = 所有 role；`0` = 关闭 |

子 Agent trace：同步/后台委派均挂 `delegate:{role}` span（内含 LLM generation 与 tool 链）。

周复盘：

```bash
bash scripts/butler-delegate-failure-review.sh
```

标注流程：LangFuse Traces 筛 `delegate:dev` → 标因（tool_wrong / patch_wrong / no_test / verify_fail）→ 高价值 case 回灌 `B9_TASKS`。

## 开发能力闭环（阶段 3）

### 硬反馈扩展（Dev 域）

`apply_hard_feedback` 除记忆半衰期外，还会根据 LangFuse 分数自动调整：

| 低分指标 | 动作 |
|----------|------|
| `dev_benchmark.pass_rate` | 收紧 coding knowledge（`strict_experience` + 更多 guidance cases） |
| `llm_benchmark.pass_rate` | 提高 delegate rescue（fix rounds / iterations / verify levels） |

覆盖写入 `~/.butler/config/eval_overrides.json`，审计 `~/.butler/audit/eval_feedback.jsonl`。

### LangFuse Experiments

```bash
bash scripts/butler-eval-experiment.sh              # B9 × 4 variants（oracle）
bash scripts/butler-eval-experiment.sh --with-swe   # 附加每周 SWE 子集
```

分数前缀：`eval_experiment.{experiment_id}.{variant}.*`

### SWE 每周 LIVE 子集

```bash
bash scripts/butler-eval-swebench-live.sh
BUTLER_EVAL_LLM_BENCHMARK=1 bash scripts/butler-eval-swebench-live.sh
```

分数前缀：`B8_swebench_live.*`（与 oracle `dev_benchmark.B8_swebench_lite` 区分）

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_EVAL_SWE_LIVE_COUNT` | `3` | 每周轮换实例数 |
| `BUTLER_EVAL_SWE_GATE_MIN_WEEKS` | `2` | 全量入场连续周数；已稳一周可设 `1` 立即入场 |
| `BUTLER_EVAL_DELEGATE_JUDGE` | `heuristic` | 委派完成启发式评分；`off` 关闭 |

每周子集结果写入 `~/.butler/audit/swe_weekly_snapshots.jsonl`（同 ISO 周覆盖更新）。

### SWE-bench Lite 全量 LIVE（门控）

默认连续 **2 周** 子集 3/3（`pass_rate=1.0`）后才允许跑全 15 题；已稳一周可设 `BUTLER_EVAL_SWE_GATE_MIN_WEEKS=1` 立即入场。

```bash
bash scripts/butler-eval-swebench-live-full.sh          # 门控未开则 exit 2
BUTLER_EVAL_SWE_GATE_MIN_WEEKS=1 bash scripts/butler-eval-swebench-live-full.sh  # stretch 入场
bash scripts/butler-eval-swebench-live-full.sh --force  # 跳过门控
BUTLER_EVAL_LLM_BENCHMARK=1 bash scripts/butler-eval-swebench-live-full.sh
```

**里程碑（2026-06-13）**：正式全量 LIVE **15/15**（`BUTLER_EVAL_SWE_GATE_MIN_WEEKS=1`，无 `--force`）。

门控状态：`python3 -c "from butler.ops.swebench_entry_gate import evaluate_swe_full_entry_gate; print(evaluate_swe_full_entry_gate())"`

**自动化（推荐）**：周日 03:30 跑周循环，门控打开后自动接全量 LIVE：

```bash
bash scripts/install-butler-b9-weekly-timer.sh   # systemd user timer
bash scripts/butler-b9-weekly-gate-followup.sh   # 手动：周循环 + 门控则全量
```

## 助手全局健康（阶段 4）

### 工具路由（delegate vs terminal）

生产每轮 `eval_turn` 使用 `tool_routing` 启发式：
- 开发类话术应走 `delegate_task`
- 直接用 `terminal`/`write_file` 修代码 → `delegate_miss` 低分

`tool_selection` / `delegate_routing` 持续偏低时，硬反馈会开启 `delegate_routing_hint` 并注入 Loop。

### 微信语料 → LangFuse

```bash
bash scripts/butler-eval-wechat-corpus.sh
```

分数：`corpus.wechat_gateway.pass_rate`（非开发能力主回归）

### 跨维度同屏

```bash
bash scripts/butler-eval-assistant-health.sh
bash scripts/butler-eval-assistant-health.sh --push   # 写 assistant_health.* 分数
```

张力示例：
- `memory_ok_dev_low` — 记得住但写不对
- `dev_ok_memory_low` — 写得出但上下文丢
- `delegate_routing_low` — 该委派却亲自 terminal

`/诊断` 与 `format_eval_quality_lines` 已包含助手全局段落。

## B9 LLM 端到端基准（O9）

```bash
bash scripts/butler-eval-llm-benchmark.sh                    # 全量 B9 oracle（CI，19 项 LIVE 固定集含 prod-shaped）
BUTLER_EVAL_LLM_BENCHMARK=1 bash scripts/butler-eval-llm-benchmark.sh  # 全量 LIVE

bash scripts/butler-eval-b9-live.sh                          # 周常：10 项 LIVE 固定集
```

LangFuse 评分前缀：`llm_benchmark.*`（`eval_bridge.llm_benchmark_to_scores`）

生产失败回灌：

```bash
bash scripts/butler-delegate-failure-review.sh          # 复盘 + 候选预览
bash scripts/butler-delegate-failure-promote.sh         # 最新一条 → 队列 + Python 脚手架
bash scripts/butler-delegate-failure-promote.sh --bundle  # 导出 candidates.json 审阅包

# 管道演示（审计为空时自动写入一条 demo 行）
bash scripts/butler-delegate-failure-promote-demo.sh
```

LIVE 固定集（`b9_live_fixed_tasks` + `b9_prod_shaped_tasks`）共 **19 项**，含 8 条 prod-shaped（含 6 条已晋升 `B9L_prod_*`）。生产 delegate 周指标见 `butler-b9-weekly-learning.sh` → `prod_delegate_snapshots.jsonl`；需 **2+ 周快照** 才有可信 `prod_delta`（清洗后首周仅作基线）。

经验闭环遥测：`~/.butler/audit/experience_selections.jsonl`（命中）、`experience_lifecycle.jsonl`（renew/demote）。

## 周常一键（推荐）

```bash
bash scripts/butler-eval-weekly.sh
bash scripts/butler-eval-weekly.sh --skip-live      # 不跑 B9/SWE LIVE（省 API）
bash scripts/butler-eval-weekly.sh --no-langfuse    # 离线自检
bash scripts/butler-eval-weekly.sh --with-experiment
```

顺序：回归门 + Dataset 同步 → 微信语料 → B9 LIVE → SWE 子集 LIVE → 助手健康推送 → 委派失败复盘清单。

## 发版回归门（O7）

`butler-deploy.sh update` 在 Step 6 自动运行 B1–B8 + MB1–MB7 基准；可用 `--skip-benchmark` 跳过。

```bash
bash scripts/butler-eval-regression.sh
bash scripts/butler-eval-regression.sh --sync-dataset   # 同步全部评测 Dataset
```

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_EVAL_DEV_PASS_RATE_MIN` | `0.85` | DevEngine 通过率下限 |
| `BUTLER_EVAL_MEM_PASS_RATE_MIN` | `0.7` | Memory 通过率下限 |

审计：`~/.butler/audit/eval_regression.jsonl`

## 评测 Dataset 同步（O8）

`--sync-dataset` 一次推送 LangFuse 上的 5 类 Dataset：

| Dataset | 来源 |
|---------|------|
| `butler-wechat-single-turn` / `butler-wechat-multi-turn` | 微信语料 YAML |
| `butler-memory-benchmark` | MB1–MB7 |
| `butler-dev-benchmark` | B1–B8 + B10 |
| `butler-coding-knowledge-benchmark` | CK T01–T10 |
| `butler-swebench-lite` | SWE-001…015 实例定义 |
| `butler-llm-delegate-benchmark` | B9 任务规格 |

```bash
bash scripts/butler-eval-regression.sh --sync-dataset
bash scripts/butler-wechat-dataset-sync.sh          # 仅微信语料
bash scripts/install-butler-eval-sync-timer.sh      # 每周 systemd timer
```

## 模块索引

| 模块 | 路径 | 职责 |
|------|------|------|
| Eval Bridge | `butler/ops/eval_bridge.py` | benchmark → LangFuse Score 推送 |
| Regression Gate | `butler/ops/eval_regression.py` | B1–B8 / MB1–MB7 发版回归门 |
| WeChat Dataset | `butler/ops/wechat_dataset.py` | 微信语料 → LangFuse Dataset |
| Memory Eval | `butler/ops/memory_eval.py` | MB1-MB7 → LangFuse evaluation |
| Eval Scoring | `butler/ops/eval_scoring.py` | 四维评分函数 |
| LangFuse Tracer | `butler/ops/langfuse_tracer.py` | 运行时追踪 |
