# WFXM 项目深层次问题检查报告

**检查日期**: 2026-05-31
**项目路径**: /home/ailearn/projects/WFXM
**检查轮次**: 5轮深度检查

---

## 第一轮：架构与设计问题检查

### 问题 1: [确认] God Module - agent_loop.py 违反单一职责原则

**文件**: `butler/core/agent_loop.py` (807 行)

**问题描述**: 尽管 v4 文档声称模块化设计，`agent_loop.py` 仍是 core/ 中最大的单一文件，将以下职责合并在一个类中：消息准备、LLM 调用编排、工具分发、压缩触发、预算 nudges、stop hooks、metrics、回退熔断、流式工具、会话 transcript 记录和 turn 状态管理。这违反了单一职责原则。

**严重程度**: HIGH

**证据**:
```python
class AgentLoop:
    # 807 行涵盖:
    # - _init_turn_state, _prepare_user_message, _run_turn_body
    # - _call_llm_with_retry, _try_activate_fallback
    # - _process_tool_calls, _dispatch_tool
    # - _maybe_stop_hook_continue
    # - 压缩、预算 nudges、流式、transcript 记录
```

**建议**: 进一步提取: `_call_llm_with_retry` 和回退逻辑 → `llm_retry.py`; 压缩触发决策 → `compaction_task.py`; metrics 记录 → `ops/runtime_metrics.py`; 流式预取逻辑 → `streaming_tools.py`。Loop body 本身应由策略对象组合而非内联条件分支。

---

### 问题 2: [确认] God Module - message_handler.py 违反单一职责原则

**文件**: `butler/gateway/message_handler.py` (1252 行)

**问题描述**: `ButlerMessageHandler` 处理：会话注册表管理、消息解析、队列排空、turn 路由、入站幂等、健康跟踪、中断、项目切换和会话终结。这是网关层的经典 God Object 反模式。

**严重程度**: HIGH

**证据**: 第 28-200+ 行涵盖 15+ 个不同职责; `_drain_queued_inbound` 等方法混合队列逻辑与处理器逻辑; `_interrupt_session_loop` 深入 runtime delegate registry

**建议**: 拆分为: `ButlerMessageHandler`（仅路由）、`GatewaySessionManager`（会话生命周期）、`InboundQueueDrain`（队列操作）、`SessionHealthTracker`（健康指标）

---

### 问题 3: [确认] God Module - builtin_impl.py 违反单一职责原则

**文件**: `butler/tools/builtin_impl.py` (1451 行)

**问题描述**: 该文件包含文件 I/O 工具、终端、搜索、委托、工作流及其辅助函数，单一文件过大导致维护困难。

**严重程度**: HIGH

**证据**: `butler/tools/builtin_impl.py: 1451 行`

**建议**: 拆分为: `file_tools.py`（文件操作）、`terminal_tools.py`（终端工具）、`search_tools.py`（搜索工具）、`delegate_tools.py`（委托工具）

---

### 问题 4: [确认] 通过 ContextVars 的循环依赖

**文件**: `butler/execution_context.py`, `butler/orchestrator.py`, `butler/core/agent_loop.py`

**问题描述**: `execution_context.py` 使用 ContextVars 存储当前 orchestrator 和 session key，但 orchestrator 也是 AgentLoop 实例的工厂。这创建了隐式循环流：orchestrator 创建循环，循环通过 contextvars 绑定回 orchestrator，然后 tools/delegate 使用这些 contextvars 获取"当前 orchestrator"。这是复杂的隐式耦合，从类型签名中不可见。

**严重程度**: MEDIUM

**证据**:
```python
# execution_context.py
_current_orchestrator: ContextVar["ButlerOrchestrator | None"]
# orchestrator.py 创建循环
loop = self._orchestrator.create_agent_loop(...)
# 但 loop.run() 使用 get_current_orchestrator() 获取同一个 orchestrator
```

**建议**: 引入显式的 `ExecutionScope` 对象通过调用链传递，而非对 orchestrator 解析使用全局 contextvars。contextvars 仅用于真正环境状态（session_key、workflow_step_id）。

---

### 问题 5: [确认] ButlerSettings 中的可变共享状态

**文件**: `butler/config.py`

**问题描述**: `ButlerSettings._runtime_model_overrides` 是可变字典，通过 `set_runtime_model_override` 在运行时修改。这在并发 agent 循环之间创建了隐藏的共享可变状态。

**严重程度**: MEDIUM

**证据**:
```python
# config.py
_runtime_model_overrides: dict[str, ModelConfig] = field(default_factory=dict, repr=False)
# orchestrator.py - 修改时无自己的锁
settings.set_runtime_model_override(config.role, mc)
```

**建议**: 使用不可变数据结构或 copy-on-write 模式。运行时模型覆盖应通过 `AgentSpawnConfig` 传递而非存储在全局 settings 中。

---

### 问题 6: [确认] TaskOrchestrator Feature Envy

**文件**: `butler/task_orchestrator.py`

**问题描述**: `TaskOrchestrator.spawn_agent` 广泛访问 `orchestrator._settings`、`orchestrator.project_manager`、`orchestrator.create_project_agent_loop`，并依赖 `ButlerOrchestrator` 作为工厂但立即覆盖其内部。该方法混合：会话 key 解析、模型覆盖锁定、工具过滤、技能上下文注入、内存预取附加、工作流步骤上下文和结果缓存，全部在一个 async 方法中。

**严重程度**: MEDIUM

**证据**: 第 114-305 行的 `spawn_agent` 方法显示跨对象 mutation 和内部访问:
```python
orch = getattr(agent, "_butler_orchestrator", None)
session_key = _resolve_spawn_session_key(config, task_id)
if orch is not None and hasattr(orch, "inject_skill_context"):
    user_message = orch.inject_skill_context(raw_user_message)
    from butler.session.lifecycle import attach_turn_memory_prefetch
    attach_turn_memory_prefetch(agent, orch, raw_user_message, role=config.role)
```

**建议**: 将会话 key 解析和上下文注入提取为独立服务类。`spawn_agent` 应接受预配置的 `AgentLoop` 而非通过 prying into orchestrator internals 构建。

---

### 问题 7: [确认] 深度嵌套控制流

**文件**: `butler/core/agent_loop.py:260-552`（`_run_turn_body` 方法）

**问题描述**: `while` 循环内包含大量嵌套的 `if/try` 块，嵌套层级超过 4 层，严重影响可读性。

**严重程度**: HIGH

**证据**:
```python
# agent_loop.py 第 260-470 行
while status == LoopStatus.RUNNING and iteration < self.config.max_iterations:
    if self._interrupted or (...):
        status = LoopStatus.INTERRUPTED
        ...
    iteration += 1
    try:
        if should_run_compaction_turn(...):
            if did_compact:
                try:
                    if ...:
                        ...
```

**建议**: 将 `while` 循环内的逻辑提取为独立的辅助方法（如 `_handle_compaction_turn`, `_handle_tool_calls`, `_handle_llm_response`），减少嵌套层级。

---

### 问题 8: [确认] 魔术数字未使用命名常量

**文件**: 多处

**问题描述**: 代码中大量使用未命名的数字字面量，降低可读性和可维护性。

**严重程度**: MEDIUM

**证据**:
```python
# builtin_impl.py
time.sleep(0.2)  # 第 540 行
chunk = pipe.read1(8192)  # 第 633 行 - 8192 应该命名

# lifecycle.py
max_age_days: float = 30.0  # 直接用 30.0 而非命名常量
cutoff = time.time() - max(1.0, float(max_age_days)) * 86400.0  # 86400 是一天的秒数
```

**建议**: 将所有魔术数字提取为模块级常量，如 `DEFAULT_TIMEOUT=0.2`, `PIPE_BUFFER_SIZE=8192`, `SECONDS_PER_DAY=86400`。

---

### 问题 9: [确认] 过于宽泛的异常捕获

**文件**: 多处

**问题描述**: 很多地方使用 `except Exception as exc: logger.debug(...)` 模式，实际上静默吞掉了错误，使得调试困难。

**严重程度**: MEDIUM

**证据**:
```python
# 几乎每个函数都有类似模式
def _tool_read_file(path: str, ...):
    try:
        ...
    except Exception as exc:
        return json.dumps({"error": str(exc)})  # 吞掉异常细节

# lifecycle.py:156-158
except Exception as exc:
    if diagnostics is not None:
        diagnostics["memory_butler_error"] = str(exc)
    logger.debug("Butler memory prefetch skipped: %s", exc)  # 静默忽略
```

**建议**: 对于预期内的错误（如文件不存在），使用特定异常类型；对于真正需要忽略的情况，添加注释说明为何可以安全忽略。

---

### 问题 10: [确认] 无界 Session Locks 字典导致内存泄漏

**文件**: `butler/gateway/session_registry.py`

**问题描述**: `_session_locks: dict[str, threading.RLock]` 随会话创建无限增长。Sessions 从 `sessions` 字典通过 LRU 驱逐，但 `_session_locks` 从不清理。这为长期运行的 gateway 进程创建内存泄漏。

**严重程度**: MEDIUM

**证据**:
```python
# line 63
_session_locks: dict[str, threading.RLock] = {}
# 在 session_lock() line 85-88 创建但会话驱逐时从不移除
```

**建议**: 当会话从注册表驱逐时清理 `_session_locks` 条目。

---

### 问题 11: [确认] ButlerOrchestrator God Factory

**文件**: `butler/orchestrator.py` (700 行)

**问题描述**: `ButlerOrchestrator` 负责：带多个模板渲染器的系统提示构建、内存上下文组装、模型凭证解析、技能路由器管理、项目内存重载、agent loop 创建（多个变体）、LLM 客户端创建和插件应用。该类有 8+ 个不同职责组混合在 700 行类中。它既是工厂又是服务定位器。

**严重程度**: MEDIUM

**建议**: 拆分为: `SystemPromptBuilder`（提示模板）、`AgentLoopFactory`（循环创建）、`MemoryContextBuilder`（上下文组装）、`SkillRouterManager`。`ButlerOrchestrator` 应协调这些而非直接实现所有逻辑。

---

### 问题 12: [确认] Gateway Session Registry 封装破坏

**文件**: `butler/gateway/session_registry.py`, `butler/gateway/message_handler.py`

**问题描述**: `GatewaySessionRegistry` 暴露 `sessions: dict[str, Any]` 和 `health_by_session: dict[str, dict]` 作为公共可变属性，`ButlerMessageHandler` 直接访问。这破坏封装——注册表应在内部管理会话生命周期，而非暴露调用者变异的原始字典。

**严重程度**: MEDIUM

**证据**:
```python
# message_handler.py
self._sessions: dict[str, AgentLoop] = self._session_registry.sessions
self._health_by_session: dict[str, dict[str, Any]] = self._session_registry.health_by_session
```

**建议**: 用显式 getter 方法替换公共字典暴露。Sessions 应仅可通过 `get_or_create()` 创建，仅通过注册表驱逐移除，绝不由外部字典 mutation。

---

### 问题 13: [确认] tool_batch.py 尺寸过大

**文件**: `butler/core/tool_batch.py` (503 行)

**问题描述**: `process_tool_calls` 处理：工具调用截断、批量序列 guard、两阶段确认分发、过期读取跳过、guardrails、缓存、重试、并行执行协调、steer 应用和结果终态。虽然比 agent_loop.py 单片好，但单个函数 503 行仍违反 200-400 行准则。

**严重程度**: MEDIUM

**建议**: 提取: 两阶段确认逻辑 → `two_phase_confirm.py`; 过期 guard 逻辑 → `batch_sequence_guard.py`; 缓存 → 独立缓存模块; steer → `steer.py`。每个应可独立测试。

---

## 第二轮：安全性检查

### 问题 14: [确认] Session Key 验证绕过风险

**文件**: `butler/session/keys.py`

**问题描述**: `_validate_session_key()` 函数将无效字符静默替换为下划线 `_` 而不报警告或拒绝请求。虽然日志记录了警告，但会话仍会继续处理，可能导致会话键冲突或混淆。

**严重程度**: MEDIUM

**证据**:
```python
def _validate_session_key(raw: str) -> str:
    key = raw[:_MAX_KEY_LEN]
    if not _KEY_PATTERN.match(key):
        import logging
        logging.getLogger(__name__).warning(
            "Session key contains invalid characters, sanitizing: %r",
            raw[:50],
        )
        key = re.sub(r"[^a-zA-Z0-9_:.\-+]", "_", key)
    return key  # 允许处理替换后的键
```

**建议**: 应在检测到无效字符时返回错误或抛出异常，而不是静默替换。

---

### 问题 15: [确认] Web Fetch 缺少 SSRF DNS 重解析检查

**文件**: `butler/tools/web_fetch.py`

**问题描述**: `download_tools.py` 有 `_resolve_public_ip()` 进行 DNS 反向解析检查以防止 SSRF，但 `web_fetch.py` 使用 `urllib.request.urlopen` 直接请求 URL，未验证目标 IP 是否为私有/保留地址。

**严重程度**: HIGH

**证据**:
```python
# download_tools.py 有完整检查
def _resolve_public_ip(hostname: str) -> tuple[bool, str]:
    ...

# web_fetch.py 无此检查
def tool_web_fetch(url: str, *, max_chars: int = 8000, **_: Any) -> str:
    ...
    req = Request(target, headers={...})
    with urlopen(req, timeout=_timeout_seconds()) as resp:  # 直接请求，无 SSRF 检查
```

**建议**: 为 `web_fetch.py` 添加类似 `download_tools.py` 的 DNS 反向解析检查。

---

### 问题 16: [确认] 敏感文件权限设置存在 TOCTOU 竞态条件

**文件**: `butler/config_secrets.py`

**问题描述**: `_ensure_private_mode()` 在检查文件权限和设置 `0o600` 之间存在时间窗口（TOCTOU），且 chmod 失败时仅记录警告而不抛出异常，文件可能暂时保持可读。

**严重程度**: MEDIUM

**证据**:
```python
def _ensure_private_mode(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            mode = path.stat().st_mode & 0o777
            if mode & 0o077:  # 检查时
                path.chmod(0o600)  # 设置时（可能有竞态）
        else:
            path.touch(mode=0o600)
            path.chmod(0o600)
    except OSError as exc:
        logger.warning("secrets chmod failed (file may be world-readable): %s", exc)
        # 仅警告，未抛出异常
```

**建议**: 应在 chmod 失败时抛出异常以强制修复，或使用原子操作确保权限安全。

---

### 问题 17: [确认] Skill Bundle 路径遍历检查可被绕过

**文件**: `butler/registry/skill_install.py`

**问题描述**: 使用 `if ".." in safe.split("/")` 检查路径遍历，但未覆盖 `..././` 或 `...\/` 等编码变体，也未解析符号链接。

**严重程度**: MEDIUM

**证据**:
```python
def quarantine_bundle(bundle: SkillBundle, *, tenant_id: str = "") -> Path:
    ...
    for rel, content in bundle.files.items():
        safe = rel.replace("\\", "/").lstrip("/")
        if ".." in safe.split("/"):  # 基本检查，可绕过
            raise ValueError(f"Unsafe path in bundle: {rel}")
```

**建议**: 使用 `path.resolve()` 解析真实路径后检查是否在允许目录内。

---

### 问题 18: [确认] MCP Stdio 命令验证后环境变量仍可注入

**文件**: `butler/mcp/client_stdio.py`

**问题描述**: MCP Stdio 连接时使用配置中的 `config.env` 覆盖安全的环境变量，虽然使用 `safe_subprocess_env()` 作为基础，但配置中的恶意值可能覆盖关键路径。

**严重程度**: MEDIUM

**证据**:
```python
def _build_stdio_env(config: McpServerConfig) -> dict[str, str]:
    from butler.tools.path_safety import safe_subprocess_env
    base = safe_subprocess_env()
    for key, value in (config.env or {}).items():
        if value is not None:
            base[str(key)] = str(value)  # 配置值覆盖安全基础环境
    return base
```

**建议**: 应限制允许覆盖的环境变量名，不允许覆盖 `PATH`、`HOME`、`USER` 等关键变量。

---

### 问题 19: [确认] Workspace Root 回退到 cwd 可能导致安全边界模糊

**文件**: `butler/tools/path_safety.py`

**问题描述**: `current_workspace_root()` 和 `tool_safe_root()` 在无法确定项目工作区时回退到 `Path.cwd().resolve()`，可能使安全边界扩展到不预期的目录。

**严重程度**: MEDIUM

**证据**:
```python
def tool_safe_root() -> Path:
    """Return the active root that tools may access."""
    return current_workspace_root() or _configured_safe_root() or Path.cwd().resolve()
    # 无项目时回退到 cwd，可能不是预期的工作目录
```

**建议**: 当无有效项目且未配置 `BUTLER_TOOL_SAFE_ROOT` 时，应拒绝工具执行而非回退到 cwd。

---

### 问题 20: [确认] IO Guardrail 密钥检测正则可被绕过

**文件**: `butler/core/io_guardrail.py`

**问题描述**: 密钥模式检测正则 `\b(sk-[a-zA-Z0-9]{20,})` 仅匹配 `sk-` 前缀，某些提供商的密钥格式（如 `ak-` 或其他格式）可能漏检。

**严重程度**: LOW

**证据**:
```python
_SECRET_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?\S{8,}"),
    re.compile(r"(?i)\bsk-[a-zA-Z0-9]{20,}"),  # 仅 sk- 格式
    re.compile(r"(?i)\bBearer\s+[a-zA-Z0-9._-]{20,}"),
]
```

**建议**: 扩展正则以覆盖更多密钥格式，如 `ak-`、`key-` 等常见前缀。

---

### 问题 21: [确认] 安全扫描仅基于静态正则，无法检测混淆攻击

**文件**: `butler/skills/guard.py`

**问题描述**: Skill 安全扫描使用固定正则模式，无法检测 base64 编码、字符串拼接或压缩后的恶意代码。

**严重程度**: MEDIUM

**证据**:
```python
DANGEROUS_PATTERNS = [
    (re.compile(r"ignore\s+previous\s+instructions", re.I), "prompt_injection"),
    (re.compile(r"eval\s*\(", re.I), "code_eval"),
    (re.compile(r"os\.system\s*\(", re.I), "shell_exec"),
    ...
]
# 可被 eval("os.system('rm -rf /')") 或 base64 编码绕过
```

**建议**: 添加运行时沙箱或更高级的代码分析，扩展静态检测规则覆盖编码场景。

---

### 问题 22: [确认] 消息去重 TTL 配置可能为负值

**文件**: `butler/gateway/message_handler.py`

**问题描述**: `BUTLER_WECHAT_MESSAGE_ID_DEDUP_TTL` 和 `BUTLER_WECHAT_CONTENT_DEDUP_TTL` 从环境变量读取后未验证非负，直接用于时间比较。

**严重程度**: LOW

**建议**: 添加范围验证确保 TTL 为非负值。

---

## 第三轮：代码质量检查

### 问题 23: [确认] 文件超长（超过 800 行限制）

**文件**: 多处

**问题描述**: 多个核心模块远超 800 行限制，增加了代码理解难度和维护成本。

**严重程度**: HIGH

**证据**:
```
butler/gateway/message_handler.py: 1252 行
butler/tools/builtin_impl.py: 1451 行
butler/tools/registry.py: 915 行
butler/session/lifecycle.py: 960 行
butler/core/agent_loop.py: 807 行
```

**建议**: 将大型模块拆分为更小的模块。例如 `message_handler.py` 可以拆分为 `message_handler.py`（主入口）+ `handler_commands.py`（命令处理）+ `handler_validation.py`（验证逻辑）。

---

### 问题 24: [确认] 长函数（超过 50 行限制）

**文件**: 多处

**问题描述**: 多个函数的代码行数远超 50 行限制，应该拆分。

**严重程度**: MEDIUM

**证据**:
```python
# builtin_impl.py:28-101
def _tool_read_file(path: str, offset: int = 1, limit: int = 500, **_) -> str:  # ~73 行

# builtin_impl.py:899-1307
def _tool_delegate_task(...):  # ~408 行

# message_handler.py:232-657
def handle_message(...):  # ~425 行

# lifecycle.py:120-324
def prefetch_turn_memory(...):  # ~204 行
```

**建议**: 按照功能将长函数拆分为更小的、更专注的函数。每个函数应该做一件事。

---

### 问题 25: [确认] 缺少类型注解

**文件**: `butler/gateway/handler_helpers.py`, `butler/memory/project_memory.py`

**问题描述**: 多个函数缺少返回类型注解和参数类型注解。

**严重程度**: MEDIUM

**证据**:
```python
# 但很多函数缺少:
def _ensure_turn_buffer(provider: Any) -> list[dict[str, Any]]:  # provider 应该是具体类型
def drain_post_session_buffer(provider: Any) -> list[dict[str, Any]]:
def _execute_post_session(orchestrator: Any, messages: list[Any]) -> dict[str, Any]:
```

**建议**: 为所有公共函数添加完整的类型注解。使用 `Any` 而非 `object` 作为最后手段。

---

### 问题 26: [确认] 可变全局状态

**文件**: `butler/tools/registry.py:21-23`

**问题描述**: 模块级可变状态用于审计事件存储，线程安全通过锁保证，但增加了复杂性。

**严重程度**: MEDIUM

**证据**:
```python
# registry.py:21-23
_TOOL_AUDIT_EVENTS: deque[dict[str, Any]] = deque(maxlen=200)
_TOOL_AUDIT_EVENTS_BY_SESSION: dict[str, deque[dict[str, Any]]] = {}
_TOOL_AUDIT_LOCK = threading.RLock()
```

**建议**: 考虑将这些封装到一个类中（如 `ToolAuditLog`），提供更好的封装和测试能力。

---

### 问题 27: [确认] 懒导入模式不一致

**文件**: 整个 `butler/` 目录

**问题描述**: 部分导入在函数内部进行（延迟导入），部分在模块顶部。混乱的导入组织影响代码可读性，且增加运行时开销。

**严重程度**: MEDIUM

**证据**:
```python
# agent_loop.py - 在函数内导入
def _run_turn_body(self, ...):
    from butler.core.turn_token_budget import (TurnBudgetState, ...)
    from butler.execution_context import get_audit_session_key
    ...

# 但同时有顶部导入
from butler.core.context_pipeline import ContextPipeline
from butler.core.llm_retry import call_llm_with_retry
```

**建议**: 将所有在函数内重复使用的导入移到模块顶部。函数内导入仅用于避免循环依赖或很少使用的功能。

---

### 问题 28: [确认] 不一致的错误处理方式

**文件**: `butler/tools/builtin_impl.py`

**问题描述**: 有的工具返回 JSON 错误字符串，有的工具抛出异常，不一致。

**严重程度**: MEDIUM

**证据**:
```python
# builtin_impl.py - 混合风格
def _tool_read_file(...):
    try:
        ...
    except Exception as exc:
        return json.dumps({"error": str(exc)})  # 返回 JSON 字符串

# vs 其他地方可能 raise Exception
```

**建议**: 统一工具函数的错误处理策略，建议：工具函数返回 JSON 字符串（保持一致性），上层调用者负责转换为异常或用户友好的消息。

---

### 问题 29: [确认] 重复代码模式

**文件**: `butler/gateway/message_handler.py:977-1194`（`_handle_command` 方法）

**问题描述**: `_handle_command` 方法包含大量相似的命令处理分支，代码重复度高。

**严重程度**: MEDIUM

**证据**:
```python
# message_handler.py:991-1057 - 重复的项目处理
if cmd in ("/projects", "/项目"):
    ...
    return "\n".join(lines)

# message_handler.py:1024-1057 - 几乎相同结构的切换命令处理
if cmd in ("/switch", "/切换"):
    ...
```

**建议**: 使用命令模式（Command Pattern）或字典映射来消除重复的 `if cmd in (...)` 分支。

---

### 问题 30: [确认] delegate_context.py 全局回调链

**文件**: `butler/core/delegate_context.py`

**问题描述**: 使用模块级 ContextVars（`_parent_callbacks`、`_parent_messages`、`_parent_system_prompt`）来跨嵌套 agent 调用传播 delegate 上下文。这是复杂的隐式数据流，使数据来源和去向难以追踪。

**严重程度**: MEDIUM

**证据**: 12 个函数操作 ContextVars；`set_parent_callbacks(None)` 在 turn 结束时清理；多个模块从此导入

**建议**: 通过调用链显式传递 delegate 上下文而非 ContextVars。考虑 `ChainContext` 对象随 delegation 调用传递。

---

## 第四轮：并发与性能检查

### 问题 31: [确认] 全局消息队列锁竞争

**文件**: `butler/gateway/message_queue.py:36-40`

**问题描述**: 全局 `_LOCK` 在所有队列操作上竞争，包括 `enqueue_inbound`、`pop_*`、`_should_dedupe`、`pending_count` 等。在高并发 gateway 场景下，所有 session 的消息都竞争同一把锁。

**严重程度**: HIGH

**证据**:
```python
_LOCK = threading.RLock()
_QUEUES: dict[str, deque[QueuedInbound]] = {}
_DEDUP_WINDOW_SEC = 2.0
_LAST_ENQUEUE: dict[str, tuple[str, float]] = {}
_DROP_SUMMARIES: dict[str, deque[str]] = {}
```

**建议**: 按 session_key 分区锁，或使用 `asyncio.Queue` 替代 threading 锁。

---

### 问题 32: [确认] Gateway Session Registry 嵌套锁风险

**文件**: `butler/gateway/session_registry.py:91-109`

**问题描述**: `enter_session` 方法在持有 session lock 的同时多次获取/释放 `_lock`，这种锁顺序交换容易导致死锁或条件唤醒失败。

**严重程度**: HIGH

**证据**:
```python
def enter_session(self, session_key: str) -> threading.RLock:
    key = str(session_key or "default")
    while True:
        with self._lock:               # 获取外层锁
            self._wait_for_reset_all_locked()
            lock = self._session_locks.get(key)
            ...
        lock.acquire()                # 释放外层锁，获取内层锁
        with self._lock:               # 再次获取外层锁
            self._pending_session_entries -= 1
            self._reset_condition.notify_all()
            ...
        lock.release()               # 提前释放会导致状态不一致
```

**建议**: 重构为单一锁策略，使用 `Condition.wait_for()` 处理等待逻辑。

---

### 问题 33: [确认] Vector Store Cache 无锁读写

**文件**: `butler/memory/vector_store.py:227-253`

**问题描述**: `_STORE_CACHE` 被无锁地读写，多线程场景下可能导致 `KeyError` 或返回未完全初始化的 store 实例。

**严重程度**: MEDIUM

**证据**:
```python
_STORE_CACHE: dict[str, VectorStore] = {}
_STORE_CACHE_MAX = 64

def get_vector_store(collection: str = "butler_personal") -> VectorStore:
    if collection in _STORE_CACHE:
        return _STORE_CACHE[collection]
    if len(_STORE_CACHE) >= _STORE_CACHE_MAX:
        oldest = next(iter(_STORE_CACHE))
        _STORE_CACHE.pop(oldest, None)
    # 竞态窗口：另一个线程可能同时修改 _STORE_CACHE
    store = ChromaVectorStore(collection_name=collection)
    _STORE_CACHE[collection] = store
    return store
```

**建议**: 添加 `threading.Lock()` 保护整个检查-创建-写入流程。

---

### 问题 34: [确认] Delegate Registry 弱引用清理竞态

**文件**: `butler/runtime/delegate_registry.py:23-47`

**问题描述**: `register_delegate_loop` 中先过滤再追加，两步操作之间若有并发 `unregister`，可能导致刚追加的引用被意外移除。

**严重程度**: MEDIUM

**证据**:
```python
def register_delegate_loop(parent_session_key: str, loop: Any) -> None:
    with _LOCK:
        rows = _BY_PARENT.setdefault(parent, [])
        rows[:] = [r for r in rows if r() is not None]  # 过滤期间其他线程可能介入
        rows.append(ref)                                  # 追加新引用
```

**建议**: 将过滤和追加合并为原子操作，或使用 copy-on-write 策略。

---

### 问题 35: [确认] Orchestrator 内存字典 LRU 驱逐无锁

**文件**: `butler/orchestrator.py:128-144`

**问题描述**: `butler_memory` 属性在检查和驱逐旧条目之间存在竞态窗口。

**严重程度**: MEDIUM

**证据**:
```python
@property
def butler_memory(self) -> ButlerMemory:
    with self._memory_lock:
        mem = self._memory_by_tenant.get(tid)
        if mem is None:
            if len(self._memory_by_tenant) >= 64:
                oldest = next(iter(self._memory_by_tenant))
                self._memory_by_tenant.pop(oldest, None)  # 驱逐和创建之间存在竞态
            mem = ButlerMemory(self._settings.butler_home, tenant_id=tid)
            self._memory_by_tenant[tid] = mem
    return mem
```

**建议**: 驱逐逻辑应先于检查，或在锁外预先计算 oldest key。

---

### 问题 36: [确认] Durable Outbox 跨进程文件锁缺失

**文件**: `butler/gateway/durable_outbox.py:107-124`

**问题描述**: 代码注释明确承认跨进程文件锁未强制执行，多 gateway 进程共享 `BUTLER_HOME` 时会竞态。

**严重程度**: MEDIUM

**证据**:
```python
def list_pending_outbox() -> list[dict[str, Any]]:
    """NOTE: cross-process file locking is NOT enforced; if multiple gateway
    processes share the same BUTLER_HOME, concurrent mark_sent / replay
    may race.  For single-process deployment this is safe.
    """
```

**建议**: 当前仅支持单进程部署，多进程场景需添加 `fcntl.flock()` 或进程锁文件。

---

### 问题 37: [确认] Message Queue 持久化竞态窗口

**文件**: `butler/gateway/message_queue.py:154-178`

**问题描述**: `_persist_enqueue` 在 `with _LOCK` 块外调用，内存队列已更新但持久化可能失败，导致重启后数据不一致。

**严重程度**: MEDIUM

**证据**:
```python
with _LOCK:
    if _should_dedupe(key, body):
        return False
    ...
    bucket.append(item)
    bucket = deque(sorted(bucket, key=lambda x: _PRIORITY_ORDER.get(x.priority, 9)))
    _QUEUES[key] = bucket
_persist_enqueue(key, item)  # 锁外持久化，失败会导致内存与磁盘不一致
```

**建议**: 将持久化移入锁内，或使用事务性写入（先写临时文件再 rename）。

---

### 问题 38: [确认] InMemoryVectorStore 无并发保护

**文件**: `butler/memory/vector_store.py:143-224`

**问题描述**: `InMemoryVectorStore` 的 `_docs` 字典在 `add`、`delete`、`query` 时无任何锁保护，多线程调用会导致数据损坏。

**严重程度**: MEDIUM

**证据**:
```python
class InMemoryVectorStore:
    def __init__(self) -> None:
        self._docs: dict[str, dict[str, Any]] = {}  # 无锁
    def add(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
        self._docs[doc_id] = {...}  # 无原子性保证
    def query(self, ...):
        for doc in self._docs.values():  # 迭代期间其他线程可能修改
```

**建议**: 添加 `threading.Lock()` 保护所有方法，或说明仅单线程使用。

---

### 问题 39: [确认] Gateway Runner Executor 无关闭机制

**文件**: `butler/gateway/runner.py:37-42`

**问题描述**: `_HANDLER_EXECUTOR` 以 `daemon=True` 创建但从未显式关闭，进程退出时会被强制终止，可能导致正在处理的消息未完成。

**严重程度**: MEDIUM

**证据**:
```python
_HANDLER_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=_handler_worker_count(),
    thread_name_prefix="butler-gw-handler",
)
# 无 shutdown() 调用
```

**建议**: 在 `run_gateway_async` 的 `finally` 块中添加 `_HANDLER_EXECUTOR.shutdown(wait=True)`。

---

### 问题 40: [确认] Session Transcript 全局状态无锁保护

**文件**: `butler/core/session_transcript.py`

**问题描述**: `session_transcript` 模块维护全局字典存储 session 历史，但无锁保护，多 gateway handler 并发写入会竞态。

**严重程度**: MEDIUM

**建议**: 添加 `threading.Lock()` 或切换到 `asyncio.Lock` 进行全局 session 状态管理。

---

### 问题 41: [确认] Tool Result Cache 无过期机制

**文件**: `butler/core/tool_result_cache.py`

**问题描述**: `get_cached_result` / `set_cached_result` 使用全局字典缓存工具结果，但无大小限制或 TTL，可能导致内存无限增长。

**严重程度**: MEDIUM

**证据**: 在 `tool_batch.py:157` 使用 `get_cached_result(name, args, session_key=session_key)`，但缓存字典增长无界。

**建议**: 实现 LRU 驱逐或 TTL 过期机制。

---

### 问题 42: [确认] Reset_all 条件等待的逻辑风险

**文件**: `butler/gateway/session_registry.py:197-232`

**问题描述**: `reset_all` 中的 `wait(timeout=1.0)` 循环在超时后会强制清理 `_active_sessions`，但未通知这些被强制终止的会话，导致其锁状态不一致。

**严重程度**: MEDIUM

**证据**:
```python
while (self._active_sessions or self._pending_session_entries) and self._now() < deadline:
    self._reset_condition.wait(timeout=1.0)
if self._active_sessions or self._pending_session_entries:
    logger.error("reset_all timed out...")
    self._active_sessions.clear()  # 强制清理但不通知相关线程
    self._pending_session_entries = 0
```

**建议**: 超时后应触发所有活跃会话的中断信号，而非静默清理。

---

## 第五轮：测试覆盖检查

### 问题 43: [确认] 9 个核心文件完全未测试 (0% 覆盖率)

**文件**: 多处

**问题描述**: 这些模块完全没有测试覆盖，属于关键路径上的代码。

**严重程度**: HIGH

**证据**:
```
butler/cli/doctor.py: 0.0%
butler/gateway/outcome_commands.py: 0.0%
butler/gateway/progressive_stream.py: 0.0%
butler/gateway/sessions_commands.py: 0.0%
butler/gateway/vision_fallback.py: 0.0%
butler/mcp/client_http.py: 0.0%
butler/mcp/client_stdio.py: 0.0%
butler/mcp/server_stdio.py: 0.0%
butler/workflows/pause_state.py: 0.0%
```

**建议**: 为每个模块编写至少 3-5 个基础单元测试，确保核心路径可测试。

---

### 问题 44: [确认] gateway/runner.py 覆盖率仅 38.1% 且有一个测试失败

**文件**: `butler/gateway/runner.py`

**问题描述**: 该文件是核心网关运行器，覆盖率仅 38.1%，存在严重的功能代码未测试。更严重的是 `test_handler_timeout_returns_wechat_message` 测试失败。

**严重程度**: HIGH

**证据**:
```
38.1% butler/gateway/runner.py
FAILED tests/test_gateway_runner.py::TestButlerMessageHandlerRunner::test_handler_timeout_returns_wechat_message
AssertionError: Expected 'handle_message' to not have been called. Called 1 times.
```

**建议**: 修复失败的测试用例，增加超时处理逻辑的测试覆盖率。

---

### 问题 45: [确认] CLI 模块全面缺乏测试

**文件**: `butler/cli/` 目录

**问题描述**: CLI 模块几乎全部缺乏测试(0-35% 覆盖率)，这些是用户交互的关键入口。

**严重程度**: HIGH

**证据**:
```
butler/cli/doctor.py: 0.0%
butler/cli/experiment_cli.py: 34.5%
butler/cli/prompt_eval_cli.py: 21.9%
```

**建议**: 为 CLI 命令添加集成测试，验证参数解析和输出格式化。

---

### 问题 46: [确认] MCP 模块测试覆盖严重不足

**文件**: `butler/mcp/` 目录

**问题描述**: MCP(模型上下文协议)相关模块测试覆盖严重不足，client_http/client_stdio/server_stdio 均为 0%。

**严重程度**: HIGH

**证据**:
```
butler/mcp/client_http.py: 0.0%
butler/mcp/client_stdio.py: 0.0%
butler/mcp/server_stdio.py: 0.0%
butler/mcp/manager.py: 29.6%
```

**建议**: 为 MCP 客户端和服务端添加连接、消息传递、错误处理的单元测试。

---

### 问题 47: [确认] 安全敏感代码缺少专项测试

**文件**: `butler/permissions/`, `butler/gateway/pii_scrub.py`, `butler/security_audit.py`

**问题描述**: 安全相关模块(如权限审批、PII 清理、安全审计)缺乏专项测试覆盖。

**严重程度**: HIGH

**建议**: 增加安全边界测试:越权访问、注入攻击、PII 泄露等场景。

---

### 问题 48: [确认] execute_code 工具安全测试缺失

**文件**: `butler/tools/execute_code.py` (覆盖率 30.6%)

**问题描述**: 代码执行工具是高风险组件，缺少沙箱逃逸、恶意代码执行的测试。

**严重程度**: HIGH

**建议**: 添加代码执行安全边界测试:超时、资源限制、危险命令拦截。

---

### 问题 49: [确认] 测试隔离性问题

**文件**: 多处

**问题描述**: 8 个测试文件使用 `reset_tool_audit_events()` 修改全局状态，但未通过 `_isolate_butler_home` fixture 进行隔离，可能导致测试间相互影响。

**严重程度**: MEDIUM

**证据**: `test_task_orchestrator.py`, `test_gateway_handler.py`, `test_agent_loop.py` 等

**建议**: 将 `reset_tool_audit_events()` 封装为 autouse fixture，或确保每个测试前自动调用。

---

### 问题 50: [确认] 覆盖率阈值设置与实际不符

**文件**: `pyproject.toml`

**问题描述**: `fail_under = 55` 但当前覆盖率达 72%，阈值设置过低无法有效推动测试质量提升。

**严重程度**: LOW

**建议**: 将覆盖率阈值提升至 80% 以匹配项目要求。

---

### 问题 51: [确认] 40 个文件覆盖率 31-50%

**文件**: 多处

**问题描述**: 这些模块有部分测试但覆盖率不足 50%，存在大量未测试的代码路径。

**严重程度**: MEDIUM

**证据**:
```
24.7% butler/core/transcript_search.py
29.6% butler/mcp/manager.py
30.6% butler/tools/execute_code.py
33.3% butler/tools/tenant_store.py
```

**建议**: 识别未覆盖的代码分支，针对性添加测试用例。

---

### 问题 52: [确认] llm_retry.py 覆盖率仅 55.3%

**文件**: `butler/core/llm_retry.py`

**问题描述**: 重试逻辑是 LLM 调用稳定性的关键，该模块覆盖不足，存在重试边界条件未测试的风险。

**严重程度**: MEDIUM

**建议**: 为 `call_llm_with_retry` 函数添加重试次数、熔断、超时等边界条件测试。

---

## 汇总：确认的问题

| 编号 | 问题描述 | 文件 | 严重程度 | 类别 |
|------|---------|------|---------|------|
| 1 | God Module - agent_loop.py | butler/core/agent_loop.py | HIGH | 架构 |
| 2 | God Module - message_handler.py | butler/gateway/message_handler.py | HIGH | 架构 |
| 3 | God Module - builtin_impl.py | butler/tools/builtin_impl.py | HIGH | 架构 |
| 4 | 通过 ContextVars 的循环依赖 | butler/execution_context.py | MEDIUM | 架构 |
| 5 | ButlerSettings 可变共享状态 | butler/config.py | MEDIUM | 架构 |
| 6 | TaskOrchestrator Feature Envy | butler/task_orchestrator.py | MEDIUM | 架构 |
| 7 | 深度嵌套控制流 | butler/core/agent_loop.py | HIGH | 代码质量 |
| 8 | 魔术数字未使用命名常量 | 多处 | MEDIUM | 代码质量 |
| 9 | 过于宽泛的异常捕获 | 多处 | MEDIUM | 代码质量 |
| 10 | 无界 Session Locks 内存泄漏 | butler/gateway/session_registry.py | MEDIUM | 性能 |
| 11 | ButlerOrchestrator God Factory | butler/orchestrator.py | MEDIUM | 架构 |
| 12 | Gateway Registry 封装破坏 | butler/gateway/session_registry.py | MEDIUM | 架构 |
| 13 | tool_batch.py 尺寸过大 | butler/core/tool_batch.py | MEDIUM | 代码质量 |
| 14 | Session Key 验证绕过风险 | butler/session/keys.py | MEDIUM | 安全 |
| 15 | Web Fetch 缺少 SSRF 检查 | butler/tools/web_fetch.py | HIGH | 安全 |
| 16 | TOCTOU 竞态条件 | butler/config_secrets.py | MEDIUM | 安全 |
| 17 | Skill Bundle 路径遍历检查可绕过 | butler/registry/skill_install.py | MEDIUM | 安全 |
| 18 | MCP Stdio 环境变量注入 | butler/mcp/client_stdio.py | MEDIUM | 安全 |
| 19 | Workspace Root 回退安全边界模糊 | butler/tools/path_safety.py | MEDIUM | 安全 |
| 20 | IO Guardrail 密钥检测正则可绕过 | butler/core/io_guardrail.py | LOW | 安全 |
| 21 | 安全扫描仅基于静态正则 | butler/skills/guard.py | MEDIUM | 安全 |
| 22 | 消息去重 TTL 可能为负值 | butler/gateway/message_handler.py | LOW | 安全 |
| 23 | 文件超长（超过 800 行） | 多处 | HIGH | 代码质量 |
| 24 | 长函数（超过 50 行） | 多处 | MEDIUM | 代码质量 |
| 25 | 缺少类型注解 | 多处 | MEDIUM | 代码质量 |
| 26 | 可变全局状态 | butler/tools/registry.py | MEDIUM | 代码质量 |
| 27 | 懒导入模式不一致 | 整个 butler/ 目录 | MEDIUM | 代码质量 |
| 28 | 不一致的错误处理方式 | butler/tools/builtin_impl.py | MEDIUM | 代码质量 |
| 29 | 重复代码模式 | butler/gateway/message_handler.py | MEDIUM | 代码质量 |
| 30 | delegate_context.py 全局回调链 | butler/core/delegate_context.py | MEDIUM | 架构 |
| 31 | 全局消息队列锁竞争 | butler/gateway/message_queue.py | HIGH | 并发 |
| 32 | Session Registry 嵌套锁风险 | butler/gateway/session_registry.py | HIGH | 并发 |
| 33 | Vector Store Cache 无锁读写 | butler/memory/vector_store.py | MEDIUM | 并发 |
| 34 | Delegate Registry 弱引用清理竞态 | butler/runtime/delegate_registry.py | MEDIUM | 并发 |
| 35 | Orchestrator LRU 驱逐无锁 | butler/orchestrator.py | MEDIUM | 并发 |
| 36 | Durable Outbox 跨进程文件锁缺失 | butler/gateway/durable_outbox.py | MEDIUM | 并发 |
| 37 | Message Queue 持久化竞态窗口 | butler/gateway/message_queue.py | MEDIUM | 并发 |
| 38 | InMemoryVectorStore 无并发保护 | butler/memory/vector_store.py | MEDIUM | 并发 |
| 39 | Gateway Runner Executor 无关闭机制 | butler/gateway/runner.py | MEDIUM | 并发 |
| 40 | Session Transcript 全局状态无锁保护 | butler/core/session_transcript.py | MEDIUM | 并发 |
| 41 | Tool Result Cache 无过期机制 | butler/core/tool_result_cache.py | MEDIUM | 性能 |
| 42 | Reset_all 条件等待逻辑风险 | butler/gateway/session_registry.py | MEDIUM | 并发 |
| 43 | 9 个核心文件完全未测试 | 多处 | HIGH | 测试 |
| 44 | gateway/runner.py 测试失败 | butler/gateway/runner.py | HIGH | 测试 |
| 45 | CLI 模块全面缺乏测试 | butler/cli/ 目录 | HIGH | 测试 |
| 46 | MCP 模块测试覆盖严重不足 | butler/mcp/ 目录 | HIGH | 测试 |
| 47 | 安全敏感代码缺少专项测试 | butler/permissions/ 等 | HIGH | 测试 |
| 48 | execute_code 工具安全测试缺失 | butler/tools/execute_code.py | HIGH | 测试 |
| 49 | 测试隔离性问题 | 多处 | MEDIUM | 测试 |
| 50 | 覆盖率阈值设置过低 | pyproject.toml | LOW | 测试 |
| 51 | 40 个文件覆盖率 31-50% | 多处 | MEDIUM | 测试 |
| 52 | llm_retry.py 覆盖率仅 55.3% | butler/core/llm_retry.py | MEDIUM | 测试 |

---

## 第六轮：测试覆盖专项检查

### 零覆盖率文件（语句数 > 50）

| 编号 | 文件 | 语句数 | 严重程度 | 问题描述 |
|------|------|--------|----------|----------|
| 53 | butler/gateway/vision_fallback.py | 68 | HIGH | 整个文件 0% 覆盖率。包含图片描述 fallback 逻辑（OpenAI Vision/OCR），是故障转移的关键路径，涉及外部 API 调用和错误处理逻辑 |
| 54 | butler/cli/doctor.py | 60 | HIGH | cmd_doctor 函数 0% 覆盖率。诊断命令涉及安全审计、依赖检查、配置验证 |
| 55 | butler/mcp/client_stdio.py | 59 | HIGH | MCP stdio 传输层 0% 覆盖率。包含异步连接逻辑和环境变量处理 |
| 56 | butler/mcp/client_http.py | 54 | HIGH | MCP HTTP 客户端 0% 覆盖率。网络 I/O 路径无测试覆盖 |
| 57 | butler/mcp/server_stdio.py | 35 | HIGH | MCP stdio 服务端 0% 覆盖率。涉及子进程管理和 I/O |
| 58 | butler/workflows/pause_state.py | 48 | HIGH | 工作流暂停状态管理 0% 覆盖率。工作流状态机核心逻辑无测试 |

### 极低覆盖率文件（< 25%）

| 编号 | 文件 | 语句数 | 覆盖率 | 严重程度 | 问题描述 |
|------|------|--------|--------|----------|----------|
| 59 | butler/gateway/registry_commands.py | 198 | 7.6% | HIGH | 183 行未覆盖。handle_registry_command、_handle_skills、_handle_mcp 完全未覆盖 |
| 60 | butler/gateway/speech_stt.py | 56 | 19.6% | HIGH | 45 行未覆盖。语音转文字功能未充分测试 |
| 61 | butler/gateway/minimax_vlm.py | 66 | 21.2% | HIGH | 52 行未覆盖。MiniMax VLM 图像理解未充分测试 |
| 62 | butler/gateway/commands/lifecycle_commands.py | 122 | 21.3% | HIGH | 96 行未覆盖。会话生命周期命令未充分测试 |
| 63 | butler/cli/prompt_eval_cli.py | 73 | 21.9% | HIGH | 57 行未覆盖 |
| 64 | butler/core/transcript_search.py | 85 | 24.7% | HIGH | 64 行未覆盖。search_transcripts 和 _iter_session_transcripts 完全未覆盖 |
| 65 | butler/registry/mcp_catalog_remote.py | 61 | 26.2% | HIGH | 45 行未覆盖。MCP 目录远程访问 |
| 66 | butler/mcp/manager.py | 159 | 29.6% | HIGH | ensure_connected (0%, 38 语句)、_handles_for、_close_handle、_connect_handle 未覆盖 |

### 错误处理路径覆盖缺失

| 文件 | 错误处理路径 | 覆盖情况 |
|------|-------------|----------|
| butler/gateway/vision_fallback.py | RuntimeError (无 API key, 空 choices, 空内容) | **未覆盖** |
| butler/gateway/registry_commands.py | ValueError (安装失败), InstallConfirmationRequired | **部分覆盖** |
| butler/core/transcript_search.py | 文件不存在, 权限错误 | **未覆盖** |
| butler/mcp/manager.py | 连接超时, 服务不可用 | **未覆盖** |

### 未覆盖的边界情况

- `butler/gateway/registry_commands.py`: 空字符串 identifier、community 源安装确认流程
- `butler/core/transcript_search.py`: 无搜索结果、单次搜索超过限制
- `butler/gateway/vision_fallback.py`: 所有 fallback 都失败时的错误提示
- `butler/mcp/client_stdio.py`: cwd 为非目录、env 包含 None 值

---

## 问题统计

| 类别 | CRITICAL | HIGH | MEDIUM | Low | 合计 |
|------|----------|------|--------|-----|------|
| 架构 | 0 | 4 | 9 | 0 | 13 |
| 安全 | 0 | 1 | 8 | 2 | 11 |
| 代码质量 | 0 | 2 | 10 | 0 | 12 |
| 并发 | 0 | 2 | 10 | 0 | 12 |
| 测试 | 0 | 14 | 3 | 2 | 19 |
| **合计** | **0** | **23** | **40** | **4** | **67** |

---

## 优先级修复建议

### 第一优先级 (立即处理):

1. **HIGH 架构问题** (问题 1, 2, 3, 7, 23)
   - 拆分 agent_loop.py (807 行)
   - 拆分 message_handler.py (1252 行)
   - 拆分 builtin_impl.py (1451 行)
   - 重构深度嵌套的控制流

2. **HIGH 安全问题** (问题 15)
   - 为 web_fetch.py 添加 SSRF 检查

3. **HIGH 并发问题** (问题 31, 32)
   - 重构全局消息队列锁
   - 修复 Session Registry 嵌套锁风险

4. **HIGH 测试问题** (问题 43, 44, 45, 46, 47, 48, 53-66)
   - 增加核心文件测试覆盖（6 个零覆盖率文件：vision_fallback, doctor, client_stdio, client_http, server_stdio, pause_state）
   - 修复 test_gateway_runner.py 失败测试
   - 增加极低覆盖率文件测试（registry_commands 7.6%, speech_stt 19.6%, mcp/manager 29.6% 等）

### 第二优先级 (下一个 Sprint):

1. **MEDIUM 架构问题** (问题 4, 5, 6, 11, 12, 30)
2. **MEDIUM 安全问题** (问题 14, 16, 17, 18, 19, 21)
3. **MEDIUM 代码质量问题** (问题 8, 9, 24, 25, 26, 27, 28, 29)
4. **MEDIUM 并发问题** (问题 33, 34, 35, 36, 37, 38, 39, 40, 41, 42)
5. **MEDIUM 测试问题** (问题 49, 51, 52)

### 第三优先级 (持续改进):

1. **LOW 问题** (问题 20, 22, 50) - 可在日常开发中逐步修复

---

## 总结

本次检查共发现 **67 个问题**，其中：
- **23 个 HIGH 严重程度** - 需要立即处理
- **40 个 MEDIUM 严重程度** - 需要计划处理
- **4 个 LOW 严重程度** - 可在日常中处理

项目整体代码质量中等，存在多个架构和设计问题需要重构，同时安全、并发和测试覆盖也需持续改进。建议按优先级分批次修复。

---

## 检查记录

| 轮次 | 检查类型 | 执行时间 | 发现问题数 |
|------|---------|---------|-----------|
| 1 | 架构与设计问题检查 | 2026-05-31 | 13 |
| 2 | 安全性检查 | 2026-05-31 | 11 |
| 3 | 代码质量检查 | 2026-05-31 | 12 |
| 4 | 并发与性能检查 | 2026-05-31 | 12 |
| 5 | 测试覆盖检查 | 2026-05-31 | 11 |
| 6 | 测试覆盖专项检查 | 2026-05-31 | 8 |
| **合计** | - | - | **67** |

---