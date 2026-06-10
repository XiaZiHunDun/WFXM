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
./scripts/langfuse-setup.sh
```

详见 [langfuse-deployment.md](langfuse-deployment.md)。

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
PYTHONPATH=. pytest tests/test_eval_bridge.py tests/test_wechat_dataset.py tests/test_memory_eval.py tests/test_eval_scoring.py -q
```

## B9 LLM 端到端基准（O9）

```bash
bash scripts/butler-eval-llm-benchmark.sh                    # oracle（CI）
BUTLER_EVAL_LLM_BENCHMARK=1 bash scripts/butler-eval-llm-benchmark.sh  # 真实 delegate
```

LangFuse 评分前缀：`llm_benchmark.*`（`eval_bridge.llm_benchmark_to_scores`）

## 发版回归门（O7）

`butler-deploy.sh update` 在 Step 6 自动运行 B1–B8 + MB1–MB7 基准；可用 `--skip-benchmark` 跳过。

```bash
bash scripts/butler-eval-regression.sh
bash scripts/butler-eval-regression.sh --sync-dataset   # 同时同步微信语料
```

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_EVAL_DEV_PASS_RATE_MIN` | `0.85` | DevEngine 通过率下限 |
| `BUTLER_EVAL_MEM_PASS_RATE_MIN` | `0.7` | Memory 通过率下限 |

审计：`~/.butler/audit/eval_regression.jsonl`

## 微信语料 Dataset 同步（O8）

```bash
bash scripts/butler-wechat-dataset-sync.sh
bash scripts/install-butler-eval-sync-timer.sh   # 每周 systemd timer
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
