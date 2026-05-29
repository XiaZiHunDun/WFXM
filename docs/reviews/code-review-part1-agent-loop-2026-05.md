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
---

## 后续审查计划

- [x] Part 1：Agent Loop
- [x] Part 2：Transport Layer
- [x] Part 3：Tools 系统 ← 新增
- [ ] Part 4：Memory 系统
- [ ] Part 5：Gateway / Session
- [ ] Part 6：CLI / Orchestrator

---

# 代码审查发现（Part 4：Memory 系统）

> 日期：2026-05-28
> 审查范围：`butler/memory/` 目录（facade.py, butler_memory.py, embedding.py, vector_store.py, semantic_index.py 等）

---

## Part 4 发现汇总

| # | 问题 | 严重度 | 类型 | 状态 |
|---|------|--------|------|------|
| 1 | Embedder 每次 embed() 调用创建新 HTTP Client | 🟡 MEDIUM | 性能/资源 | 需改进 |
| 2 | `get_embedder()` 无缓存，每次调用返回新实例 | 🟡 MEDIUM | 性能 | 需改进 |
| 3 | `_JIEBA` 全局状态在模块级别可变 | 🟢 LOW | 可维护性 | 风险低 |
| 4 | `_store_root()` 重复调用 `get_butler_home()` | 🟢 LOW | 性能 | 风险低 |
| 5 | `ChromaVectorStore` 初始化时 probe 调用 embed() | 🟢 LOW | 性能 | 风险低 |
| 6 | `facade.py:159-165` is_available 异常时默认返回 True | 🟢 LOW | 健壮性 | 设计选择 |
| 7 | `get_embedder()` fallback chain 日志分散 | 🟢 LOW | 可观测性 | 风险低 |

**结论：2 个问题需实际改进，其余风险可控或为设计选择。**

---

## 问题 1：Embedder 每次 embed() 调用创建新 HTTP Client

### 位置

- `embedding.py:117-124`（`OpenAIEmbedder.embed`）
- `embedding.py:151-158`（`MinimaxEmbedder.embed`）

### 问题描述

```python
# embedding.py:117-124
def embed(self, text: str) -> list[float]:
    from openai import OpenAI

    client = OpenAI(api_key=self._api_key, base_url=self._base_url)  # 每次调用创建新 client
    resp = client.embeddings.create(model=self._model, input=(text or "").strip())
    vec = list(resp.data[0].embedding)
    self._dim = len(vec)
    return _l2_normalize(vec)
```

每次调用 `embed()` 都创建新的 `OpenAI()` client 实例和新的 HTTP 连接。API 调用密集时：
- 连接建立开销大
- 可能触发连接池耗尽
- 无复用连接带来的性能收益

### 影响

- 向量查询/写入延迟增加
- 连接资源浪费
- 高频调用时可能出现连接问题

### 建议

在 `__init__` 中创建 client 并复用：

```python
class OpenAIEmbedder:
    def __init__(self, *, api_key: str, model: str, base_url: str = "https://api.openai.com/v1") -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._dim = 0
        self._model_id = f"openai/{model}"
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, base_url=base_url)  # 复用 client

    def embed(self, text: str) -> list[float]:
        resp = self._client.embeddings.create(model=self._model, input=(text or "").strip())
        vec = list(resp.data[0].embedding)
        self._dim = len(vec)
        return _l2_normalize(vec)
```

### 优先级

🟡 MEDIUM — 影响性能和资源使用，建议改进。

---

## 问题 2：`get_embedder()` 无缓存，每次调用返回新实例

### 位置

- `embedding.py:242-276`

### 问题描述

```python
def get_embedder() -> Embedder:
    provider = embedding_provider_name()
    model = embedding_model_name()
    if provider in ("local", "hash", "hashing", ""):
        return HashingEmbedder(model_id=model or "hashing-v1")  # 每次新建
    if provider == "fastembed":
        fe = _resolve_fastembed(model)
        if fe is not None:
            return fe  # 每次新建
        ...
    api = _resolve_api_embedder(provider, model)
    if api is not None:
        try:
            probe = api.embed("ping")  # 每次新建并 probe
            if probe:
                logger.info("Embedding provider: %s (%s)", provider, api.model_id)
                return api  # 每次新建
        except Exception as exc:
            ...
    return HashingEmbedder(model_id="hashing-v1")  # 每次新建
```

每次调用都：
1. 重新读取环境变量
2. 创建新的 embedder 实例（除了 `_resolve_fastembed` 有 `probe`）
3. 对 API provider 每次都执行 probe

### 影响

- 每次向量操作都触发 `get_embedder()`
- API embedder 每次 probe 浪费一次 API 调用
- 内存中可能存在多个 embedder 实例

### 建议

添加模块级缓存：

```python
_EMBEDDER_CACHE: dict[str, Embedder] = {}

def get_embedder() -> Embedder:
    provider = embedding_provider_name()
    model = embedding_model_name()
    cache_key = f"{provider}:{model}"
    
    if cache_key in _EMBEDDER_CACHE:
        return _EMBEDDER_CACHE[cache_key]
    
    embedder: Embedder
    # ... resolve embedder ...
    
    _EMBEDDER_CACHE[cache_key] = embedder
    return embedder
```

### 优先级

🟡 MEDIUM — 影响性能和资源使用，建议改进。

---

## 问题 3：`_JIEBA` 全局状态在模块级别可变

### 位置

- `embedding.py:18-19`

```python
_JIEBA = None
_JIEBA_TRIED = False
```

### 问题描述

使用模块级可变变量存储 jieba 分词器状态。虽然有 `_JIEBA_TRIED` 标志防止重复初始化，但全局状态在多线程环境下可能有潜在问题。

### 影响

- 多线程同时导入时可能重复初始化
- 但 `jieba.setLogLevel()` 是幂等的，问题有限

### 优先级

🟢 LOW — 风险低，当前实现可接受。

---

## 问题 4：`_store_root()` 重复调用 `get_butler_home()`

### 位置

- `vector_store.py:46-49`

```python
def _store_root() -> Path:
    from butler.config import get_butler_home
    return get_butler_home() / "vector_store"
```

### 影响

每次调用 `_store_root()` 都会调用 `get_butler_home()`。在 `ChromaVectorStore.__init__` 和 `InMemoryVectorStore.__init__` 中都会调用，可能导致重复调用。

### 优先级

🟢 LOW — `get_butler_home()` 本身可能有缓存，实际影响小。

---

## 问题 5：`ChromaVectorStore` 初始化时 probe 调用 embed()

### 位置

- `vector_store.py:71`

```python
self._embedder = _get_embedder()  # 调用 get_embedder()
```

### 影响

`ChromaVectorStore` 初始化时调用 `get_embedder()`，如果返回 API embedder，会触发 probe（见问题 2）。

### 优先级

🟢 LOW — 仅在初始化时发生，影响有限。

---

## 问题 6：`facade.py:159-165` is_available 异常时默认返回 True

### 位置

- `facade.py:159-165`

```python
def is_available(self) -> bool:
    try:
        from butler.config import get_butler_home
        return bool(get_butler_home())
    except Exception:
        return True  # 默认返回 True
```

### 设计选择

当 `get_butler_home()` 失败时返回 `True`（可用），这意味着 memory 系统在无法确认时假设可用。这是防御性设计，保证系统不会因为配置问题完全不可用。

### 优先级

🟢 LOW — 设计选择，有合理原因。

---

## 问题 7：`get_embedder()` fallback chain 日志分散

### 位置

- `embedding.py:247`, `255`, `265-270`, `272-275`

### 问题描述

日志分散在多处：
- `logger.debug` 用于正常返回 hashing
- `logger.warning` 用于 fastembed/api 失败
- 无统一格式

### 影响

难以追踪 fallback 决策过程。

### 优先级

🟢 LOW — 风险低，可接受现状。

---

## Part 4 改进优先级汇总

| 优先级 | 问题 | 建议 | 工作量 |
|--------|------|------|--------|
| 🟡 MEDIUM | Embedder 每次创建新 HTTP Client | 在 `__init__` 中创建并复用 client | 低 |
| 🟡 MEDIUM | `get_embedder()` 无缓存 | 添加模块级缓存，API provider 只 probe 一次 | 中 |
| 🟢 LOW | `_JIEBA` 全局状态 | 可接受现状 | - |
| 🟢 LOW | `_store_root()` 重复调用 | 可接受现状 | - |
| 🟢 LOW | ChromaVectorStore probe | 可接受现状 | - |
| 🟢 LOW | is_available 默认 True | 设计选择 | - |
| 🟢 LOW | fallback chain 日志分散 | 可接受现状 | - |

---

## 后续审查计划

- [x] Part 1：Agent Loop
- [x] Part 2：Transport Layer
- [x] Part 3：Tools 系统
- [x] Part 4：Memory 系统 ← 新增
- [ ] Part 5：Gateway / Session
- [ ] Part 6：CLI / Orchestrator

---

## 后续审查计划

- [x] Part 1：Agent Loop
- [x] Part 2：Transport Layer
- [x] Part 3：Tools 系统
- [x] Part 4：Memory 系统
- [x] Part 5：Gateway / Session ← 新增
- [ ] Part 6：CLI / Orchestrator

---

# 代码审查发现（Part 5：Gateway / Session）

> 日期：2026-05-28
> 审查范围：`butler/gateway/` + `butler/session/` 目录

---

## Part 5 发现汇总

| # | 问题 | 严重度 | 类型 | 状态 |
|---|------|--------|------|------|
| 1 | `_SEEN` 幂等字典无 TTL/过期清理机制 | 🟡 MEDIUM | 内存 | 需改进 |
| 2 | `GatewaySessionRegistry` LRU evict 在持有锁时调用 `_finalize_loop` | 🟡 MEDIUM | 并发 | 需改进 |
| 3 | `durable_outbox` 跨进程文件锁未强制 | 🟡 MEDIUM | 可靠性 | 设计权衡 |
| 4 | `_warmup_gateway_runtime` 失败仅 debug | 🟢 LOW | 可观测性 | 风险低 |
| 5 | `_reset_all` 超时后强制清理无最终化通知 | 🟢 LOW | 可靠性 | 风险低 |
| 6 | `reset_sessions_for_chat` 循环内调用 `reset()` 逐个加锁 | 🟢 LOW | 性能 | 风险低 |
| 7 | `bot_loop_guard` 失败静默 | 🟢 LOW | 安全 | 风险低 |
| 8 | `record_and_should_suppress` 中 `_PAIR_COUNTS` 仅通过时间窗口裁剪 | 🟢 LOW | 内存 | 风险低 |

**结论：3 个问题需实际改进，其余风险可控或为设计选择。**

---

## 问题 1：`_SEEN` 幂等字典无 TTL/过期清理机制

### 位置

- `inbound_idempotency.py:18-19`

```python
_SEEN: dict[str, OrderedDict[str, tuple[str, float]]] = {}
_MAX_IDS_PER_SESSION = 512
```

### 问题描述

`_SEEN` 字典存储 `("inflight"|"done", timestamp)` 元组，仅通过 `_prune_session()` 限制每个 session 的最大条目数（512），但：

1. **无时间过期**：`"done"` 状态的消息永远保留（直到 session 被 reset）
2. **无 TTL**：长时间运行的 session 的 `_SEEN` 字典持续增长
3. **`reset_session()` 仅在显式调用时清理**：调用前会一直占用内存

### 影响

- 每个活跃 session 最多 512 条记录，足够大但非无限
- `done` 状态的消息永久保存可能不需要（处理后即可清理）
- 极端场景：大量不同 external_id 的消息导致 OOM

### 建议

为 `"done"` 状态添加 TTL（如 10 分钟）并在 `complete_inbound()` 后主动清理：

```python
def complete_inbound(session_key: str, external_id: str | None) -> None:
    eid = _normalize_external_id(external_id)
    if not eid:
        return
    sk = str(session_key or "default").strip() or "default"
    with _LOCK:
        bucket = _SEEN.get(sk)
        if bucket is None:
            return
        bucket[eid] = ("done", time.monotonic())
        # 主动清理已完成的旧条目（>10分钟）
        _prune_done_entries(bucket)
        _prune_session(bucket)
```

### 优先级

🟡 MEDIUM — 内存泄漏风险，建议改进。

---

## 问题 2：`GatewaySessionRegistry` LRU evict 在持有锁时调用 `_finalize_loop`

### 位置

- `session_registry.py:256-276`

```python
def enforce_lru(self) -> list[str]:
    loops_to_finalize: list[Any] = []
    with self._lock:
        # ...pop loops...
        loops_to_finalize.append(loop)
    for loop in loops_to_finalize:  # ❌ 锁外但在 session_lock 持有期间
        self._finalize_loop(loop)
```

### 问题描述

`enforce_lru()` 在 `with self._lock` 内部调用 `session_lock()` 获取每个 evicted loop 的锁，然后释放 `_lock`，再逐个 `_finalize_loop()`。但 `_finalize_loop()` 可能触发：

1. `trigger_session_end()` → `run_session_end_hooks()` → 任意 user hook
2. `flush_observer_queue()` → 磁盘 I/O
3. 其他慢操作

在**持有 session_lock 期间**执行 `_finalize_loop`，可能导致其他等待该锁的请求超时。

### 实际情况

`enforce_lru()` 在 `get_or_create()` 末尾调用，而 `get_or_create()` 持有 `self._lock` 并调用 `session_lock()`。evicted loop 的锁在 `_lock` 释放后才会被 `_finalize_loop()` 使用。

关键问题：`enforce_lru()` 在 `with self._lock` 块中获取 evicted loop 的锁并 pop 它们，但 `_finalize_loop()` 在锁外执行。锁泄漏风险存在于 `_finalize_loop()` 执行期间如果它尝试获取其他 session 的锁。

### 影响

- `_finalize_loop()` 可能耗时较长（I/O、hook 执行）
- 虽然不在 `_lock` 保护范围内，但 `session_lock` 持有期间其他请求可能被阻塞
- 建议：将 `_finalize_loop()` 完全移到 `_lock` 释放后的线程池执行

### 优先级

🟡 MEDIUM — 潜在锁持有时间过长，建议将 finalization 移到后台。

---

## 问题 3：`durable_outbox` 跨进程文件锁未强制

### 位置

- `durable_outbox.py:111-113`

```python
NOTE: cross-process file locking is NOT enforced; if multiple gateway
processes share the same BUTLER_HOME, concurrent mark_sent / replay
may race.  For single-process deployment this is safe.
```

### 设计权衡

- 文件锁会降低性能，且某些文件系统不支持
- 当前设计假设单进程部署
- 多进程场景需额外协调

### 建议

如果需要多进程部署：
1. 添加 `fcntl.flock()` 文件锁
2. 或使用 SQLite 的 WAL 模式内置锁
3. 或使用独立的消息队列服务

### 优先级

🟡 MEDIUM — 设计选择，单进程部署无问题。

---

## 问题 4：`_warmup_gateway_runtime` 失败仅 debug

### 位置

- `runner.py:61-62`

```python
except Exception as exc:
    logger.debug("Gateway warmup skipped: %s", exc)
```

### 影响

Gateway 运行时 warmup 失败（jieba/skill index），如果用户依赖首次消息的 skill 功能，可能静默降级。

### 优先级

🟢 LOW — warmup 失败不影响核心功能，仅可能影响首次响应速度。

---

## 问题 5：`_reset_all` 超时后强制清理无最终化通知

### 位置

- `session_registry.py:197-232`

```python
if self._active_sessions or self._pending_session_entries:
    logger.error(
        "reset_all timed out after %.0fs (active=%s pending=%d); forcing clear",
        wait_timeout,
        sorted(self._active_sessions),
        self._pending_session_entries,
    )
    self._active_sessions.clear()
    self._pending_session_entries = 0
```

### 影响

超时后直接清理，不等待活跃 session 完成，也不调用 `_finalize_loop()`。可能导致：
- 未完成的 post_session extraction 被跳过
- session summary 未写入

### 优先级

🟢 LOW — 超时是极端情况，已有日志记录。

---

## 问题 6：`reset_sessions_for_chat` 循环内调用 `reset()` 逐个加锁

### 位置

- `session_registry.py:165-182`

```python
for key in keys:
    self.reset(key)  # 每个 reset() 获取 session_lock
    cleared.append(key)
```

### 影响

如果有多个 session 需要 reset，循环内逐个加锁可能较慢。但 key 数量通常很少（每个 chat 一个 project session）。

### 优先级

🟢 LOW — 实际影响小。

---

## 问题 7：`bot_loop_guard` 失败静默

### 位置

- `bot_loop_guard.py:93-94`

```python
except Exception as exc:
    logger.debug("record and should suppress skipped: %s", exc)
```

### 影响

`record_generic_event()` 失败时静默，不影响 bot loop guard 本身功能。

### 优先级

🟢 LOW — 功能正常，仅 telemetry 失败。

---

## 问题 8：`record_and_should_suppress` 中 `_PAIR_COUNTS` 仅通过时间窗口裁剪

### 位置

- `bot_loop_guard.py:70-76`

```python
while bucket and (now - bucket[0]) > _WINDOW_SEC:
    bucket.popleft()
```

### 影响

每个 `PAIR_COUNTS[key]` deque 的大小受 `_WINDOW_SEC`（120s）和 `pair_threshold()`（默认 6）控制。每个 key 最多保留 6 个时间戳在 120s 窗口内，内存占用极小。

### 优先级

🟢 LOW — 内存占用可控。

---

## Part 5 改进优先级汇总

| 优先级 | 问题 | 建议 | 工作量 |
|--------|------|------|--------|
| 🟡 MEDIUM | `_SEEN` 无 TTL/过期清理 | 为 `done` 状态添加 TTL，主动清理 | 中 |
| 🟡 MEDIUM | LRU evict finalization 在锁持有期间 | 将 finalization 移到后台线程 | 中 |
| 🟡 MEDIUM | durable_outbox 跨进程锁未强制 | 文档说明或添加文件锁 | 中 |
| 🟢 LOW | warmup 失败仅 debug | 可接受现状 | - |
| 🟢 LOW | reset_all 超时后强制清理 | 可接受现状 | - |
| 🟢 LOW | reset_sessions_for_chat 逐个加锁 | 可接受现状 | - |
| 🟢 LOW | bot_loop_guard 失败静默 | 可接受现状 | - |
| 🟢 LOW | _PAIR_COUNTS 内存可控 | 可接受现状 | - |

---

## 后续审查计划

- [x] Part 1：Agent Loop
- [x] Part 2：Transport Layer
- [x] Part 3：Tools 系统
- [x] Part 4：Memory 系统
- [x] Part 5：Gateway / Session
- [ ] Part 6：CLI / Orchestrator

---

## 后续审查计划

- [x] Part 1：Agent Loop
- [x] Part 2：Transport Layer
- [x] Part 3：Tools 系统
- [x] Part 4：Memory 系统
- [x] Part 5：Gateway / Session
- [x] Part 6：CLI / Orchestrator ← 新增

---

# 代码审查发现（Part 6：CLI / Orchestrator）

> 日期：2026-05-28
> 审查范围：`butler/orchestrator.py`, `butler/project/manager.py`, `butler/cli/` 目录

---

## Part 6 发现汇总

| # | 问题 | 严重度 | 类型 | 状态 |
|---|------|--------|------|------|
| 1 | `ProjectManager` 单例非线程安全 | 🟡 MEDIUM | 并发 | 需改进 |
| 2 | `ButlerOrchestrator.butler_memory` 每次访问重新解析 tenant | 🟡 MEDIUM | 性能 | 需改进 |
| 3 | `ProjectManager._projects` 并发修改无保护 | 🟡 MEDIUM | 并发 | 风险低 |
| 4 | `ButlerMemory` per-tenant 字典无清理机制 | 🟡 MEDIUM | 内存 | 改进可选 |
| 5 | `secrets_cli` api_key 参数暴露在命令历史 | 🟡 MEDIUM | 安全 | 设计权衡 |
| 6 | CLI spinner 硬编码清除宽度 60 | 🟢 LOW | 健壮性 | 改进可选 |
| 7 | `doctor.py` 重复 import `BUTLER_RUNTIME_DIRS` | 🟢 LOW | 代码质量 | 微小 |
| 8 | `WaitSpinner._run` 在非 TTY 时仍写 stdout | 🟢 LOW | 健壮性 | 风险低 |
| 9 | `ProjectManager.current_project` 直接赋值无锁 | 🟢 LOW | 并发 | 风险低 |

**结论：4 个问题需实际改进，其余风险可控或为设计选择。**

---

## 问题 1：`ProjectManager` 单例非线程安全

### 位置

- `manager.py:22-30`

```python
_instance: ProjectManager | None = None

def __new__(cls, *_args: Any, **_kwargs: Any) -> ProjectManager:
    if cls._instance is None:
        inst = super().__new__(cls)
        inst._initialized = False  # type: ignore[attr-defined]
        cls._instance = inst
    assert cls._instance is not None
    return cls._instance
```

### 问题描述

多线程同时调用 `get_project_manager()` 时，如果 `cls._instance is None`，可能在 `__new__` 中竞争：
1. Thread A 判断 `is None`，开始创建
2. Thread B 判断 `is None`，也开始创建
3. 两个线程可能都创建实例，只有最后一个被写入 `cls._instance`

虽然通常进程启动后单线程调用，但 Gateway 的 `ThreadPoolExecutor` 会在初始化阶段触发并发访问。

### 影响

- 极端并发场景下可能创建多个实例
- `__init__` 中有 `_initialized` 保护，所以只有一个会被真正初始化
- 已有 `_initialized` 保护，实际风险低

### 建议

添加 `threading.Lock()` 保护单例初始化：

```python
_LOCK = threading.Lock()

def __new__(cls, *_args: Any, **_kwargs: Any) -> ProjectManager:
    if cls._instance is None:
        with _LOCK:
            if cls._instance is None:  # 二次检查
                inst = super().__new__(cls)
                inst._initialized = False
                cls._instance = inst
    return cls._instance
```

### 优先级

🟡 MEDIUM — 建议添加 double-checked locking。

---

## 问题 2：`ButlerOrchestrator.butler_memory` 每次访问重新解析 tenant

### 位置

- `orchestrator.py:126-138`

```python
@property
def butler_memory(self) -> ButlerMemory:
    from butler.tenant import resolve_tenant_for_project

    tid = resolve_tenant_for_project(...)  # 每次调用都重新解析
    mem = self._memory_by_tenant.get(tid)
    if mem is None:
        mem = ButlerMemory(...)
        self._memory_by_tenant[tid] = mem
    return mem
```

### 问题描述

`resolve_tenant_for_project()` 每次都会调用 `get_project_manager().get_current()` 并执行解析逻辑，可能涉及文件系统访问和环境变量读取。

### 影响

- 每次访问 `orchestrator.butler_memory` 都有额外开销
- 如果 `_memory_by_tenant` 中已缓存，直接返回即可，不需要重新解析

### 建议

改为直接检查缓存，只有缓存未命中时才解析 tenant：

```python
@property
def butler_memory(self) -> ButlerMemory:
    from butler.tenant import resolve_tenant_for_project

    # 先尝试从缓存获取（如果已有 tenant_id）
    for tid, mem in self._memory_by_tenant.items():
        if tid:  # 如果缓存存在，直接返回
            return mem
    # 缓存未命中才解析
    tid = resolve_tenant_for_project(...)
    mem = self._memory_by_tenant.get(tid)
    if mem is None:
        mem = ButlerMemory(...)
        self._memory_by_tenant[tid] = mem
    return mem
```

### 优先级

🟡 MEDIUM — 性能问题，建议改进。

---

## 问题 3：`ProjectManager._projects` 并发修改无保护

### 位置

- `manager.py:51-65` (`_scan_projects`)

```python
def _scan_projects(self) -> None:
    self._projects.clear()  # ❌ 并发修改 dict
    for item in self.projects_dir.iterdir():
        ...
        self._projects[proj.name] = proj  # ❌ 并发修改 dict
```

### 问题描述

`_scan_projects()` 直接对 `self._projects` 执行 clear + 多次赋值。如果在 `_scan_projects()` 执行期间，其他方法（如 `get_project()`、`list_projects()`）访问 `self._projects`，可能遇到 RuntimeError: dictionary changed size during iteration。

### Python 版本说明

Python 3.7+ 的 dict 实现是原子性的，单个 `d[key] = value` 操作不会触发 ConcurrentModificationException，但复合操作（如 clear 后重新填充）仍可能导致迭代问题。

### 影响

- 在 `refresh()` 和 `get_project()` 并发时可能触发
- 通常由主线程调用，实际风险低

### 优先级

🟡 MEDIUM — 建议添加锁保护或使用 copy-on-write 模式。

---

## 问题 4：`ButlerMemory` per-tenant 字典无清理机制

### 位置

- `orchestrator.py:101` (`_memory_by_tenant: dict[str, ButlerMemory] = {}`)

### 问题描述

`_memory_by_tenant` 字典存储 `tenant_id -> ButlerMemory` 映射，一旦创建就永久保留，无 TTL 或 LRU 淘汰机制。

如果用户频繁切换项目或 tenant_id 动态生成，字典会持续增长。

### 影响

- 每个 `ButlerMemory` 实例包含 `ExperienceStore` (SQLite connection)、`ProfileStore`、可能的 `SemanticMemoryIndex`
- 长期运行可能导致内存缓慢增长

### 建议

添加 `_memory_by_tenant` 的定期清理或弱引用：
```python
import weakref
_MEMORY_BY_TENANT: weakref.WeakValueDictionary[str, ButlerMemory] = {}
```

### 优先级

🟡 MEDIUM — 改进可选，长期运行可能需要注意。

---

## 问题 5：`secrets_cli` api_key 参数暴露在命令历史

### 位置

- `secrets_cli.py:34`

```python
st.add_argument("api_key", help="API key 明文（仅本地）")
```

### 设计权衡

Bash 命令历史会记录 `butler secrets set minimax sk-xxxx`，明文 API key 可能泄露。

但这是 CLI 工具的标准限制，用户需自行管理命令历史。

### 建议

使用 `getpass.getpass()` 交互式输入，避免明文参数：
```python
import getpass
key = getpass.getpass("API key: ")
```

### 优先级

🟡 MEDIUM — 设计权衡，安全意识提醒有用。

---

## 问题 6：CLI spinner 硬编码清除宽度 60

### 位置

- `spinner.py:51`

```python
sys.stdout.write("\r" + " " * 60 + "\r")  # 硬编码 60
```

### 问题描述

如果终端宽度小于 60，spinner 清除后可能有残留字符。

### 实际情况

`stream.py:90` 已正确使用 `shutil.get_terminal_size()`，但 `spinner.py` 未使用。

### 优先级

🟢 LOW — 影响小。

---

## 问题 7：`doctor.py` 重复 import `BUTLER_RUNTIME_DIRS`

### 位置

- `doctor.py:15` 和 `doctor.py:25`

```python
# Line 15
from butler.config import BUTLER_RUNTIME_DIRS, get_butler_home

# Line 25
from butler.config import BUTLER_RUNTIME_DIRS  # noqa: F811
```

### 影响

冗余 import，但不影响功能。

### 优先级

🟢 LOW — 微小代码质量问题。

---

## 问题 8：`WaitSpinner._run` 在非 TTY 时仍写 stdout

### 位置

- `spinner.py:41-52`

```python
def _run(self) -> None:
    i = 0
    while not self._stop.wait(0.12):
        ...
        sys.stdout.write(f"\r  {frame} {self._label} ...")
```

### 实际情况

`start()` 已检查 `_can_spin()`，所以 `_run()` 只在确认可以 spin 时才会被调用。问题在 `_run()` 内部逻辑本身是正确的。

### 优先级

🟢 LOW — 无实际问题。

---

## 问题 9：`ProjectManager.current_project` 直接赋值无锁

### 位置

- `manager.py:103`, `218`, `247`

```python
self.current_project = matched  # switch_project
self.current_project = self._default_project  # __init__
```

### 影响

如果 `switch_project` 和 `get_current` 并发执行，可能读到中间状态。

### 优先级

🟢 LOW — 通常单线程 CLI 使用，风险低。

---

## Part 6 改进优先级汇总

| 优先级 | 问题 | 建议 | 工作量 |
|--------|------|------|--------|
| 🟡 MEDIUM | ProjectManager 单例非线程安全 | 添加 double-checked locking | 低 |
| 🟡 MEDIUM | butler_memory 重复 tenant 解析 | 改进缓存逻辑 | 低 |
| 🟡 MEDIUM | _projects 并发修改无保护 | 添加锁或 copy-on-write | 中 |
| 🟡 MEDIUM | _memory_by_tenant 无清理机制 | 使用 WeakValueDictionary | 中 |
| 🟡 MEDIUM | secrets_cli api_key 参数暴露 | 改用 getpass 交互输入 | 低 |
| 🟢 LOW | spinner 硬编码 60 | 使用 shutil.get_terminal_size | 低 |
| 🟢 LOW | doctor 重复 import | 合并 import | 低 |
| 🟢 LOW | WaitSpinner 非 TTY 问题 | 无需改进 | - |
| 🟢 LOW | current_project 无锁 | 可接受现状 | - |

---

## 全部 Part 汇总（6 Parts）

| Part | 范围 | MEDIUM 问题数 | LOW 问题数 |
|------|------|---------------|-----------|
| Part 1 | Agent Loop | 1 | 3 |
| Part 2 | Transport Layer | 3 | 5 |
| Part 3 | Tools 系统 | 2 | 8 |
| Part 4 | Memory 系统 | 2 | 5 |
| Part 5 | Gateway / Session | 3 | 5 |
| Part 6 | CLI / Orchestrator | 5 | 4 |
| **合计** | | **16** | **30** |

---

## 全部需要实际改进的 MEDIUM 问题

| # | 问题 | Part | 建议 |
|---|------|------|------|
| 1 | Broad 异常捕获 debug→warning | Part 1 | 升级日志级别 |
| 2 | Tool wire 失败静默降级 | Part 2 | 添加 warning 日志 |
| 3 | Audit persistence 失败 debug | Part 3 | 升级为 warning |
| 4 | Embedder 每次创建新 HTTP Client | Part 4 | 复用 client |
| 5 | `get_embedder()` 无缓存 | Part 4 | 添加缓存 |
| 6 | `_SEEN` 无 TTL/过期清理 | Part 5 | 添加 TTL 和主动清理 |
| 7 | LRU evict finalization 在锁持有期 | Part 5 | 移到后台线程 |
| 8 | durable_outbox 跨进程锁未强制 | Part 5 | 文档说明或添加文件锁 |
| 9 | ProjectManager 单例非线程安全 | Part 6 | 添加 double-checked locking |
| 10 | butler_memory 重复 tenant 解析 | Part 6 | 改进缓存逻辑 |
| 11 | _projects 并发修改无保护 | Part 6 | 添加锁 |
| 12 | _memory_by_tenant 无清理机制 | Part 6 | 使用 WeakValueDictionary |
| 13 | secrets_cli api_key 参数暴露 | Part 6 | 改用 getpass |
