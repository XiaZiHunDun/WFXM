# Butler v4 ↔ autoresearch 对照与提炼报告

> **状态**：分析完成（2026-05-25）；**主线 D 已落地**（PR6，见 [`four-reports-improvement-roadmap-2026-05.md`](four-reports-improvement-roadmap-2026-05.md) §9）  
> **本地对照代码**：`reference/autoresearch/`（gitignore，主公维护）  
> **Butler 事实来源**：`docs/architecture/v4-architecture.md`、`butler/` 实现  
> **原则**：只借鉴**研究组织**设计，零新增依赖；不引入 GPU 训练栈

---

## 1. 执行摘要

**autoresearch**（Karpathy, 2026）解决的是：**自主「改代码 → 固定评测 → 保留/丢弃」通宵闭环**，而非更强的 LLM Agent Loop。

**Butler v4** 已是完整对话型 Agent 平台（自建 Loop、微信 Gateway、runtime/workflow、语料 harness）。与 autoresearch 相比：

| 维度 | autoresearch 更强 | Butler 更强 |
|------|-------------------|-------------|
| 实验组织 | 不可变 harness、单文件可写面、TSV 账本、git advance/reset | — |
| Agent 运行时 | — | 压缩/队列/委派/观测/人工门控 |
| 产品形态 | 单机 overnight 研究 | 微信管家、多项目、运营 |

**结论**：最值得提炼的是 **harness 边界 + 实验账本 + 固定预算单指标 + keep/discard + 长输出 grep 卫生**；不宜照搬「永不询问用户」的通宵自治进默认微信路径。

---

## 2. autoresearch 架构速览

### 2.1 三文件分工

| 文件 | 角色 | 谁改 |
|------|------|------|
| `prepare.py` | 数据、常量、`TIME_BUDGET=300`、`evaluate_bpb()` | **禁止** Agent 修改 |
| `train.py` | 模型、优化器、训练循环 | **唯一** Agent 可改文件 |
| `program.md` | 分支命名、实验循环、日志、自治章程 | **人类**迭代（「研究组织代码」） |

### 2.2 评测与可比性

- **固定墙钟**：训练段恒为 5 分钟（`TIME_BUDGET`），改架构/批量仍可比。
- **单主指标**：`val_bpb`（validation bits per byte），越低越好，与 vocab 无关。
- **机器可读尾部**：脚本结束打印 `val_bpb:`、`peak_vram_mb:` 等；Agent 只 `grep` 这些行，完整日志进 `run.log`。

### 2.3 实验状态机

```text
LOOP:
  1. 改 train.py → git commit
  2. uv run train.py > run.log 2>&1
  3. grep 关键指标（或 tail 栈追踪判 crash）
  4. 写入 results.tsv（不提交 git）
  5. 指标改善 → 保留 commit（advance 分支）
     否则 → git reset 丢弃
```

`results.tsv` 列：`commit | val_bpb | memory_gb | keep|discard|crash | description`

### 2.4 program.md 关键章程

- 实验分支：`autoresearch/<tag>`，每轮独立 tag。
- **简洁性准则**：同等指标下更简单优先；删代码且指标不变/更好必 keep。
- **Crash 分类**：蠢错（typo）可修；想法必崩记 crash 跳过。
- **上下文卫生**：禁止 tee 洪水；禁止循环中问用户「要继续吗」（通宵自治）。
- **超时**：>10 分钟 kill，按失败 discard。

### 2.5 train.py 实现要点（非迁移目标）

- Fast-fail：`NaN` 或 `loss > 100` 立即退出。
- 固定 eval harness 调用 `prepare.evaluate_bpb`。
- 与 Butler 无关：Muon、Flash Attention、单 GPU 训练等。

---

## 3. Butler v4 现状（对照基线）

详见 [`v4-architecture.md`](../architecture/v4-architecture.md)。与本报告相关模块：

| 能力 | 路径 | 说明 |
|------|------|------|
| Agent Loop | `butler/core/agent_loop.py` | 压缩、工具批、委派、流式预取 |
| 工具与权限 | `butler/tools/registry.py`、`butler/permissions.py` | patch/terminal 等；`.butler/permissions.yaml` |
| Runtime 任务 | `butler/runtime/`、`runtime/jobs.yaml` | 只读/变更、timeout、子进程 |
| Workflow | `butler/workflows/` | DAG + `requires_approval` |
| 人工门控 | `butler/human_gate.py` | 微信确认链 |
| 语料评测 | `tests/corpus_harness.py`、`docs/plans/corpus-testing-module-design-2026-05.md` | harness + archive 设计 |
| 目标循环 | `butler/core/goal_loop.py` | `BUTLER_GOAL_LOOP=0`，`/循环` 最多 20 轮 |
| 对话回滚 | `butler/core/transcript_revert.py` | 截断 transcript，**不**恢复工作区代码 |
| 运行指标 | `butler/ops/runtime_metrics.py` | `/诊断` 零依赖指标 |

**外部对标规划**（Prometheus/OpenClaw 等）已收口，见 [`reference-learning-plan-2026-05.md`](reference-learning-plan-2026-05.md)。autoresearch 属**新专题**：「自主实验组织」，仍零依赖。

---

## 4. 概念映射表

| autoresearch | Butler 近似 | 差距 |
|--------------|-------------|------|
| `prepare.py` 不可变评测 | `runtime` 子进程、`tests/corpus/harness` | 缺项目级**单一不可变 harness** 约定 |
| 只改 `train.py` | `patch`/`write_file` 任意路径 | 无**可写范围白名单**（研究模式） |
| `TIME_BUDGET` | `JobDef.timeout_seconds` | 无**横向对比用统一实验预算** |
| `val_bpb` | job `success` + `summary`、语料 rubric | 无**标量 metric 驱动 keep/discard** |
| `results.tsv` | runtime audit、transcript | 无**实验矩阵账本** |
| `git reset` 丢弃 | `/回滚` transcript | 无**代码级回滚**与实验绑定 |
| `program.md` | Skills、Lead system prompt | 缺简洁性准则、grep 章程等 |
| log + grep | tool spill、prune | 可加强 terminal **默认摘要策略** |
| NEVER STOP | `goal_loop`（默认关） | 产品需人在回路，不宜默认通宵 |

---

## 5. 提炼建议（按优先级）

### P0 — 高兼容、建议优先

#### 5.1 双层边界：Harness（只读）+ Experiment Surface（可写）

**目标目录约定**（项目层）：

```text
projects/<name>/
  .butler/harness/          # permissions deny，Agent 不可 patch
    eval.sh 或 eval.py      # 固定入口；stdout 打印 metric_value=...
  experiments/              # 或单一 experiments/main.py
  .butler/experiments.tsv   # gitignore 实验账本
```

**衔接**：`butler/permissions.py`、`run_runtime_job`（只读）调用 harness。

#### 5.2 实验账本（results.tsv 模式）

建议列（TSV 或 JSONL）：

```text
timestamp  git_sha  metric_name  metric_value  cost_mb  status  hypothesis
```

- `status`：`keep | discard | crash`
- 展示：`/诊断` 或 `list_runtime_jobs` 附最近 N 条

#### 5.3 长输出上下文卫生

- Job 模板：输出重定向到 `.butler/last_run.log`
- 只读后处理或 Skill 规则：**禁止**把 >200 行原样贴回模型；只 grep `metric_*=` 等前缀行

#### 5.4 固定预算 + 单一主指标

| 场景 | 固定预算 | 主指标示例 |
|------|----------|------------|
| runtime job | 统一 `timeout_seconds` | 解析 `METRIC name=value` |
| corpus live | case `max_tokens` | rubric 分 / keyword 命中 |
| 研究用 goal | 每轮 wall-clock 上限 | 项目自定义 scalar |

`jobs.yaml` 可先文档约定 `metrics:` / `budget_seconds:`，再考虑 schema 扩展。

---

### P1 — 需「研究模式」开关

#### 5.5 Keep / Discard 与 Git

- `BUTLER_EXPERIMENT_MODE=1`：仅 `experiments/` 可写；harness deny
- 指标未改善：`git reset --hard <best_sha>`（**仅**实验分支 + CLI/cron，不进默认微信）
- 与 `goal_loop` 分离：goal 是自然语言多轮；experiment 是**标量驱动**改代码

#### 5.6 简洁性准则

写入 Lead Skill / `post_compact_cleanup` 锚点 / `delegate_task` 模板：

- 同等指标 → 更简单优先
- 删代码且指标 ≥ 基线 → keep
- 微小提升 + 高复杂度 → discard

#### 5.7 可迭代「研究组织 Skill」

archetype `software-research`：内置 `PROGRAM.md`（分支、TSV、grep、crash 策略）；人类改 Skill，Agent 只读执行。

#### 5.8 Fast-fail 与 Crash 分类

- runtime：OOM/timeout → `crash` 记入账本，同一 hypothesis 连续 crash 可 block
- 与 `tool_guardrails`、`failure_tracker` 对齐

---

### P2 — 参考或子集，不默认产品化

| autoresearch | Butler 处理 |
|--------------|-------------|
| NEVER STOP 通宵 | 仅 cron/CLI + 显式开关；微信保持门控 |
| 每轮 git commit | 必须实验分支隔离 |
| 训练实现细节 | 不迁移 |

---

## 6. 与现有 Butler 规划衔接

| 已有能力 | autoresearch 加强 |
|----------|-----------------|
| `tests/corpus` harness + archive | 增加 keep/discard、git_sha 列 |
| `runtime/jobs.yaml` | metric 解析、实验分支文档 |
| `goal_loop` | 不合并；另设 experiment_loop（可选） |
| `human_gate` / workflow approval | harness 自动跑；**代码 advance** 仍批准 |
| `reference-learning-plan`（已关闭） | 本报告为独立新线，零依赖 |

---

## 7. 落地路线

### 阶段 A — 文档 + 模板（1–2 天）

1. 本报告入 [`plans/README.md`](README.md) 索引  
2. 项目 archetype 示例：`harness/eval.sh`、`experiments/README.md`  
3. `.gitignore`：`.butler/experiments.tsv`、`.butler/last_run.log`  
4. Lead Skill 片段：简洁性 + grep 规范  

### 阶段 B — 轻量代码（约 1 周，零依赖）

1. `permissions.yaml` 模板 deny `harness/**`  
2. runtime enrich：解析约定 metric 前缀行  
3. `/诊断` 展示最近实验行  
4. 可选 CLI：`butler experiment record` / `best`  

### 阶段 C — 研究模式（产品决策后）

1. `BUTLER_EXPERIMENT_MODE` + git 分支策略  
2. metric 比较 + 受控 `git reset`  
3. corpus nightly + 项目 harness 双指标  

---

## 8. 明确不做

- GPT 训练 / Muon / Flash Attention 等实现迁移  
- 默认微信路径通宵无人值守、无批准 mutating  
- 在无分支隔离的 main 上自动每轮 commit  
- 把 Loop 收成 autoresearch 式单文件编辑（与 v4 模块化相反）  

---

## 9. 总结

autoresearch 的价值在 **「可对比、可回滚、可记账的实验组织协议」**，不在 Agent Loop。Butler 应把 harness 边界、实验账本、标量 metric、keep/discard 与 **corpus harness**、**runtime jobs** 对齐，而非再造训练栈。

---

## 附录：autoresearch 仓库文件清单

```text
reference/autoresearch/
  prepare.py      # 不可变：数据、TIME_BUDGET、evaluate_bpb
  train.py        # 可变：模型与训练
  program.md      # 组织章程
  README.md
  pyproject.toml
  analysis.ipynb
```
