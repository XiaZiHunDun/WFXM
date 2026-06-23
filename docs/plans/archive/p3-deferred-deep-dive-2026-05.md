# P3 未做项深度分析（2026-05-22）

> **历史文档**：下文三项（记忆双轨、`/health` 抽取、微信 `/steer`）**均已落地** — 见 [`memory-unification-implementation-2026-05.md`](../archive/memory-unification-implementation-2026-05.md)、[`health-report-refactor-2026-05.md`](../archive/health-report-refactor-2026-05.md)、[`wechat-steer-implementation-2026-05.md`](../archive/wechat-steer-implementation-2026-05.md)。**勿**据此排期；活跃 backlog 见 [`post-consolidation-roadmap-2026-05.md`](../active/post-consolidation-roadmap-2026-05.md) 与 [`roadmap-backlog-and-boundaries-2026-05.md`](../decisions/roadmap-backlog-and-boundaries-2026-05.md)。
>
> **状态**：规划分析（非实施承诺，**仅作 ADR 考古**）  
> **前置**：[`consolidation-p3-implementation-2026-05.md`](../archive/consolidation-p3-implementation-2026-05.md) 已完成；本文对应其中「本轮不做」三项。  
> **原则**：影响面越大，方案与验收越细；实施前需 ADR + 专门回归，不并入日常小熵减。

---

## 0. 总览与优先级

| 优先级 | 项 | 影响面 | 若不处理的主要风险 | 建议轨道 |
|--------|-----|--------|-------------------|----------|
| **P0** | 记忆双轨合并 | **极高**（数据一致性、M1–M4、post_session、工具写入） | Agent 工具写入与轮次预取/诊断可能读到不同内存对象；post_session 双入口 | **D.1 + 记忆 ADR**（先于大规模运营） |
| **P1** | `/health`·`/诊断` 重构 | **中高**（运维可见性、静默回归） | 三分支重复导致改一处漏一处；真机排障文案漂移 | **A.4**（发版前快照测试加固） |
| **P2** | 微信 `/steer` | **中**（产品语义 + 多会话并发） | 全局 steer 与网关 per-session 锁冲突；用户误以为可插队 | **D.3 或独立 ADR**（按需） |

```text
推荐实施顺序：记忆双轨（P0）→ /health 抽取（P1）→ /steer 产品+网关（P2）
```

与 [`post-consolidation-roadmap-2026-05.md`](../active/post-consolidation-roadmap-2026-05.md) 映射：**记忆**属轨道 D 配置/架构债；**/health** 支撑轨道 A 运营与 C.2 诊断可读；**/steer** 属体验增强，非灵文验收阻塞项。

---

## 1. 记忆双轨合并（最高优先级）

### 1.1 现状：不是「两个目录」，而是「两条运行时管线」

存储 SSOT 已在 `butler/memory/`（`ButlerMemory`、`ProjectMemory`、语义索引、诊断）。  
`butler/memory_plugin.py`（`ButlerMemoryService` / `ButlerMemoryProvider`）是 **Hermes 迁型遗留的 Facade**，仍承担：

| 职责 | 实际调用方 | 使用的内存对象 |
|------|------------|----------------|
| 轮次预取注入 | `session_lifecycle.prefetch_turn_memory` → `attach_turn_memory_prefetch` | **`orchestrator.butler_memory`** + `_project_memory` |
| 系统提示静态块 | `orchestrator.build_memory_context` | 同上 |
| 回合同步（可选回声） | `sync_turn_memory` | `butler_memory.experience` + **`memory_provider.sync_turn`** |
| 工具 `butler_remember` / `butler_recall` | `tools/memory_tools.py` | 优先 **`orch.memory_provider._butler_global`** |
| 缓冲后 post_session | `memory_provider.sync_turn` → 满 8 条触发 | **`provider._butler_global` / `_project_memory`** |
| `/new` 会话结束提炼 | `trigger_session_end` | **`orchestrator.butler_memory`**（非 provider） |

**关键事实**：网关主路径 **从不** 调用 `memory_plugin.prefetch()`；预取逻辑以 `session_lifecycle` 为准（含 hybrid/semantic/向量 profile、项目 facts 等）。  
`memory_plugin.prefetch()` 仍是较旧的 FTS 路径，属于 **死分叉**，增加阅读成本。

### 1.2 一致性风险（必须正视）

`ButlerOrchestrator` 在初始化时：

```python
provider = ButlerMemoryService()
provider.initialize(...)  # 内部 _reload_butler_global() → 新建 ButlerMemory
self.memory_provider = provider
```

同时 `orchestrator.butler_memory` 按租户懒建 **另一套** `ButlerMemory`（`_memory_by_tenant`）。  
项目切换时 `_refresh_memory_provider_for_project_switch` 只 reload provider 分支，**不会** 把 `butler_memory` 与 `provider._butler_global` 绑成同一实例。

因此：

1. **工具写入路径**：`butler_remember` → `provider._butler_global`  
2. **预取/诊断路径**：`prefetch_turn_memory` → `orchestrator.butler_memory`  
3. 二者通常落同一磁盘（`~/.butler`），但 **进程内缓存**（语义索引、profile 向量、`_project_memory` 句柄）可能短暂不一致。  
4. **post_session 双入口**：  
   - `/new` → `trigger_session_end` 用 `orchestrator.butler_memory`  
   - 每 4 轮 provider 缓冲 → `memory_plugin._trigger_background_extraction` 用 `provider._butler_global`  
   可能重复提炼或在一侧看不到另一侧刚写入的缓存。

`memory_tools._memory_service()` 在 fallback 时会 `svc._butler_global = orch.butler_memory` 打补丁，但 **正常网关路径** 走 `orch.memory_provider`，补丁不生效。

**运营影响**：灵文 Lead 记忆 P0–P2 已验收，但「Agent 说已记住 vs `/诊断` 预取未命中」类问题，排查时应先查 **是否双实例 + 缓存未 reload**，而非先怀疑模型。

### 1.3 目标架构（建议 ADR 结论方向）

```text
ButlerOrchestrator
  └── memory: MemoryFacade（单例门面）
        ├── butler_global: ButlerMemory   # 唯一实例，按 tenant
        ├── project: ProjectMemory | None # 与 project_manager 同步
        ├── prefetch(query, role, diagnostics)  # 迁自 session_lifecycle 主逻辑
        ├── sync_turn(...)                      # 回合缓冲 + 提炼策略统一
        ├── remember / recall                   # 工具实现
        └── diagnostics → memory/diagnostics.py # 已有

删除或瘦身为 re-export：memory_plugin.py（兼容测试 import 一版）
```

**硬约束**：

- 不改动 `butler/memory/*` 磁盘格式与 M1–M4 语义。  
- 不改变 `prefetch_turn_memory` 对外注入格式（`<memory-context>` 围栏）。  
- `post_session` 只保留 **一个** 触发策略（建议：缓冲阈值 + `/new` 显式触发，二者共用同一 `ButlerMemory` 引用）。  
- 微信记忆命令（`/记忆待审` 等）仍走 `gateway/memory_commands.py`，门面后移实现即可。

### 1.4 分阶段实施（降低大爆炸）

| 阶段 | 内容 | 行为变更 | 验收 |
|------|------|----------|------|
| **M1** | **实例统一**：`memory_provider._butler_global = orchestrator.butler_memory`（同 tenant）；`_project_memory` 与 `orchestrator._project_memory` 同一引用；切换项目时单点 reload | 无用户可见变更 | 现有 memory pytest + `test_orchestrator` provider mock 更新 |
| **M2** | **预取单点**：`ButlerMemoryService.prefetch` 委托 `prefetch_turn_memory(orchestrator, …)` 或迁入门面后删 plugin 内重复 FTS | 无 | `test_semantic_memory_p1`、`test_project_facts_prefetch`、gateway 记忆注入测试 |
| **M3** | **post_session 单策略**：合并 `sync_turn` 缓冲与 `trigger_session_end` 配置（阈值、互斥锁、去重） | 可能改变「第 8 条消息」提炼时机 — 需 release note | 手工：连续 8 轮对话 + `/new` 各测一次；查 `memory_updates` 日志 |
| **M4** | **删除 `memory_plugin` 厚实现**：保留薄 re-export 或并入 `butler/memory/facade.py` | import 路径变更（内部） | full smoke + 灵文 `/记忆待审` 真机抽测 |

每阶段结束：`PYTHONPATH=. pytest -q` + `bash scripts/butler-smoke.sh --tier=full`。

### 1.5 测试与回归清单

- 单元：`tests/test_memory_*`、`test_semantic_memory_p1.py`、`test_orchestrator.py`（provider 初始化）  
- 网关：`tests/gateway/test_gateway_handler.py` 记忆诊断行  
- 工具：remember → recall 同一 orchestrator 会话内可见  
- **新增建议**（M1）：`test_memory_single_instance` — 断言 `id(orch.butler_memory) == id(orch.memory_provider._butler_global)`  
- **新增建议**（M3）：post_session 只触发一次（mock `PostSessionProcessor.process` 调用计数）

### 1.6 为何 P3 未做

牵 `orchestrator`、`session_lifecycle`、`memory_tools`、`post_session`、微信 M1–M4；任一回归表现为「记忆丢失/重复提炼」，不符合 P3「零行为变更」契约。  
**应在运营轨道 A 稳定后、灵文 B 余量并行前**，单独立项（预估 2–4 人日 + 真机 half-day）。

---

## 2. `/health` 与 `/诊断` 三分支重构（中高优先级）

### 2.1 现状

实现集中在 `butler/gateway/message_handler.py` 的 `_format_health_summary`（约 175 行），三分支：

| 分支 | 条件 | 输出差异 |
|------|------|----------|
| A | 无 `health` 且无工具审计 | 静态诊断 + 记忆层 + 项目元数据 + runtime + model + ops |
| B | 有 `health` 快照 | 上述 + 压缩/Schema/Skill/记忆同步/post_session 模型行 |
| C | 仅有工具审计、无 health | 部分重复 A 的尾部块 |

**重复块**（三处拷贝）：`format_memory_diagnostic_lines`、`format_runtime_diagnostic_lines`、`format_model_diagnostic_lines`、`format_ops_diagnostic_lines`、项目元数据组装。

调用面：

- 微信/网关：`/health`、`/诊断`（sessionless，见 P3b）  
- CLI：`main.py` 构造 `ButlerMessageHandler` 并填 `_health_by_session["cli"]`  
- 文案：`outbound_bridge.py`、`runner.py`、`user_errors.py` 引导用户发 `/health`  
- Lead 系统提示：只读检查优先 `run_runtime_job`，但运维仍依赖 `/诊断`

### 2.2 风险：静默回归

已有 **15+** 测试直接断言 `_format_health_summary` 子串（`tests/gateway/test_gateway_handler.py`、`test_cli_acceptance.py`、`test_semantic_memory_p1.py` 等），包括：

- 会话隔离（不能读其他 session 的 health）  
- 工具审计按 session 分桶  
- 错误信息 redaction  
- 无轮次时仍展示记忆层  

重构若只「抽函数」但改变 **行序、标签文案、默认值**，真机运营会以为「记忆坏了」而实际是展示层变化。

### 2.3 目标结构（建议）

新建 `butler/ops/health_report.py`（或 `gateway/health_format.py`）：

```python
@dataclass
class HealthReportInput:
    session_key: str
    health: dict | None
    tool_summary: dict
    mem_stats: dict
    orchestrator: ButlerOrchestrator

def build_health_report(inp: HealthReportInput) -> str:
    sections = [
        header_section(inp),
        turn_section(inp),      # 有 health 才展开
        memory_section(inp),    # 统一调用 memory.diagnostics
        project_section(inp),
        runtime_section(inp),
        model_section(inp),
        ops_section(inp),
        tools_section(inp),
    ]
    return "\n".join(line for sec in sections for line in sec if sec)
```

`message_handler._format_health_summary` 瘦身为组装 `HealthReportInput` + 调用 `build_health_report`。

### 2.4 实施要点

| 要点 | 说明 |
|------|------|
| **黄金快照** | 重构前对 3–5 个 fixture（无轮次 / 有 health / 仅工具 / lead / cli）保存完整输出文本；重构后 `assert report == golden` |
| **CLI 与网关同库** | 避免 `main.py` 与 handler 再分叉 |
| **不改字段语义** | `memory_sync.skipped`、`provider_synced` 等键名保持不变 |
| **分两步** | ① 抽取 section 函数，行为不变；② 再考虑合并 A/C 分支（可选） |

### 2.5 验收

- 全部现有 health 相关 pytest 无修改通过（或仅更新 golden 文件一次）  
- `bash scripts/butler-smoke.sh --tier=full`  
- 真机：长对话中发 `/诊断`，对比重构前后截图（运营 sign-off）

### 2.6 为何 P3 未做

属 **可读性/可维护性** 债，非功能缺陷；P3 承诺网关零行为变更。  
建议在 **记忆 M1 完成后** 做，避免同时改「记忆统计行」与「内存对象」两处。

---

## 3. 微信 `/steer`（中优先级，产品先行）

### 3.1 现状

| 端 | 支持 | 实现 |
|----|------|------|
| CLI | ✅ `/steer <文本>` | `main.py` → `butler.core.steer.steer()` |
| 微信网关 | ❌ | `message_handler._handle_command` 无分支；`slash_commands` 含 `steer` 仅 CLI 补全 |

机制（`butler/core/steer.py`）：

- 进程级全局 `_pending` + 锁  
- `AgentLoop.run()` 开头 **`clear_steer()`**  
- 工具批结束后 `apply_steer_to_tool_results` 把指引追加到 **最近一批 tool 消息**  
- 不打断当前工具执行（相对 `/interrupt`）

### 3.2 与网关架构的冲突

1. **多会话**：网关 `ThreadPoolExecutor` + per-chat session 锁；steer 全局一份，**会话 A 的 steer 可能被会话 B 的 `clear_steer` 清掉**（另一会话新 turn 开始）。  
2. **长 turn 窗口**：用户可能在工具跑很久时发 steer；需定义是否 sessionless（P3b 已扩展 sessionless 集，但 steer 未列入）。  
3. **与 Lead 角色**：Lead 委派 dev 时，steer 注入 butler loop 还是子 agent？当前仅主 `AgentLoop`。  
4. **产品语义**：微信用户易理解为「打断并重说」；实际为「排队贴到 tool 结果」— 需文案与失败反馈（无 tool 批时 re-queue）。

### 3.3 建议产品决策（实施前必须选定）

| 选项 | 行为 | 推荐度 |
|------|------|--------|
| **S1** | 仅当本 session 有 **RUNNING** 的 loop 时接受；steer 按 `session_key` 分桶存储 | ✅ 推荐 |
| **S2** | 与 CLI 相同全局队列，文档声明「仅单会话调试」 | 仅开发环境 |
| **S3** | 不做微信 steer，改为运行时 job「插入指引」 | 工作量大 |

### 3.4 技术方案草图（S1）

```text
steer.py: _pending: dict[str, str]  # session_key -> text
gateway: /steer / 指引 <text> → sessionless 或 锁内转发
message_handler: 若 loop 非 RUNNING → 回复「当前无进行中的 Agent 轮次」
agent_loop: clear_steer(session_key)  # 按 session
```

验收：

- 两微信会话并行：A steer 不影响 B  
- 工具批中 steer：下批 tool 可见 `User guidance:`  
- 无工具轮次 steer：提示未生效而非静默丢失  
- CLI 行为回归

### 3.5 为何 P3 未做

缺 **产品 ADR**（session 语义、Lead 委派边界）；实现小但 **误用成本高**。  
不阻塞轨道 A/B；可在灵文「长任务委派」运营稳定后作为 D 体验项。

---

## 4. 与后续轨道的衔接

| 未做项 | 建议纳入 | 阻塞关系 |
|--------|----------|----------|
| 记忆 M1–M2 | 轨道 **D.1** 前置技术债 | 阻塞「记忆一致性」类运营工单定性 |
| 记忆 M3–M4 | 独立 mini-release | 与 B3 publish-preflight 无硬依赖 |
| /health 抽取 | **A.4** 发版纪律 + 测试黄金文件 | 不阻塞灵文验收 |
| /steer S1 | **D.3** 或新 ADR | 不阻塞 C 多项目 |

---

## 5. 文档小债（顺带）

- [`post-consolidation-roadmap-2026-05.md`](../active/post-consolidation-roadmap-2026-05.md) §4 pytest 基线应为 **1092**（P3 删除 `TestLingwenLeadHooks` 后）。  
- 本文实施后更新 [`consolidation-p3-implementation-2026-05.md`](../archive/consolidation-p3-implementation-2026-05.md) §「本轮不做」为「已迁移至本文 §1–3」。

---

## 6. 相关文档

- [`architecture/memory-roadmap.md`](../../architecture/memory-roadmap.md)  
- [`consolidation-p3-implementation-2026-05.md`](../archive/consolidation-p3-implementation-2026-05.md)  
- [`post-consolidation-roadmap-2026-05.md`](../active/post-consolidation-roadmap-2026-05.md)  
- [`reviews/project-deep-audit-2026-06.md`](../../reviews/project-deep-audit-2026-06.md)
