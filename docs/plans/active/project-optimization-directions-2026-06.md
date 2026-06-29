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

### S1 — 宽泛异常吞噬（最大隐患，1296 处）

**Top-15 热点文件**：

| 文件 | `except Exception` 数 | 风险 |
|------|----------------------|------|
| `butler/ops/health_report.py` | 34 | 中（诊断路径不崩是合理的） |
| `butler/core/tool_batch.py` | 30 | **高**（核心路径吞错误） |
| `butler/gateway/locked_phases.py` | 26 | **高**（入站处理隐患） |
| `butler/ops/langfuse_tracer.py` | 24 | 中（可观测 opt-in） |
| `butler/core/agent_loop_phases.py` | 22 | **高**（主循环吞错误） |
| `butler/memory/facade.py` | 21 | 中高 |
| `butler/tools/registry.py` | 17 | 中 |
| `butler/session/memory_prefetch.py` | 17 | 中 |
| `butler/core/context_compressor.py` | 17 | 中高 |
| `butler/gateway/platforms/wechat_ilink/__init__.py` | 16 | 中 |
| `butler/ops/execution_surface_diagnostics.py` | 15 | 低 |
| `butler/memory/diagnostics.py` | 15 | 低 |
| `butler/gateway/message_pipelines.py` | 15 | 中 |
| `butler/permissions/rules.py` | 14 | 中 |
| `butler/gateway/outbound_bridge.py` | 13 | 中 |

**后果**：生产错误被静默吞噬，排障极难；LangFuse/诊断无法观测到被吃掉的异常。

### S2 — 循环依赖（lazy import 预算守门）

- `butler/contracts/` 已建（EventsSink + OwnerGate + BridgeAccess）
- `core/` / `tools/` 直 import `gateway.*` 已 AST 守门（ENG-7）
- 延迟 `from butler.*`：**~3356**（`LAZY_IMPORT_BUDGET=3400`，`tests/test_lazy_import_budget.py`）

### S3 — 大函数 / 大文件残留

**核心路径 Top-5 大函数（ENG-2 已解 delegate，core 尚未触及）**：

| 函数 | 行数 | 文件 | 职责 |
|------|------|------|------|
| `process_tool_calls` | 375 | `core/tool_batch.py` | 工具批执行全流程 |
| `call_llm_with_retry` | ~142（编排） | `core/llm_retry.py` | 子模块 `invoke`/`errors`/`success`/`safe` |
| `compress_messages` | 234 | `core/context_compressor.py` | 上下文压缩 |
| `cmd_doctor` | 229 | `cli/doctor.py` | 诊断命令 |
| `_run_delegate_job_inner` | 226 | `runtime/delegate_job.py` | 异步委派执行 |

**大文件 Top-5（ENG-2 后残留）**：

| 文件 | 行数 |
|------|------|
| `dev_engine/coding_knowledge.py` | 1614 |
| `gateway/platforms/wechat_ilink/phases.py` | 1206 |
| `gateway/platforms/wechat_ilink/__init__.py` | 1120 |
| `core/agent_loop_phases.py` | 859 |
| `butler/orchestrator/` | ~590（门面） |

### S4 — 测试工程（2026-06-29）

- 全量 pytest（排除 corpus）：**0 fail**（ENG-9，6250+ pass）
- 发版以 `butler-pytest-fast-gate.sh` + `butler-eng-domain-gate.sh` 为准
- mypy strict 子集：`butler-mypy-strict-gate.sh` 入 fast-gate

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

**验收**：
- `rg 'except Exception' butler/core/tool_batch.py -c` <= 15
- `rg 'except Exception' butler/core/agent_loop_phases.py -c` <= 10
- fast-gate 绿

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

**验收**：
- 关闭 `BUTLER_EMBEDDING_PROVIDER` → `butler doctor` 输出 WARNING
- `/诊断` 简要显示降级数
- `PYTHONPATH=. pytest tests/test_owner_surface.py -q` 绿

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

**验收**：
- `wc -l` 各新文件 < 150 行
- `PYTHONPATH=. pytest tests/test_cc_p3_p4_features.py tests/test_tool_result_storage.py -q` 绿
- fast-gate 绿

---

#### 方向 D：contracts 层启动（ENG-6 轻量首步）

**目标**：建立 `butler/contracts/` 包，以 Protocol 定义 core→gateway 的接口契约。

**实施路径**：

1. 新建 `butler/contracts/__init__.py` + `events.py`：
   ```python
   from typing import Protocol, Any

   class EventsSink(Protocol):
       def record_generic_event(self, session_key: str, event_type: str, data: dict) -> None: ...
       def record_tool_action(self, session_key: str, tool_name: str, ...) -> None: ...
   ```
2. **竖切**：`butler/core/session_transcript.py` 改为接受 `EventsSink` 注入
3. **Gateway 注册**：`butler/gateway/runner.py` 启动时注册实现
4. **core 验证**：core 单测可不 import gateway 通过

**验收**：
- `butler/contracts/events.py` 存在
- `rg 'from butler.gateway' butler/core/session_transcript.py` = 0
- `PYTHONPATH=. pytest tests/test_delegate_impl_split.py -q` 绿

---

### P2 — 工程治理（07-31 后或低风险窗）

#### 方向 E：pytest 技术债系统清理（ENG-9 续）

**目标**：全量 `pytest tests/`（不含 corpus）fail <= 20。

**实施路径**：
1. 修 `tests/corpus/conftest_gateway.py` 的 `from butler.env_parse` 导入链路（当前阻断全量 pytest）
2. 按域 bisect：`butler-domain-pytest.sh gateway` → `tools` → `memory` → `core`
3. `conftest.py` 增 session-scope env 隔离 fixture（`monkeypatch` 仓库 `.env`）
4. `test_tools_registry` 全面 fixture 化（ENG-9 首步已做 `reset_tool_registry`）

#### 方向 F：静态类型检查渐进引入

**目标**：`butler/contracts/` 和 `butler/tools/delegate_run_state.py` 通过 `mypy --strict`。

**实施路径**：
1. `pyproject.toml` 添加 `[tool.mypy]` 配置（default: `check_untyped_defs = true`）
2. 逐目录 override：先 `contracts/` → `tools/delegate_*.py` → `core/` → `gateway/`
3. CI optional gate（不阻断发版，逐步扩范围）

#### 方向 G：文档卫生清理

**目标**：修正 9 处已识别矛盾。

**实施文件**：
- `docs/architecture/v4-architecture.md`：删除/修正「5040 tests 全部通过」
- `docs/DOCUMENTATION.md`：active 索引补 `software-engineering-refactor`
- `docs/plans/active/software-engineering-refactor-2026-06.md`：文首删「§3.11 待写入」
- `docs/plans/decisions/roadmap-backlog-and-boundaries-2026-05.md`：EXT-5 / P 表历史清理
- `.cursor/rules/`：统一 workflow auto_resume 表述

---

### P3 — 架构演进（远期 / 需决策）

#### 方向 H：记忆系统统一检索入口

- 将 `coding_experiences.json` 纳入 `butler_recall` 可搜范围
- 明确文档：`vector_store.py`（ChromaDB）= 非生产/实验 only
- 评估 Observation Store 从 opt-in 派生升为辅助检索层

#### 方向 I：延迟导入减量

- 目标：3189 → 2000（~37% 减量）
- 手段：contracts Protocol 替代 + 运行时注入 + 按需 import
- 配合 ENG-6/7 分批推进

#### 方向 J：配置面收敛

- 540 项 env 中评估可合并/废弃项
- `check-dead-env.sh` + CI 集成
- 考虑 schema-driven reference.md 自动生成

---

## 四、执行节奏建议

```
现在 → 07-31（G1-04 窗内，低风险优先）
├─ P0-A: 异常治理 top-3 文件（tool_batch → agent_loop_phases → locked_phases）
├─ P0-B: degradation_registry + doctor/诊断 集成
├─ P1-C: process_tool_calls 拆分（ENG-4 关联方向）
└─ P2-G: 文档 9 处矛盾修正（纯文档 PR，随时可做）

07-31 → 08 月（G1-04 结案后）
├─ P1-D: contracts 首步
├─ P2-E: pytest 全域修债
├─ P2-F: mypy 渐进引入
├─ P1-C 续: call_llm_with_retry + compress_messages 拆分
└─ P3-H/I: 架构演进评估决策

持续：
├─ 每周 G1-04 打卡（butler-ops-cadence.sh --weekly）
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
