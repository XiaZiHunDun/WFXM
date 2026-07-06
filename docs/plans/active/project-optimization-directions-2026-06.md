# Butler v4 项目全景分析与优化方向

> **分析日期**：2026-06-26
> **分析范围**：架构 / 代码质量 / 运维 / 记忆 / 测试
> **后续 SSOT**：与 [`software-engineering-refactor-2026-06.md`](active/software-engineering-refactor-2026-06.md) 互补

---

## 一、现状全景

| 维度 | 数据 |
|------|------|
| 代码规模 | 686 Python 文件 / 131K 行生产 + 105K 行测试 |
| 模块分布 | core(124) / ops(73) / tools(62) / gateway(55) / memory(44) / dev_engine(36) / transport(28) / mcp(28) |
| 配置面 | ~540 项 `BUTLER_*` 变量（`.env.example`） |
| 运维脚本 | 159 个 shell 脚本 |
| 产品状态 | P0-P5 done / G1-04 观测至 07-31 / ENG 重构在第二批 |
| 发版标准 | 分层 gate 绿（非全量 pytest） |
| 测试规模 | 642 测试文件 / ~6023 测试函数 |

---

## 二、六大核心发现

### S1 — 宽泛异常吞噬（主模块已 closure，守门 791）

> **2026-07-03 P0-A closure**：batch 1–29（7 对/批）+ mega-batch 30–35（14–16 对/批）完成；**791** gate tests（`butler-p0a-exception-gate.sh`）。主模块 bare `except Exception` 仅余注释/审计字符串（如 `review_static.py`、`github.py` 注释）。扫描：`bash scripts/p0a-scan-remaining.sh`。

**历史 Top-15**（2026-06 扫描；多数已迁 `*_ops.py`）：

| 文件 | 状态 |
|------|------|
| `butler/core/tool_batch.py` | ✅ 0（`tool_batch_finalize_ops`） |
| `butler/core/agent_loop_phases.py` | ✅ 0 |
| `butler/gateway/locked_phases.py` | ✅ P0-A（hygiene + error card 降级） |
| `butler/memory/facade.py` | ✅ 0（`facade_ops`） |
| `butler/tools/registry.py` | ✅ 0（`registry_*_ops`） |
| `butler/transport/auxiliary_client.py` | ✅ batch 30 |
| `butler/dev_engine/*` 评测路径 | ✅ batch 35 |
| `butler/ops/health_report.py` | 诊断聚合（非 batch 范围，可观测 opt-in） |

**后果**：生产错误被静默吞噬，排障极难；LangFuse/诊断无法观测到被吃掉的异常。

### S2 — 循环依赖（lazy import 预算守门）

- `butler/contracts/` 已建（EventsSink + OwnerGate + BridgeAccess）
- `core/` / `tools/` 直 import `gateway.*` 已 AST 守门（ENG-7）
- 延迟 `from butler.*`（**函数内**，AST 计数）：**~3427**（`LAZY_IMPORT_BUDGET=3457`；报告 `scripts/p3i-lazy-import-report.sh`）

### S3 — 大函数 / 大文件残留

**核心路径 Top-5 大函数（P1-C 已拆 `process_tool_calls` / `compress_messages` / `call_llm_with_retry`）**：

| 函数 | 行数 | 文件 | 职责 |
|------|------|------|------|
| `process_tool_calls` | **~108** | `core/tool_batch.py` | 编排器；分发在 `tool_dispatch` |
| `call_llm_with_retry` | **~142**（编排） | `core/llm_retry.py` | 子模块 `invoke`/`errors`/`success`/`safe`/`outcomes` |
| `compress_messages` | **~31**（门面） | `core/context_compressor.py` | 委托 `context_compress_pipeline` |
| `cmd_doctor` | 229 | `cli/doctor.py` | 诊断命令 |
| `_run_delegate_job_inner` | 226 | `runtime/delegate_job.py` | 异步委派执行 |

**大文件 Top-5（ENG-2 后残留）**：

| 文件 | 行数 |
|------|------|
| `dev_engine/coding_knowledge.py` | 1614 |
| `gateway/locked_phases.py` | 826 |
| `core/agent_loop_phases.py` | 906 |
| `gateway/platforms/wechat_ilink/phases.py` | ~1206 |
| `gateway/platforms/wechat_ilink/__init__.py` | ~1120 |

### S4 — 测试工程（2026-06-29）

- 全量 pytest（排除 corpus）：**0 fail**（ENG-9，6250+ pass）
- 发版以 `butler-pytest-fast-gate.sh` + `butler-eng-domain-gate.sh` 为准
- mypy strict 主模块：`butler-mypy-strict-gate.sh`（**826** 模块，`--follow-imports=skip`）入 fast-gate

### S5 — 文档与代码不一致（已收口 2026-06-29）

历史矛盾项已由 ENG/P2-G 与本文修订对齐；发版测试数以分层 gate 为准（见 `agent-testing-strategy`）。

### S6 — 记忆系统架构隐患

- 双向量存储（`SemanticMemoryIndex` SQLite vs `vector_store.py` ChromaDB）定位命名易混
- 编码知识与对话记忆检索不统一（`butler_recall` 不搜 coding_experiences）
- 向量索引与 Store 写入非事务（漂移依赖手动 `butler memory-reindex`）
- 嵌入默认 local hashing（`Recall@3` 仅约 20-40%），保守但影响体验

---

## 三、优化方向（10 个方向，4 档优先级）

### P0 — 生产稳定性（立即可做，07-31 前）

#### 方向 A：异常治理 — 收窄核心路径宽泛 except

**目标**：`tool_batch` / `agent_loop_phases` / `locked_phases` 中 `except Exception` 从 78 处降至 ~30 处。

**实施路径**：

1. **分类**：每个 `except Exception` 标注为：
   - `必要`：确实需要 catch-all 防崩（如 best-effort telemetry）
   - `可收窄`：应换为 `(ImportError, AttributeError)` 等具体类型
   - `应移除`：错误应传播或至少 log.error
2. **核心路径优先**：
   - `butler/core/tool_batch.py`（30处）— 工具分发失败不应静默
   - `butler/core/agent_loop_phases.py`（22处）— 主循环降级应计数
   - `butler/gateway/locked_phases.py`（26处）— 入站失败需 Owner 可见
3. **统一模式**：
   ```python
   # 必要的 catch-all 统一用 _safe_best_effort 包装：
   def _safe_best_effort(fn, *, label: str):
       try:
           return fn()
       except Exception as exc:
           logger.debug("%s skipped: %s", label, exc)
           inc("best_effort_skip", labels={"path": label})
   ```
4. **可观测**：新增 `runtime_metrics` counter `exception_swallowed{path=...}`

**验收**（2026-06-29 守门 `butler-p0a-exception-gate.sh`）：
- `rg 'except Exception' butler/core/tool_batch.py -c` <= 15（当前 **1**：工具分发兜底）
- `rg 'except Exception' butler/core/agent_loop_phases.py -c` <= 10（当前 **0**，已迁 `safe_best_effort`）
- `rg 'except Exception' butler/gateway/locked_phases.py -c` <= 10（当前 **2**：hygiene 健康位 + error card 降级）
- `agent_loop._record_skipped_plugin` → `best_effort_skip` 指标 + `/诊断` ring
- fast-gate 含 P0-A gate

---

#### 方向 B：ENG-8 深化 — 降级全链路显性化

**目标**：任何组件降级在 30s 内可通过 `/诊断` 或 `butler doctor` 发现。

**实施路径**：

1. **启动时检测 + 日志**：
   - `embedding.py` 降级时 `logger.error()`（不仅 debug）
   - `butler doctor` 增加 embedding health 一行（调用 `check_embedding_recall()`）
2. **降级注册表**（轻量版）：
   - 新建 `butler/ops/degradation_registry.py`
   - API：`register_degradation(component, reason)` / `list_degradations()` / `clear(component)`
   - 组件自行注册：embedding、MCP server、memory facade、Skill 合并
3. **`/诊断` 集成**：
   - 简要模式增「降级 N 项」概览行（ENG-8 首步已做 memory 一行，扩展到全组件）
   - 详细模式列出每项 `(component, reason, since_ts)`
4. **Metric**：`degradation_active{component=...}` gauge

**验收**（2026-06-29 守门 `butler-p0b-degradation-gate.sh`）：
- `degradation_registry`：`register`/`clear`/`list` + `degradation_active{component=…}` gauge
- embedding/MCP/memory/Skill/compaction_acl 降级 → `logger.warning` + registry
- `/诊断` 简要「降级 N 项」；详细含 `(持续 Xm)` + best_effort 最近跳过
- `butler doctor` 输出 `[运行降级] ⚠ …` 概览行
- `tests/test_degradation_registry.py` + owner brief 子集绿

---

### P1 — 核心路径可维护性（与 G1-04 并行，低风险）

#### 方向 C：拆解 core 三大函数

**目标**：`process_tool_calls` 编排 **≤150 行**（2026-06-29 已 ~171 行 + `tool_dispatch` 206 行）；**随 tool 批逻辑改动顺带**外提 `tool_batch` 辅助状态，非独立立项。

**`process_tool_calls`（375 行）拆分方案**：

当前结构（读源码后分析）：
```
L297-L328:  pre-processing（truncate + reorder + append assistant msg）— 32 行
L329-L484:  _dispatch_one 内联函数 — 155 行
L486-L571:  辅助内联函数（_transcript_source / _on_start / _on_complete / _precheck_tool）— 85 行
L573-L671:  主循环（parallel vs sequential）+ post-process — 99 行
```

拆法：
1. `butler/core/tool_dispatch.py`：`_dispatch_one()` 提取为独立函数（含 guardrail/cache/two-phase）
2. `butler/core/tool_batch_hooks.py`：`_on_start` / `_on_complete` / `_transcript_source` / `_precheck_tool`
3. `process_tool_calls` 变为 ~80 行编排器

**`call_llm_with_retry`（291 行）拆分方案**：

- ✅ 2026-06-29：`llm_retry_invoke` / `llm_retry_errors` / `llm_retry_success` / `llm_retry_safe`；编排 ~142 行
- ✅ 2026-06-29 续：`llm_retry_outcomes`（interrupt/fail 指标）

**`compress_messages` 拆分**：

- ✅ 2026-06-29 续：`context_compress_pipeline.run_compress_messages` + `context_compress_support` 生命周期钩子

**验收**（守门 `butler-p1c-gate.sh`）：
- `wc -l` 各新文件 < 150 行
- `PYTHONPATH=. pytest tests/test_cc_p3_p4_features.py tests/test_tool_result_storage.py -q` 绿
- fast-gate 绿

---

#### 方向 D：contracts 层启动 — **done** 2026-06-30

**目标**：建立 `butler/contracts/` 包，以 Protocol 定义 core→gateway 的接口契约（ENG-6 轻量首步已超额完成）。

**验收**（2026-06-30 核对）：
- `butler/contracts/events.py` + `sink_registry` + ACL ports（`memory_ports` / `hook_context_ports` 等）
- `rg 'from butler.gateway' butler/core/session_transcript.py` = 0；`core/` 无顶层 gateway import
- `runner.py` → `register_gateway_events_sink()` + `register_gateway_contracts()`
- `PYTHONPATH=. pytest tests/test_delegate_impl_split.py tests/test_contracts_events.py tests/test_core_events_sink_layering.py -q` 绿

---

### P2 — 工程治理（07-31 后或低风险窗）

#### 方向 E：pytest 技术债系统清理 — **done** 2026-06-30

**目标**：分层 gate 全绿 + 全量（不含 corpus）已知 fail 收敛。

**验收**：
- `bash scripts/butler-pytest-bisect.sh` Layers A–E + `DOMAINS=1` → `layer_fail=0`
- `tests/conftest.py` session-scope env 默认 + per-test `BUTLER_*` 隔离（P2-E）
- 全量探测（`pytest tests/ --ignore=tests/corpus`）剩余 **5 fail** → **`4d064b9` 修债**（B11 计数、lazy budget 3650、schema recovery、retry sleep patch）
- 发版仍以 `butler-pytest-fast-gate.sh` + bisect Layers A–D 为准；`RUN_FULL=1` 维护者可选（见 [`pytest-full-suite-bisect-2026-06-30.md`](../decisions/pytest-full-suite-bisect-2026-06-30.md)）

---

#### 方向 F：静态类型检查渐进引入 — **done** 2026-07-06（P2-F 主模块扩面完成）

**目标**：各域主模块（非 `*_ops.py`）通过 `mypy --strict`（`--follow-imports=skip`）。

**验收**（`bash scripts/butler-mypy-strict-gate.sh`）：
- **826** 模块 strict 绿（Batch 36 **741** → Batch 37–44 **826**）：`cli`/`gateway/commands`/`gateway/platforms/wechat_ilink`/`plan`/`prompt_eval`/`execpolicy`/`extensions` 等剩余主模块全部入 gate
- `pyproject.toml` `[tool.mypy.overrides]` 与 gate 列表同步；`p2f-zero-harvest-scan.sh` / `p2f-rebuild-gate.py` 已扩展为 rglob + 新 SCAN_DIRS

**范围外（显式 backlog）**：`*_ops.py`（388 文件）· 无 `--follow-imports=skip` 的全仓库 strict

#### 方向 G：文档卫生清理 — **done** 2026-06-29

**目标**：修正已识别矛盾并与 P0-A/B、P1-C 收口对齐。

**验收**（`bash scripts/butler-p2g-doc-gate.sh`）：
- `v4-architecture`：分层 gate + **6250+** 叙事（无「5040 tests 全部通过」）
- `DOCUMENTATION.md`：`active/` 含 `software-engineering-refactor` + `project-optimization-directions`
- `software-engineering-refactor`：基线表与 ENG-2 `delegate_phases` 门面一致；登记 roadmap §3.11（无「待写入」）
- `roadmap-backlog` §3.6：执行顺序改为窗满/运营导向（非过期「本周」日历）
- `.cursor/rules/butler-v4-source-of-truth.mdc`：`BUTLER_WORKFLOW_AUTO_RESUME=1` 与 `AGENTS.md` 一致
- 本文 §S1–S3、§四 与 P0-A/B、P1-C 守门数据一致

---

### P3 — 架构演进（远期 / 需决策）

#### 方向 H：记忆系统统一检索入口

- 将 `coding_experiences.json` 纳入 `butler_recall` 可搜范围
- 明确文档：`vector_store.py`（ChromaDB）= 非生产/实验 only
- 评估 Observation Store 从 opt-in 派生升为辅助检索层

#### 方向 I：延迟导入减量 — **进行中** 2026-07-06（P3-I Batch 2–8）

- **基线**：函数内 **3593** → 当前 **3427**（−166；模块顶 **~1401**）
- **目标**：→ **2000**（长期；Batch 9+ 继续 top 文件 helper/hoist）
- **手段**：文件内 helper 合并 + 安全模块顶 hoist（`safe_best_effort` / `env_parse` / gateway 簇）
- **Batch 2–8 已做**：`chat_cli` · `info_commands` · `slash_dispatch` · `message_pipelines` · `handler_helpers` · `wechat_ilink/adapter` · `outbound_bridge` · `completion_notify` · `locked_phases`（langfuse）· `agent_loop_phases` · `workflows/runner` · `tool_batch` · `health_report` · `task_orchestrator` · `context_compressor`
- **门禁**：`p3i-lazy-import-report.sh` 已挂 **ENG domain gate**

#### 方向 J：配置面收敛 — **进行中** 2026-07-06（P3-J Batch 2–4）

- ~540 项 env（`.env.example`）；`p3j-env-hygiene-gate.sh` + **`p3j-env-audit.sh`** + **`p3j-env-schema-poc.py`**
- **Batch 2–4**：显式 reference 行（`BUTLER_ENABLE_GIT_WRITE` / `DELEGATE_COMPLETION_MODE` / `TOOLS_ENGINE_FORCE_OFF` / `INSTRUCTION_WALKUP`）· Deprecated/Legacy 附录 · **fast-gate** 挂 p3j

---

## 四、执行节奏建议

```
已完成（2026-07-06）
├─ P0-A/B · P1-C · P2-G · P1-D · P2-E · P2-F（mypy **826** 主模块）✅
└─ P3-H 记忆统一检索 Phase 1–3 + lead 剖面 rollout（2026-07-02）✅

现在 → 07-31（G1-04 窗内）
├─ 每周 G1-04 打卡（butler-ops-cadence.sh --weekly）
├─ 07-27: TCR strict flip（见 ops 日历）
└─ 07-31: G1-04 窗满结案（butler-g1-04-closure-check.sh）

进行中（2026-07-06）
├─ P3-I Batch 1：AST lazy-import 计数 + report + memory_cli hoist
└─ P3-J Batch 1：p3j-env-hygiene-gate → eng-domain gate

Backlog（G1-04 结案后加深）
├─ P3-I：locked_phases / chat_cli / info_commands 懒 import 减量
├─ P3-J：env 差集审计 · 废弃 key 标记
└─ P2-F-ops（可选）：388 个 *_ops.py strict

持续：
├─ 改 gateway 后 restart
└─ 发版走 fast-gate + pre-release-smoke
```

---

## 五、与已有 ENG 线的映射

| 优化方向 | 对应 ENG | 关系 |
|----------|----------|------|
| A (异常治理) | **新增 ENG-13** | S1 独立问题域 |
| B (降级显性化) | ENG-8 续 | 深化到全组件 |
| C (core 拆分) | ENG-4 扩展 | 加入 tool_batch/llm_retry |
| D (contracts) | ENG-6 | 轻量首步竖切 |
| E (pytest) | ENG-9 续 | 系统清理 |
| F (类型检查) | **新增 ENG-14** | 全新方向 |
| G (文档卫生) | — | 独立低成本 |
| H (记忆统一) | — | 远期架构决策 |
| I (延迟import) | ENG-6/7 间接 | contracts 完成后自然减量 |
| J (配置收敛) | ENG-10 关联 | 扩展 |

---

## 六、风险评估

| 方向 | 行为变更风险 | 回滚难度 | 建议 |
|------|-------------|---------|------|
| A (异常治理) | **中**（可能暴露之前隐藏的错误） | 低（git revert） | 逐文件 PR + canary 观测 |
| B (降级注册) | 低（新增模块，无侵入） | 低 | 直接做 |
| C (core 拆分) | 低（纯 extract，行为不变） | 低 | 逐函数 PR |
| D (contracts) | 低（新增 Protocol，渐进替换） | 低 | 先竖切 1 条验证 |
| E (pytest) | 无（测试代码） | 无 | 随时可做 |
| F (mypy) | 无（新增 check，不改代码） | 无 | CI optional |
| G (文档) | 无 | 无 | 随时可做 |
