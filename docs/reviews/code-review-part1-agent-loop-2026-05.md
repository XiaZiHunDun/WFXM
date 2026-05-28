# 代码审查发现（Part 1：Agent Loop）

> 日期：2026-05-28
> 审查范围：`butler/core/agent_loop.py` + `butler/core/context_pipeline.py`
> 严重度：🔴 HIGH / 🟡 MEDIUM / 🟢 LOW

---

## 发现汇总

| # | 问题 | 严重度 | 类型 | 状态 |
|---|------|--------|------|------|
| 1 | Broad 异常捕获导致可选功能静默失败 | 🟡 MEDIUM | 可靠性 | 需改进 |
| 2 | `_attached_loop` 循环引用设计不透明 | 🟢 LOW | 可维护性 | 设计瑕疵 |
| 3 | Silent fallback 初始化缺少告警 | 🟢 LOW | 可靠性 | 风险可控 |
| 4 | messages setter 缺乏保护 | 🟢 LOW | 一致性 | 风险有限 |

**结论：无严重故障，有改进空间。**

---

## 问题 1：Broad 异常捕获导致可选功能静默失败

### 位置

- `agent_loop.py`：19 处 `except Exception as exc: logger.debug(...)`
- `context_pipeline.py`、`tool_selector.py` 等模块类似模式

### 问题描述

关键路径上的可选功能使用 `except Exception` 捕获后仅记录 `logger.debug`，当这些功能应该工作但因异常静默失败时，用户无法察觉。

典型案例（agent_loop.py:221-222）：
```python
except Exception as exc:
    logger.debug("Tool selector skipped: %s", exc)
```

工具选择失败时，回退到使用全部工具——这是**安全回退**，但用户不会收到任何警告。

### 影响

| 功能 | 失败表现 | 用户感知 |
|------|----------|----------|
| 工具选择 | 使用全部工具 | 无感知，可能导致 context 过大 |
| 压缩检查点 | 无 checkpoint | 问题定位困难 |
| Budget nudge | 无 token 预算控制 | 可能超支 |
| Session transcript | 无记录 | 审计缺失 |
| Stop hooks | 无 hooks 执行 | 安全/合规问题 |

### 建议

将关键可选功能的日志级别从 `logger.debug` 升级为 `logger.warning`：

```python
# Before
except Exception as exc:
    logger.debug("Tool selector skipped: %s", exc)

# After
except Exception as exc:
    logger.warning("Tool selector failed, using all tools: %s", exc)
```

**影响范围**：所有可选功能（checkpoint、transcript、budget nudge、stop hooks 等）

### 优先级

🟡 MEDIUM — 不影响核心功能，但影响可观测性和问题定位。

---

## 问题 2：`_attached_loop` 循环引用设计不透明

### 位置

- `agent_loop.py:62-63`
- `context_pipeline.py:35`

### 问题描述

```python
# agent_loop.py:62-63
self._context = ContextPipeline(self.config)
self._context._attached_loop = self  # 循环引用！

# context_pipeline.py:35
_attached_loop: Any | None = None
```

`ContextPipeline` 持有 `AgentLoop` 引用（`_attached_loop`），而 `AgentLoop` 持有 `ContextPipeline`。虽然当前使用场景合理（压缩检查点、thinking protocol），但：

1. **接口不透明**：`_attached_loop` 是私有属性，访问时使用 `getattr(pipeline, "_attached_loop", None)`
2. **紧耦合**：`ContextPipeline` 难以独立测试
3. **内存管理**：Python GC 可处理循环引用，但长期可能积累

### 使用场景

- `context_pipeline.py:75-82`：压缩检查点时需要访问 `loop.client` 和 `loop.tools`
- `context_pipeline.py:194-195`：thinking protocol 需要获取 provider/model 信息

### 建议

1. **短期**：将 `_attached_loop` 改为明确的方法或属性，如 `loop_access: AgentLoopAccess`
2. **长期**：考虑依赖注入或策略模式解耦

### 优先级

🟢 LOW — 当前功能正常，仅影响可维护性和测试性。

---

## 问题 3：Silent Fallback 初始化缺少告警

### 位置

- `agent_loop.py:67-73`

### 问题描述

```python
_chain = list(self.config.fallback_entries or [])
try:
    from butler.transport.provider_health import filter_fallback_chain
    _chain = filter_fallback_chain(_chain)
except Exception as exc:
    logger.debug("Fallback chain filter skipped: %s", exc)
```

如果 `filter_fallback_chain` 抛出异常，fallback chain 保持原始值。如果原始值为空，则系统无 fallback 能力，但无任何告警。

### 实际情况

`filter_fallback_chain` 失败时，chain 保持原样继续运行。风险可控，但缺少告警。

### 建议

```python
except Exception as exc:
    logger.warning("Fallback chain filter failed: %s", exc)
```

### 优先级

🟢 LOW — 风险可控，升级日志级别即可。

---

## 问题 4：messages setter 缺乏保护

### 位置

- `agent_loop.py:765-767`

### 问题描述

```python
@messages.setter
def messages(self, value: list[dict]) -> None:
    self._messages = list(value)
```

任何时候都可以重置 `messages`。如果在 loop 执行期间调用，可能导致状态不一致。

### 影响

当前使用场景是单线程同步的，风险有限。但设计上可以更严格。

### 建议

可考虑添加守卫：
```python
@messages.setter
def messages(self, value: list[dict]) -> None:
    if hasattr(self, '_in_run') and self._in_run:
        raise RuntimeError("Cannot reset messages during run")
    self._messages = list(value)
```

### 优先级

🟢 LOW — 当前风险有限，改进可选。

---

## 改进优先级汇总

| 优先级 | 问题 | 建议 | 工作量 |
|--------|------|------|--------|
| 🟡 MEDIUM | Broad 异常捕获 | 升级日志级别 debug → warning | 低 |
| 🟢 LOW | `_attached_loop` | 明确接口，改进可测试性 | 中 |
| 🟢 LOW | Silent fallback | 升级日志级别 | 低 |
| 🟢 LOW | messages setter | 添加运行时检查 | 低 |

---

## 后续审查计划

- [x] Part 1：Agent Loop
- [x] Part 2：Transport Layer ← 新增
- [ ] Part 3：Tools 系统
- [ ] Part 4：Memory 系统
- [ ] Part 5：Gateway / Session
- [ ] Part 6：CLI / Orchestrator

---

# 代码审查发现（Part 2：Transport Layer）

> 日期：2026-05-28
> 审查范围：`butler/transport/` 目录（llm_client.py, providers.py, error_classifier.py 等）

---

## Part 2 发现汇总

| # | 问题 | 严重度 | 类型 | 状态 |
|---|------|--------|------|------|
| 1 | Tool wire 失败静默降级缺少日志 | 🟡 MEDIUM | 可观测性 | 需改进 |
| 2 | Streaming 异常时返回部分数据无明确告知 | 🟡 MEDIUM | 可靠性 | 建议改进 |
| 3 | Reasoning 字段处理逻辑分散 | 🟡 MEDIUM | 可维护性 | 风险可控 |
| 4 | Provider 注册延迟初始化多线程竞争 | 🟢 LOW | 并发 | 风险低 |
| 5 | Circuit breaker 状态全局积累 | 🟢 LOW | 内存 | 风险低 |
| 6 | `_detect_api_mode` 逻辑简陋 | 🟢 LOW | 健壮性 | 风险低 |
| 7 | API mode fallback 逻辑分散 | 🟢 LOW | 可维护性 | 设计瑕疵 |
| 8 | Think scrubber 状态泄露风险 | 🟢 LOW | 并发 | 无实际问题 |

**结论：1 个问题需实际修复（tool wire 日志），其他风险可控或为设计选择。**

---

## 问题 1：Tool wire 失败静默降级缺少日志

### 位置

- `llm_client.py:136-137`
- `llm_client.py:197-198`

### 问题描述

```python
# llm_client.py:136-137 (complete 方法)
try:
    converted_tools = wire_tools_for_provider(...)
except Exception:
    converted_tools = transport.convert_tools(tools)  # 静默降级，无日志

# llm_client.py:197-198 (stream 方法)
try:
    converted_tools = wire_tools_for_provider(...)
except Exception:
    converted_tools = transport.convert_tools(tools)  # 静默降级，无日志
```

当 `wire_tools_for_provider` 失败时，回退到 `transport.convert_tools`。虽然 `tool_wire.py:47-49` 有 `logger.debug`，但外层 `llm_client.py` 捕获了异常却没有记录。

### 影响

- Tool wire 失败时无日志，难以排查问题
- 用户不知道工具转换走了备用路径

### 建议

```python
# llm_client.py:136-137
except Exception as exc:
    logger.warning("Tool wire failed, using transport fallback: %s", exc)
    converted_tools = transport.convert_tools(tools)
```

### 优先级

🟡 MEDIUM — 影响可观测性，建议添加日志。

---

## 问题 2：Streaming 异常时返回部分数据无明确告知

### 位置

- `llm_client.py:362-367`

### 问题描述

```python
except Exception as exc:
    logger.error("Stream error: %s", exc)
    if collected_content:
        pass  # 返回部分内容，但不告知用户
    else:
        raise
```

当 streaming 中途出错且已有内容时，系统返回部分结果。用户不知道响应被截断。

### 实际情况

- 使用 `logger.error` 而非 `debug`，说明有日志记录
- 返回部分结果是保守策略，避免因网络瞬断丢失完整响应

### 建议

- 返回的 `NormalizedResponse` 应包含某种标记表明响应不完整
- 或者在日志中明确说明"返回部分内容"

### 优先级

🟡 MEDIUM — 建议改进，但有合理原因（保守策略）。

---

## 问题 3：Reasoning 字段处理逻辑分散

### 位置

- `chat_completions.py:124`
- `llm_client.py:322`
- `reasoning_replay.py`
- `content_sanitize.py`

### 问题描述

不同 Provider 的 reasoning 字段名称不同：
- OpenAI chunk: `reasoning_content`
- DeepSeek message: `reasoning`
- Anthropic: `thinking` (via content block)

代码通过 `or` fallback 处理，但逻辑分散在多处：
```python
# chat_completions.py:124
reasoning = msg.get("reasoning") or msg.get("reasoning_content")
```

### 影响

- 难以追踪 reasoning 字段的完整处理流程
- 新增 Provider 时容易遗漏

### 建议

考虑在 `NormalizedResponse` 中统一 reasoning 字段处理，或添加注释说明各 Provider 的字段映射。

### 优先级

🟡 MEDIUM — 风险可控，但改进可提升可维护性。

---

## 问题 4：Provider 注册延迟初始化多线程竞争

### 位置

- `providers.py:46-49`
- `transport/__init__.py:36-43`

### 问题描述

```python
def get_provider(name: str) -> Optional[ProviderProfile]:
    if not _REGISTRY:
        _register_builtin()  # 多线程可能重复调用
    ...
```

虽然有幂等保护（后续写入不覆盖已有条目），但不是最佳实践。

### 影响

- 多次调用 `_register_builtin()`
- 多线程环境下可能短暂创建重复条目

### 优先级

🟢 LOW — 有幂等保护，实际风险低。

---

## 问题 5：Circuit breaker 状态全局积累

### 位置

- `provider_health.py:14-15`
- `provider_health.py:139-151`

### 问题描述

```python
_STATE: dict[str, "_CircuitState"] = {}  # 只增不减
```

`_STATE` 字典只增不减。虽然 `is_circuit_open()` 会重置状态，但 key 本身不会删除。长时间运行后可能膨胀。

### 影响

- 内存占用缓慢增长
- `health_snapshot()` 可能返回大量历史记录

### 优先级

🟢 LOW — 每个 key 只有几十字节，增长缓慢。

---

## 问题 6：`_detect_api_mode` 逻辑简陋

### 位置

- `llm_client.py:66-70`

### 问题描述

```python
def _detect_api_mode(self) -> str:
    url = (self._base_url or "").lower().rstrip("/")
    if url.endswith("/anthropic"):
        return "anthropic_messages"
    return "chat_completions"
```

仅基于 URL 推断，无法处理自定义 base_url。

### 影响

- 用户使用非标准路径时可能推断错误
- 但 `_resolve_config()` 会优先使用 profile 中的 api_mode

### 优先级

🟢 LOW — 有其他机制补充。

---

## 问题 7：API mode fallback 逻辑分散

### 位置

- `llm_client.py:106` (降级到 chat_completions)
- `llm_client.py:253` (根据 api_mode 分流)

### 问题描述

API mode 可能在三处被修改或判断：
1. `_resolve_config()` 设置
2. `_get_anthropic_client()` 失败时降级
3. `_raw_call()` 中根据 api_mode 分流

虽然功能正常，但逻辑分散。

### 优先级

🟢 LOW — 功能正常，设计瑕疵。

---

## 问题 8：Think scrubber 状态泄露风险

### 位置

- `llm_client.py:221`

### 问题描述

每次 stream 调用创建新 `StreamingThinkScrubber()` 实例。如果同一 client 被并发使用，可能有状态混淆风险。

### 实际情况

`_stream_call` 是同步方法，单线程使用场景下无问题。

### 优先级

🟢 LOW — 无实际问题。

---

## Part 2 改进优先级汇总

| 优先级 | 问题 | 建议 | 工作量 |
|--------|------|------|--------|
| 🟡 MEDIUM | Tool wire 失败静默降级 | 添加 warning 日志 | 低 |
| 🟡 MEDIUM | Streaming 返回部分数据无告知 | 标记不完整响应 | 中 |
| 🟡 MEDIUM | Reasoning 字段处理分散 | 统一处理逻辑 | 中 |
| 🟢 LOW | Provider 注册多线程 | 可接受现状 | - |
| 🟢 LOW | Circuit breaker 状态积累 | 可接受现状 | - |
| 🟢 LOW | `_detect_api_mode` 简陋 | 可接受现状 | - |
| 🟢 LOW | API mode fallback 分散 | 可接受现状 | - |
| 🟢 LOW | Think scrubber 状态泄露 | 无需改进 | - |

---

## 后续审查计划

- [x] Part 1：Agent Loop
- [x] Part 2：Transport Layer
- [x] Part 3：Tools 系统 ← 新增
- [ ] Part 4：Memory 系统
- [ ] Part 5：Gateway / Session
- [ ] Part 6：CLI / Orchestrator

---

# 代码审查发现（Part 3：Tools 系统）

> 日期：2026-05-28
> 审查范围：`butler/tools/` 目录（registry.py, builtin_impl.py, path_safety.py, tool_guardrails.py 等）

---

## Part 3 发现汇总

| # | 问题 | 严重度 | 类型 | 状态 |
|---|------|--------|------|------|
| 1 | Audit persistence 失败静默 | 🟡 MEDIUM | 可观测性 | 需改进 |
| 2 | 权限检查 fail-open 设计 | 🟡 MEDIUM | 安全 | 设计权衡 |
| 3 | 全局 Registry 无并发保护 | 🟢 LOW | 并发 | 风险低 |
| 4 | `terminal_approval` TTL 硬编码 | 🟢 LOW | 灵活性 | 改进可选 |
| 5 | 敏感目录列表硬编码 | 🟢 LOW | 灵活性 | 改进可选 |
| 6 | Tool guardrail 配置硬编码 | 🟢 LOW | 灵活性 | 改进可选 |
| 7 | Plan mode 检查失败静默 | 🟢 LOW | 安全 | 风险低 |
| 8 | Session context 无清理机制 | 🟢 LOW | 并发 | 风险低 |
| 9 | `_ensure_builtins` 无并发保护 | 🟢 LOW | 并发 | 风险低 |
| 10 | `_PIPE_SAFE_COMMANDS` 硬编码 | 🟢 LOW | 灵活性 | 改进可选 |

**结论：2 个问题需改进，其余为设计选择或风险可控。**

---

## 问题 1：Audit persistence 失败静默

### 位置

- `audit_persist.py:49-50`

### 问题描述

```python
except OSError as exc:
    logger.debug("Tool audit JSONL append skipped: %s", exc)
```

审计持久化是可选功能（`BUTLER_TOOL_AUDIT_JSONL=1` 开启），失败时使用 `logger.debug`，不易追踪。

### 影响

- 当审计日志写入失败时，难以排查问题
- 可能导致审计数据丢失

### 建议

```python
except OSError as exc:
    logger.warning("Tool audit JSONL append failed: %s", exc)
```

### 优先级

🟡 MEDIUM — 影响可观测性，建议改进。

---

## 问题 2：权限检查 fail-open 设计

### 位置

- `registry.py:131-132` (MCP permission)
- `registry.py:209-210` (project permission)
- `registry.py:236-237` (pre tool hooks)
- `permissions/rules.py:457-458`

### 问题描述

权限检查失败时默认允许（fail-open）：
```python
# permissions/rules.py:457-458
workspace = _current_workspace()
if workspace is None:
    return None  # None = 允许
```

在 `dispatch_tool` 中：
```python
except Exception as exc:
    logger.debug("Project permission rules skipped: %s", exc)
# 失败后继续执行工具，无权限验证
```

### 设计权衡

这是**安全/便利的权衡**：
- fail-open：工具总是能执行，但可能失去权限保护
- fail-closed：工具被阻断，但可能影响正常使用

当前设计选择便利性。

### 建议

如果需要更严格的安全策略，考虑：
1. 添加环境变量 `BUTLER_PERMISSIONS_FAIL_OPEN=0` 切换到 fail-closed
2. 或者在日志中明确记录权限检查被跳过

### 优先级

🟡 MEDIUM — 取决于安全需求，当前为设计选择。

---

## 问题 3：全局 Registry 无并发保护

### 位置

- `registry.py:44` (`_REGISTRY: Dict[str, ToolEntry] = {}`)
- `registry.py:656-661` (`_ensure_builtins`)

### 问题描述

`register()` 直接写入 `_REGISTRY[name]`，但 Python dict 单操作是原子的。`_ensure_builtins()` 有 `global _builtins_loaded` 标志但无锁保护。

### 影响

多线程同时调用时可能多次执行 `_register_builtin_tools()`，但实际风险低。

### 优先级

🟢 LOW — 风险低。

---

## 问题 4：`terminal_approval` TTL 硬编码

### 位置

- `terminal_approval.py:14`

```python
_TTL_SEC = 300.0
```

### 建议

可添加环境变量 `BUTLER_TERMINAL_APPROVAL_TTL` 配置。

### 优先级

🟢 LOW — 改进可选。

---

## 问题 5：敏感目录列表硬编码

### 位置

- `path_safety.py:340-378`

```python
sensitive_dirs = [
    home / ".ssh",
    home / ".aws",
    ...
]
```

### 建议

可添加环境变量 `BUTLER_SENSITIVE_DIRS` 扩展。

### 优先级

🟢 LOW — 改进可选。

---

## 问题 6：Tool guardrail 配置硬编码

### 位置

- `tool_guardrails.py:24-48`

```python
IDEMPOTENT_TOOLS = frozenset({...})
MUTATING_TOOLS = frozenset({...})
```

### 建议

可添加环境变量或配置文件扩展。

### 优先级

🟢 LOW — 改进可选。

---

## 问题 7：Plan mode 检查失败静默

### 位置

- `registry.py:107-108`

```python
except Exception as exc:
    logger.debug("MCP plan mode check skipped: %s", exc)
```

### 影响

plan mode 旨在防止危险操作，如果检查失败则跳过，可能失去保护。

### 优先级

🟢 LOW — 风险低（plan mode 检查是额外保护层）。

---

## 问题 8：Session context 无清理机制

### 位置

- `terminal_danger.py:13-16`, `40-45`

```python
_CURRENT_SESSION: contextvars.ContextVar[str] = contextvars.ContextVar(
    "butler_terminal_session",
    default="",
)

def set_terminal_session_context(session_key: str) -> contextvars.Token:
    return _CURRENT_SESSION.set(str(session_key or "").strip())
```

### 实际情况

`contextvars` 会在协程/任务结束时自动清理。手动设置后如果异常未恢复，contextvar 会自然过期。

### 优先级

🟢 LOW — 无实际问题。

---

## 问题 9：`_ensure_builtins` 无并发保护

### 位置

- `registry.py:656-661`

```python
def _ensure_builtins() -> None:
    global _builtins_loaded
    if _builtins_loaded:
        return
    _builtins_loaded = True
    _register_builtin_tools()
```

### 影响

多线程同时调用时可能多次执行，但 `_builtins_loaded = True` 在 `_register_builtin_tools()` 之前，所以实际只执行一次函数体。

### 优先级

🟢 LOW — 风险低。

---

## 问题 10：`_PIPE_SAFE_COMMANDS` 硬编码

### 位置

- `path_safety.py:151-154`

```python
_PIPE_SAFE_COMMANDS = frozenset({
    "grep", "rg", "wc", "head", "tail", "sort", "uniq", "tr", "cut",
    "awk", "sed", "cat", "tee", "xargs", "find", "ls", "echo",
})
```

### 建议

可添加环境变量 `BUTLER_PIPE_SAFE_COMMANDS` 扩展。

### 优先级

🟢 LOW — 改进可选。

---

## Part 3 改进优先级汇总

| 优先级 | 问题 | 建议 | 工作量 |
|--------|------|------|--------|
| 🟡 MEDIUM | Audit persistence 失败静默 | 升级为 warning 日志 | 低 |
| 🟡 MEDIUM | 权限检查 fail-open | 添加环境变量控制 | 中 |
| 🟢 LOW | Registry 无并发保护 | 可接受现状 | - |
| 🟢 LOW | TTL/目录列表/配置硬编码 | 可接受现状或改进 | 低 |