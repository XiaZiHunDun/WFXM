# 功能完整性深度分析报告

> 日期：2026-05-28
> 范围：Butler 系统功能完整性五大核心问题
> 基础：product-critique-2026-05.md 已列问题 + 代码深度分析

---

## 问题一：项目发现与切换体验

### 问题场景

用户在微信端通过 `/切 <项目名>` 精确匹配项目名称。拼写错误或使用项目别名时系统直接返回"未找到项目"，用户无法直观浏览已有项目列表。

产品文档（product-critique-2026-05.md §5）指出：无语境列表命令；切换项目仅支持精确匹配；建议增加 `/项目列表` 命令。

### 根因分析

**代码位置**：`butler/project/manager.py` 第 79-95 行 `resolve_project_name()`

```python
def resolve_project_name(self, name: str) -> str | None:
    """Match a user-provided project name (exact, then unique case-insensitive, then unique substring)."""
    raw = str(name or "").strip()
    if not raw:
        return None
    if raw in self._projects:
        return raw  # 精确匹配优先
    lower = raw.lower()
    ci = [p for p in self._projects if p.lower() == lower]
    if len(ci) == 1:
        return ci[0]  # 大小写不敏感唯一匹配
    if len(ci) > 1:
        return None  # 多于一个则无法判断
    substr = [p for p in self._projects if lower in p.lower()]
    if len(substr) == 1:
        return substr[0]  # 唯一子串匹配
    return None  # 模糊匹配失败
```

**问题 1：多匹配场景静默失败**

当用户输入 `灵` 而存在 `灵文1号` 和 `灵文2号` 两个项目时，`ci` 列表长度 > 1，函数直接返回 `None`，用户收到模糊的"未找到项目"错误，无列表选择提示。

**问题 2：子串匹配逻辑缺陷**

当前实现是 `lower in p.lower()`，但多匹配时同样静默失败，未提供 disambiguation（消歧）界面。

**问题 3：已有帮助文本但无对应路由**

`butler/gateway/help_commands.py` 第 8-9 行已有帮助条目 `/项目 列出所有项目`，但 `handle_project_onboarding_command`（project_commands.py）中仅处理 `新建` 和 `体检` 子命令，未实现列表功能。

### 改进方案

#### 方案 A：增强 `/项目` 路由（低复杂度）

修改 `handle_project_onboarding_command` 增加列表分支，实现 `_project_list_wechat()` 函数返回纯文本项目列表。

#### 方案 B：多匹配时返回消歧列表（中复杂度）

修改 `resolve_project_name()` 返回 `(最佳匹配, 候选项列表)`，微信命令层在匹配失败时检查候选项，输出"你说的是哪个？"并列出选项。

| 方案 | 复杂度 | 改动范围 | 用户价值 |
|------|--------|----------|----------|
| A：增强 `/项目` 路由 | 低 | 1 个文件 | 高（基础体验） |
| B：多匹配消歧 | 中 | 2-3 个文件 | 高（核心体验） |

**推荐优先级**：A + B 合并实现，P1。

---

## 问题二：委派结果摘要质量不稳定

### 问题场景

`/详细` 命令输出的摘要依赖 LLM 压缩，长时间对话后委派任务，早期上下文已被压缩，摘要可能包含"根据之前的讨论"但用户已不记得之前讨论了什么。

### 根因分析

**代码位置**：`butler/core/context_compressor.py` 第 180-209 行 `_summarize_middle()`

```python
def _summarize_middle(middle: list[dict], previous_summary: str = "") -> tuple[str, bool]:
    transcript = _format_for_summary(middle)
    # ...
    try:
        text = auxiliary_complete(
            prompt,
            task="compression",
            system="You compress conversation history into structured handoff notes.",
        )
        return text, False
    except Exception as exc:
        logger.warning("Summary LLM failed — aborting compression to preserve context: %s", exc)
        return "", False  # 失败时返回空摘要，上下文保留
```

**问题 1：摘要中无时间戳和版本标识**

`_format_for_summary()` 函数（第 164-177 行）对每条消息仅截取前 600 字符，格式为 `[ROLE]: content`，没有消息时间戳、没有压缩迭代次数、没有相对于原始对话的位置信息。

**问题 2：失败时压缩继续但无有效摘要**

当辅助模型调用失败时，`return "", False` 导致压缩继续进行但没有生成有效摘要，用户看到的是空洞的压缩块。

**问题 3：委派结果摘要与压缩摘要未区分**

委派任务（`delegate_task`）返回的结果通过 `AgentReport` 的 `summary` 字段暴露，但压缩上下文产生的摘要与委派结果摘要使用同一套机制。

### 改进方案

#### 方案 A：摘要增加结构化元信息（低复杂度）

在摘要 block 头部增加版本信息：
```
[COMPACTED CONTEXT v{N}]
Source: turns {START}-{END} (of ~{TOTAL})
Compression iteration: {N}
---
```

#### 方案 B：压缩摘要增加时间戳参考（低复杂度）

在 `_format_for_summary()` 中从消息元数据提取时间戳：`[ROLE @ HH:MM]: content`

| 方案 | 复杂度 | 改动范围 | 用户价值 |
|------|--------|----------|----------|
| A：结构化元信息 | 低 | 1-2 个文件 | 高（可定位性） |
| B：时间戳参考 | 低 | 1 个文件 | 中（上下文恢复） |

**推荐优先级**：A + B 合并实现，P1。

---

## 问题三：记忆系统断点（`/新对话` 后记忆保留状态不清晰）

### 问题场景

用户执行 `/新对话` 后，系统清空会话上下文，但 `.butler/observations.db` 和 workspace 记忆是否保留、跨会话连续性如何保障，用户无感知。

### 根因分析

**代码位置**：`butler/session/lifecycle.py` 第 763-779 行 `format_new_session_user_message()`

```python
def format_new_session_user_message(...) -> str:
    lines = [
        "已清空本轮对话上下文。",
        "长期记忆（Owner 画像、项目 MEMORY、经验库）仍保留；上轮闲聊回声已移除。",
    ]
    # ...
    return "\n".join(lines)
```

**问题 1：用户感知层已有说明，但信息粒度不足**

虽然回复文本说明了"长期记忆仍保留"，但未说明具体保留了哪些记忆层、哪些被清除、新对话是否继承了上一次会话的压缩上下文版本。

**问题 2：系统有 3 层记忆用户不感知**

- `observations.db`（workspace 级向量/标量记忆）
- `session_transcript.jsonl`（会话级 transcript）
- `reactive_compact`（压缩摘要）

用户不知道 `/新对话` 后这三层的各自状态。

**问题 3：跨会话连续性机制不透明**

`inject_turn_memory()` 将记忆上下文注入每轮对话，但用户看不见这个过程，无法判断记忆检索是否成功。

### 改进方案

#### 方案 A：增强 `/新对话` 返回信息的结构化（P1，低复杂度）

修改 `format_new_session_user_message()` 返回更有结构的响应：

```
已清空本轮对话上下文。

记忆保留状态：
  ✅ 项目 MEMORY.md — 保留（上次提炼: {N} 条）
  ✅ 经验库 — 保留
  ✅ observations.db — 保留（{K} 条）
  🗑️ 会话回声 — 已清除（{removed} 条）
```

**推荐优先级**：P1。

---

## 问题四：Workflow 调试成本高

### 问题场景

用户定义 Workflow YAML 后，在微信端无法预览 DAG 结构。执行失败后不知道哪一步出问题。

### 根因分析

**代码位置**：`butler/workflows/commands.py` 第 11-75 行 `handle_workflow_command()`

`format_workflows_for_wechat()`（loader.py 第 168-186 行）的输出：

```
工作流列表：
1. dev-qa-loop（可执行）
   步骤: implement(dev) → qa(dev)
运行: /工作流 run <名称> [补充说明]
```

**问题 1：输出信息扁平化丢失 DAG 拓扑**

`WorkflowDef.steps` 包含 `depends_on` 拓扑信息，但输出函数简化为 ` → ` 扁平序列，丢失分支、并行和依赖关系。

**问题 2：无 DAG 可视化专用命令**

用户发送 `/workflow preview <名称>` 时，handler 无法识别 `preview` 子命令，fallback 到将其作为 workflow 名直接运行。

**问题 3：执行结果黑箱**

`TaskOrchestrator.execute_graph()` 返回 `TaskGraphResult`，包含 `execution_order` 和 `nodes`，但微信端用户只收到最终合并的文本响应。

### 改进方案

#### 方案 A：增加 `/workflow 预览 <名称>` 子命令（P1，低复杂度）

实现 `_format_workflow_preview()` 函数，将 DAG 结构以树形展示：

```
工作流: dev-qa-loop
DAG 结构:
  [implement] (dev)  ← 起始节点
      ↓
  [qa] (dev)          ← 终止节点
并行层: layer-0: [implement], layer-1: [qa]
```

#### 方案 B：Workflow 执行增加步骤状态报告（中复杂度）

在 runner.py 的返回值中增加结构化的步骤状态摘要：

```
Workflow: dev-qa-loop 执行结果
  ✅ implement (dev) — 成功 (23.4s, 3 iterations)
  ✅ qa (dev) — 成功 (8.1s, 2 iterations)
执行顺序: implement → qa
总耗时: 31.5s
```

#### 方案 C：失败定位增强（中复杂度）

当 `TaskGraphResult.success == False` 时，明确指出失败节点和原因。

| 方案 | 复杂度 | 改动范围 | 用户价值 |
|------|--------|----------|----------|
| A：DAG 预览 | 低 | 1 个文件 | 高（调试入口） |
| B：步骤状态报告 | 中 | 2-3 个文件 | 高（可观测性） |
| C：失败定位 | 中 | 2 个文件 | 高（核心调试） |

**推荐优先级**：A + B + C 合并实现，P1。

---

## 问题五：隐式上下文机制用户理解度低

### 问题场景

`BUTLER_TOOL_IMPLICIT_CONTEXT` 环境变量控制自动注入 `_butler_session_key`、`_butler_project_root`、`_butler_workflow_step` 等隐式参数到工具调用上下文。用户对这些隐式注入的参数无感知，当工具行为异常时无法判断是否由隐式上下文引起。

### 根因分析

**代码位置**：`butler/tools/tool_implicit_context.py` 第 1-76 行

```python
def build_implicit_tool_args() -> dict[str, Any]:
    """Keys prefixed with ``_butler_`` — stripped from LLM schemas, passed to handlers via ``**_``."""
    if not implicit_context_enabled():
        return {}
    out: dict[str, Any] = {}
    # 注入 _butler_session_key, _butler_project_root, _butler_workspace, _butler_workflow_step
    return out

def merge_implicit_tool_args(args: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(args or {})
    for key, val in build_implicit_tool_args().items():
        merged.setdefault(key, val)  # 仅当不存在时才注入
    return merged
```

**问题 1：参数以 `_butler_` 为前缀但用户不可见**

LLM 在生成工具调用时不感知这些隐式参数（从 schema 中 strip 掉了），用户调试时看到的工具 schema 不包含这些参数，无法理解参数来源。

**问题 2：开关机制缺乏用户层面说明**

`BUTLER_TOOL_IMPLICIT_CONTEXT` 默认开启，但用户不知道这个机制的存在。

**问题 3：无诊断命令查看隐式上下文状态**

用户无法通过命令查看当前会话的隐式上下文注入状态。

### 改进方案

#### 方案 A：增加 `/隐式上下文` 诊断命令（P1，低复杂度）

返回当前隐式上下文状态：
```
隐式上下文状态:
  BUTLER_TOOL_IMPLICIT_CONTEXT = 1（已启用）
  _butler_session_key = "wechat:abc123:dft"
  _butler_project_root = "/path/to/workspace"
  _butler_workflow_step = ""
  当前项目: 灵文1号
```

#### 方案 B：在工具执行错误信息中包含关键隐式变量（低复杂度）

在 dispatch 错误处理中附加上下文摘要。

#### 方案 C：文档化（低复杂度）

在用户文档中增加"隐式上下文"章节。

**推荐优先级**：A + B + C 合并实现，P1。

---

## 横向问题：命令路由层的一致性

以上五个问题都涉及一个横向问题：**微信端命令路由与实际功能的不对齐**。

- `help_commands.py` 定义的命令与 `message_handler.py` 实际路由的命令集合存在差异
- 很多命令（如 `/隐式上下文`、`/项目列表`）已在帮助文本中声明但未实现路由
- 不同命令类别分散在不同的 *_commands.py 文件中，缺乏统一的路由注册表

### 建议的横向改进

创建 `butler/gateway/command_registry.py`，集中注册所有命令及对应的 handler：

```python
COMMAND_REGISTRY: list[tuple[str, Callable[..., str | None]]] = [
    ("/帮助", handle_help_command),
    ("/新对话", handle_new_session),
    ("/项目", handle_project_onboarding),
    ("/切换", handle_project_switch),
    # ...
]
```

---

## 优先级汇总

| # | 问题 | 优先级 | 实现复杂度 | 核心文件 |
|---|------|--------|------------|----------|
| 1 | 项目发现与切换 | P1 | 低-中 | `project/manager.py`, `gateway/project_commands.py` |
| 2 | 委派结果摘要 | P1 | 低 | `core/context_compressor.py` |
| 3 | 记忆系统断点 | P1 | 低 | `session/lifecycle.py` |
| 4 | Workflow 调试 | P1 | 低-中 | `workflows/commands.py`, `workflows/runner.py` |
| 5 | 隐式上下文透明 | P1 | 低 | `tools/tool_implicit_context.py` |
| 横 | 命令路由一致性 | P2 | 中 | `gateway/command_registry.py`（新建） |

## 附录：关键代码路径索引

| 问题 | 相关文件 | 关键函数/类 |
|------|----------|--------------|
| 项目切换 | `butler/project/manager.py` | `ProjectManager.resolve_project_name()` |
| 项目列表 | `butler/gateway/project_commands.py` | `handle_project_onboarding_command()` |
| 项目列表 | `butler/gateway/help_commands.py` | `_HELP_GROUPS["项目"]` |
| 压缩摘要 | `butler/core/context_compressor.py` | `_summarize_middle()`, `_format_for_summary()` |
| 委派报告 | `butler/task_orchestrator.py` | `AgentResult`, `AgentReport` |
| 新对话 | `butler/session/lifecycle.py` | `handle_new_session_command()`, `format_new_session_user_message()` |
| 记忆保留 | `butler/session/lifecycle.py` | `clear_session_boundary_memory()` |
| 记忆注入 | `butler/session/lifecycle.py` | `inject_turn_memory()`, `prefetch_turn_memory()` |
| Workflow | `butler/workflows/commands.py` | `handle_workflow_command()` |
| Workflow | `butler/workflows/loader.py` | `format_workflows_for_wechat()` |
| Workflow | `butler/workflows/runner.py` | `run_workflow_for_project()` |
| 隐式上下文 | `butler/tools/tool_implicit_context.py` | `build_implicit_tool_args()`, `merge_implicit_tool_args()` |
| 会话注册 | `butler/gateway/session_registry.py` | `GatewaySessionRegistry` |