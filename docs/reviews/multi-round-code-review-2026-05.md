# Butler v4 多轮代码挑刺报告

> 生成时间：2026-05-28
> 挑刺轮次：第1轮、第2轮、第3轮、第4轮、第5轮、第6轮、第7轮、第8轮
> 项目：WFXM / Butler v4
> 累计发现问题：CRITICAL 24 | HIGH 76 | MEDIUM 181 | LOW 102

---

## 目录

- [CRITICAL 问题清单](#critical-问题清单)
- [HIGH 问题清单](#high-问题清单)
- [MEDIUM 问题清单](#medium-问题清单)
- [LOW 问题清单](#low-问题清单)
- [按模块分类](#按模块分类)
- [修复优先级建议](#修复优先级建议)

---

## CRITICAL 问题清单

### C1. 环境变量注入绕过Terminal命令白名单

**位置**：`butler/tools/path_safety.py:48-59`

**问题描述**：`BUTLER_TERMINAL_ALLOWLIST_EXTRA` 环境变量可被攻击者利用，向白名单添加任意命令（如 `wget,curl,nc`），绕过受限的 argv 执行模型。

**严重程度**：CRITICAL - 安全漏洞

**发现轮次**：第1轮·安全与权限

**修复建议**：环境变量注入的允许名单操作应仅在可信配置源（系统环境变量，非用户可控的 .env）中生效，或迁移到配置文件+签名验证。

---

### C2. MCP community catalog `env_hints` 诱骗敏感凭据

**位置**：`butler/registry/mcp_install.py:46-49`

**问题描述**：community 目录条目通过 `env_hints` 可引用敏感环境变量名（如 `GITHUB_TOKEN`、`AWS_SECRET`），用户被引导提供这些凭据。`trust` 字段对 community 仅生成警告，不阻止安装。

**严重程度**：CRITICAL - 安全漏洞

**发现轮次**：第1轮·安全与权限

**修复建议**：将 `"community_trust"` 加入 `_BLOCK_CODES`，或对 community 条目强制过滤敏感环境变量名。

---

### C3. TaskOrchestrator 职责越界（承担Agent工厂职责）

**位置**：`butler/task_orchestrator.py:111-166`

**问题描述**：`TaskOrchestrator` 直接创建 `AgentLoop` 实例、解析模型配置、过滤工具列表，违反了 v4 架构"新增能力优先落入子模块"的原则，承担了"工作流编排"和"Agent 实例化"两个职责。

**严重程度**：CRITICAL - 架构问题

**发现轮次**：第1轮·架构设计

**修复建议**：引入 `AgentFactory` 子模块，将模型解析、工具解析、AgentLoop 创建收敛到一处。TaskOrchestrator 只负责 DAG 执行调度。

---

### C4. 创建新 ButlerOrchestrator 而非复用上下文

**位置**：`butler/task_orchestrator.py:680-689`

**问题描述**：当 `execution_context` 中没有绑定 orchestrator 时，代码直接 `return ButlerOrchestrator(user_id="owner", channel="orchestrator")` —— 这会创建全新的实例，而非复用外部已初始化的共享实例。导致内存、skill_router、project_memory 等状态丢失。

**严重程度**：CRITICAL - 架构问题

**发现轮次**：第1轮·架构设计

**修复建议**：应在入口处接受并传递 orchestrator 实例，而非每次都创建新的。调用方应确保正确的 orchestrator 被传入。

---

### C5. `_doom_soft_nudged` 永久记忆导致 doom loop 可绕过软提醒

**位置**：`butler/tool_guardrails.py:246-252`

**问题描述**：`_doom_soft_nudged` 是记录已收到软提醒的 `set`，但它永远不会被清除（仅 `reset_for_turn()` 可重置）。如果用户不回应，agent 在下一轮重试相同调用时不会再看到软提醒，因为签名仍在 `_doom_soft_nudged` 中。

**严重程度**：CRITICAL - 逻辑缺陷

**发现轮次**：第2轮·工具系统

**修复建议**：`_doom_soft_nudged` 必须在 `reset_for_turn()` 中与其他 per-turn 状态一起清除。

---

### C6. `mcp_install.py` 验证异常未捕获，bubbles up

**位置**：`butler/registry/mcp_install.py:138`

**问题描述**：`_validate_stdio_command(entry.command)` 在第138行被调用，如果抛出 `ValueError`，不会被捕获，会作为未处理异常向上传播，产生糟糕的错误信息给 agent。

**严重程度**：CRITICAL - 错误处理

**发现轮次**：第2轮·工具系统

**修复建议**：用 try/except 包装第138行，返回干净的错误码而非异常。

---

### C7. `DELEGATE_BLOCKED_TOOLS` 两处定义不同步

**位置**：`butler/delegate/policy.py:7-10` 和 `butler/delegate/subagent_permissions.py:13-19`

**问题描述**：两处都定义了 `DELEGATE_BLOCKED_TOOLS`，内容不一致：
- `policy.py`: `{delegate_task, run_workflow}`
- `subagent_permissions.py`: `{delegate_task, run_workflow, run_runtime_job, session_todos_list, session_todos_write}`

如果两个模块的用户不同（subagent vs orchestrator），blocking 集合不一致。

**严重程度**：CRITICAL - 安全一致性

**发现轮次**：第2轮·Workflow系统

**修复建议**：将 `DELEGATE_BLOCKED_TOOLS` 提取到共享常量，两个模块都引用它。

---

### C8. `until_assertion` 错误被 rescue_steps 掩盖

**位置**：`butler/task_orchestrator.py:533-556`

**问题描述**：`until_assertion_failed` 被写入 `last_result.error`，但 `_run_rescue_steps` 会继续执行并最终返回。如果 rescue steps 全部失败，最终返回的是 "rescue_completed" 而非原始的 `until_assertion`，导致调用方无法区分"真正 QA 失败"还是"断言格式错误"。

**严重程度**：CRITICAL - 逻辑缺陷

**发现轮次**：第2轮·Workflow系统

**修复建议**：rescue_steps 执行后应保留原始 `until_assertion` 错误信息，或在最终结果中明确标记"QA 失败但 rescue 也失败"。

---

### C9. `asyncio.run()` 从已运行的 event loop 调用

**位置**：`butler/session/lifecycle.py:604`

**问题描述**：`asyncio.run()` 会创建新 event loop 并阻塞。如果从已有 event loop 的线程调用（如 WebSocket gateway turn 中），会抛出 `RuntimeError: asyncio.run() cannot be called from a running event loop`，导致 session end 处理静默失败。

**严重程度**：CRITICAL - 运行环境错误

**发现轮次**：第3轮·Session与生命周期

**修复建议**：使用 `asyncio.create_task()` 和正确的 await 模式替代 `asyncio.run()`。

---

### C10. `_scan_projects` 符号链接可绕过安全边界

**位置**：`butler/project/manager.py:56-67`

**问题描述**：`_scan_projects` 中 `item.is_dir()` 后直接取 `config = item / "project.yaml"`。若 `projects_dir` 下存在指向外部的符号链接，则会绕过安全边界扫描到外部目录的 `project.yaml`。

**严重程度**：CRITICAL - 安全漏洞

**发现轮次**：第4轮·项目系统

**修复建议**：在扫描时对每个子目录检查绝对路径是否仍在 `projects_dir` 内，拒绝符号链接指向外部的情况。

---

### C11. `effective_workspace` 可逃离项目根目录

**位置**：`butler/project/worktree.py:45-47`

**问题描述**：相对 `worktree` 路径拼接到 `base` 后无边界检查。`target = (base / target).resolve()` 后无检查 `target` 是否仍在 `base` 内。攻击者可通过 `worktree: ../../../etc` 或 `worktree: /tmp/evil` 逃逸到任意文件系统位置。

**严重程度**：CRITICAL - 安全漏洞

**发现轮次**：第4轮·项目系统

**修复建议**：添加 `is_subpath(target, workspace)` 类似检查，防止逃逸。

---

### C12. `auto_extract` 的 `rglob` 无限制递归扫描

**位置**：`butler/project/project_memory.py:540-546`

**问题描述**：`root.rglob("*.py")` 和 `rglob("*.ts")` 对大仓库无限制。如果项目目录包含大量文件（如 node_modules 未被排除），会导致内存暴涨、性能灾难。

**严重程度**：CRITICAL - 资源耗尽

**发现轮次**：第4轮·项目系统

**修复建议**：对 `rglob` 结果限制数量或超时，或将目录排除改为基于 `.gitignore` 模式。

---

### C13. `run_interruptible` 超时后工作线程无法回收

**位置**：`butler/transport/interruptible_client.py:46-48`

**问题描述**：当 `StaleApiCallError` 被抛出时，工作线程是 daemon 线程不会被 join。函数返回后 thread 仍是 daemon 状态，orphaned。如果 LLM API 响应慢（>90s stale timeout），工作线程继续运行直到 API 返回，然后设置 `result["value"]` 但无人读取。

**严重程度**：CRITICAL - 资源泄漏

**发现轮次**：第4轮·循环依赖与边界case

**修复建议**：在抛出 `StaleApiCallError` 前调用 `thread.join(0.1)` 确保线程完全结束，或使用 `ThreadPoolExecutor` 而非手动管理线程。

---

## HIGH 问题清单

### H1. `ContextPipeline._attached_loop` 双向耦合

**位置**：`butler/core/context_pipeline.py:35` + `butler/core/agent_loop.py:63`

**问题描述**：`ContextPipeline` 持有 `_attached_loop` 引用，让 pipeline 可以访问 loop 的 client 信息，违反单向依赖原则。

**严重程度**：HIGH - 架构问题

**发现轮次**：第1轮·架构设计

**修复建议**：将 provider/model 信息作为参数传入 `prepare_messages_for_api`，而非通过 `._attached_loop` 隐式获取。

---

### H2. ButlerOrchestrator 违反单一职责原则（God Object）

**位置**：`butler/orchestrator.py:94-113`

**问题描述**：`ButlerOrchestrator` 一个类承担了记忆管理、Skill路由、模型配置、AgentLoop创建、系统提示构建、内存服务初始化等职责，约600行。

**严重程度**：HIGH - 架构问题

**发现轮次**：第1轮·架构设计

**修复建议**：按 v4 文档的模块化原则拆分，引入 `MemoryManager`、`SkillManager`、`PromptBuilder`、`AgentFactory` 等独立组件。

---

### H3. `permissions.yaml` 由 workspace 所有者控制

**位置**：`butler/permissions/rules.py:42-62`

**问题描述**：`permissions.yaml` 从 workspace 目录加载。如果 workspace 是共享的，所有者可以定义 permissive 规则（如 `external_directory` 允许 `*`），影响所有工具包括 MCP 工具。

**严重程度**：HIGH - 安全边界

**发现轮次**：第1轮·安全与权限

**修复建议**：workspace 级权限应受限于全局策略，不应允许完全绕过全局安全边界。

---

### H4. Subagent 工具过滤依赖 workspace 权限

**位置**：`butler/delegate/subagent_permissions.py:22-31`

**问题描述**：`filter_tools_for_subagent` 从 workspace 加载权限配置 `allow_tools`/`deny_tools`。由于 subagent 在父 session 权限下运行，workspace 的宽松权限可能导致通过 subagent 权限提升。

**严重程度**：HIGH - 权限提升风险

**发现轮次**：第1轮·安全与权限

**修复建议**：subagent 工具过滤应使用全局策略而非 workspace 可控配置。

---

### H5. Project-scope MCP 安装写入 workspace 无审批

**位置**：`butler/tools/mcp_self_service.py:63-74`

**问题描述**：当 `scope=project` 时，工具将 MCP 配置写入 `project/.butler/mcp.yaml`。与 catalog 级安装不同，project 级安装似乎不需要 `human_gate` 审批。

**严重程度**：HIGH - 安全流程

**发现轮次**：第1轮·安全与权限

**修复建议**：project-scope MCP 安装应要求与 catalog 级相同的 `human_gate` 审批流程。

---

### H6. `message_handler.py` 275行命令分发5层嵌套

**位置**：`butler/gateway/message_handler.py:664-693`

**问题描述**：命令分发链迭代10个 normalizer，然后有40+个 `if cmd in (...)` 块处理斜杠命令，每个处理器本身可能包含复杂的逻辑。嵌套至少5层。

**严重程度**：HIGH - 可维护性

**发现轮次**：第1轮·代码质量

**修复建议**：将命令分发重构为基于字典的路由表，使用 `match/case` 或命令注册表模式。

---

### H7. 测试：`ProjectManager._instance` 单例状态泄露

**位置**：`tests/test_gateway_handler.py:27-30`

**问题描述**：`_reset_singletons()` 只被 `handler` 和 `handler_with_project` fixture 调用，但直接操作 `handler._sessions`、`handler._health_by_session` 的测试没有调用它。遗留状态会在测试间泄漏。

**严重程度**：HIGH - 测试质量

**发现轮次**：第1轮·测试覆盖

**修复建议**：所有修改 handler 状态的测试都应在 teardown 中调用 `_reset_singletons()`。

---

### H8. 测试：`reset_queue()` 清理不完整

**位置**：`tests/test_message_queue.py:25-36`

**问题描述**：`test_enqueue_pop_order` 末尾的 `reset_queue()` 只清除 default key，但 `"s1"` bucket 仍有1条消息未清理。`test_dedupe_same_text`、`test_queue_cap_drop_old` 也没有清理。

**严重程度**：HIGH - 测试质量

**发现轮次**：第1轮·测试覆盖

**修复建议**：在 `reset_queue()` 中强制清理所有会话的队列，或在 teardown 中遍历清理所有 key。

---

### H9. `tool_batch.py` 并行执行前未检查 guardrails halt

**位置**：`butler/core/tool_batch.py:316-325`

**问题描述**：当 `enable_parallel_tools` 为 true 时，`execute_tools_parallel` 调用的 `_precheck_tool` 不检查 `guardrails.halt_decision`。如果 halt 在并行执行开始前被设置，工具仍可能被并行分派。

**严重程度**：HIGH - 逻辑缺陷

**发现轮次**：第2轮·工具系统

**修复建议**：Guardrails `halt_decision` 必须在 `_precheck_tool` 中检查以防止并行分派。

---

### H10. `registry.py` 工具名覆盖无警告

**位置**：`butler/tools/registry.py:56`

**问题描述**：`_REGISTRY[name] = ToolEntry(...)` 静默覆盖任何同名已存在的工具。没有重复检查、警告或错误。

**严重程度**：HIGH - 可维护性

**发现轮次**：第2轮·工具系统

**修复建议**：如果工具名已存在，应抛出 `ValueError` 或记录警告。

---

### H11. `path_safety.py` symlink 可绕过敏感路径检查

**位置**：`butler/tools/path_safety.py:340-378`

**问题描述**：`_sensitive_path_error` 只检查 `Path.home()` 相对路径，不解析 symlink。workspace 路径如 `/home/user/project/links-to/.ssh` 会通过检查，但解析后指向 `~/.ssh`。

**严重程度**：HIGH - 安全漏洞

**发现轮次**：第2轮·工具系统

**修复建议**：在所有路径比较前调用 `path.resolve()`。

---

### H12. `IDEMPOTENT_TOOLS` 缺少常用读取工具

**位置**：`butler/tool_guardrails.py:24-36`

**问题描述**：`IDEMPOTENT_TOOLS` 缺少 `grep`、`glob`、`search_code`、`list_dir` 等在 `batch_sequence_guard.py` 中被跟踪为 stale-read-batch-tools 的工具。

**严重程度**：HIGH - 功能缺陷

**发现轮次**：第2轮·工具系统

**修复建议**：将 `grep`、`glob`、`search_code`、`list_dir` 加入 `IDEMPOTENT_TOOLS`。

---

### H13. `enqueue_inbound` 每次插入全量排序 O(n log n)

**位置**：`butler/gateway/message_queue.py:143-149`

**问题描述**：每次 `enqueue_inbound` 调用都对整个 bucket 进行全量排序，时间复杂度 O(n log n)，高并发场景下成为性能瓶颈。

**严重程度**：HIGH - 性能问题

**发现轮次**：第2轮·Gateway与队列

**修复建议**：使用堆维护有序队列，或在插入时利用优先级队列特性避免全量排序。

---

### H14. 模块级 `_LOCK` 所有会话竞争同一把锁

**位置**：`butler/gateway/message_queue.py:36-42`

**问题描述**：所有会话共享同一个 `_LOCK`。虽然 `_QUEUES` 按 session_key 分隔，但所有对任何 session 的入队/出队操作都要竞争同一把锁。

**严重程度**：HIGH - 并发性能

**发现轮次**：第2轮·Gateway与队列

**修复建议**：考虑 session_key 级别的细粒度锁，或使用无锁数据结构。

---

### H15. `evict_idle` 嵌套锁有潜在死锁风险

**位置**：`butler/gateway/session_registry.py:234-276`

**问题描述**：`evict_idle` 持有 `_lock` 遍历过期会话，但 `_reset_if_still_idle` 内部获取 `session_lock` 再获取 `_lock`。如果另一个线程在 `get_or_create` 中持有 `_lock` 并等待 `session_lock`，可能形成等待环。

**严重程度**：HIGH - 线程安全

**发现轮次**：第2轮·Gateway与队列

**修复建议**：重新设计锁顺序，或使用 try_lock_with_timeout 替代阻塞获取。

---

### H16. `enforce_lru` 在锁外可能驱逐刚创建的 session

**位置**：`butler/gateway/session_registry.py:69-79`

**问题描述**：`enforce_lru()` 在锁外执行，线程 A 释放锁后线程 B 创建 session，线程 A 再调用 `enforce_lru()` 可能驱逐 B 刚创建的 session。

**严重程度**：HIGH - 逻辑缺陷

**发现轮次**：第2轮·Gateway与队列

**修复建议**：`enforce_lru()` 应在锁内执行，或在驱逐前验证 session 创建时间。

---

### H17. `query_decompose` rank_score vs score 字段名不匹配导致去重失效

**位置**：`butler/memory/query_decompose.py:100`

**问题描述**：`merge_retrieval_hits` 使用 `item.get("rank_score")` 判断，但 `search_with_subqueries` 的 `search_fn` 返回结果只包含 `score` 字段。因此 `rank_score` 始终为0，dedupe 逻辑永远触发"保留新 hit"。

**严重程度**：HIGH - 功能缺陷

**发现轮次**：第2轮·记忆系统

**修复建议**：统一字段名为 `score`，或修改 `merge_retrieval_hits` 使用 `score` 字段。

---

### H18. `observer_queue` rollback 乱序

**位置**：`butler/memory/observer_queue.py:121-128`

**问题描述**：`insert_many(batch)` 失败后，代码 `reversed(batch)` 逐条 `appendleft` 回队列。如果新批次 items 被 appendleft 的顺序是 reversed(original)，队列内容与原始顺序不一致。

**严重程度**：HIGH - 数据一致性

**发现轮次**：第2轮·记忆系统

**修复建议**：直接用 `extendleft(batch)` 而非逐条 `appendleft(reversed(batch))`。

---

### H19. `observation_store` 迁移脚本 dedupe 逻辑无效

**位置**：`butler/memory/observation_store.py:75-97`

**问题描述**：DELETE subquery 在表刚创建时执行（无数据），该 DELETE 实际删除0行。然后 DROP/CREATE INDEX —— 这个 dedupe 逻辑从未真正运行过。

**严重程度**：HIGH - 逻辑缺陷

**发现轮次**：第2轮·记忆系统

**修复建议**：在表有数据时执行 dedupe，或使用 `INSERT OR IGNORE` 防止重复插入。

---

### H20. `delegate_depth +1` 逻辑混乱

**位置**：`butler/task_orchestrator.py:159`

**问题描述**：`config.delegate_depth` 传入后创建 tool_dispatcher 时传 `depth=config.delegate_depth + 1`，这个+1是什么意思？如果 delegate_depth=2 达到上限，实际创建的 agent 还有 depth=3。

**严重程度**：HIGH - 逻辑错误

**发现轮次**：第2轮·Workflow系统

**修复建议**：明确注释 delegate_depth 的语义，+1 应在文档中说明或提取为命名常量。

---

### H21. `diff_section` 追加导致 summary 超长

**位置**：`butler/delegate_job.py:199`

**问题描述**：`task_preview = (job.task or "").strip()[:200]`，但 `_try_attach_diff_summary` 会把 diff stat（可能 >1000 字符）追加到 report.summary，最终可能超过微信消息长度限制。

**严重程度**：HIGH - 边界问题

**发现轮次**：第2轮·Workflow系统

**修复建议**：在追加前检查总长度，超限时截断 diff_section 而非整个 summary。

---

### H22. `fallback.py` 硬编码 minimax 特定逻辑

**位置**：`butler/transport/fallback.py:58-61`

**问题描述**：为 minimax 硬编码了回退目标列表 `("deepseek", "qwen", "openai")`，污染了通用的 failover 链设计。

**严重程度**：HIGH - 架构问题

**发现轮次**：第3轮·Transport层

**修复建议**：改为通用配置驱动或策略模式，不在代码中硬编码特定 provider 的回退链。

---

### H23. `_ROLE_ALIASES` 两处定义，不同步风险

**位置**：`butler/model_resolve.py:17-22` 和 `butler/orchestrator.py:30-34`

**问题描述**：`_ROLE_ALIASES` 在两个模块中独立定义，内容一致但无共享来源。长期维护风险 —— 若在一个地方添加新别名而忘记另一个，会导致行为不一致。

**严重程度**：HIGH - 可维护性

**发现轮次**：第3轮·CLI与配置

**修复建议**：提取到 `butler/config.py` 作为单一数据源，两个模块都引用它。

---

### H24. 全局配置单例不感知环境变量动态更新

**位置**：`butler/config.py:347-356`

**问题描述**：`get_butler_settings()` 返回全局单例 `_settings`，但 `_load_env_providers()` 仅在 `__post_init__` 时调用一次。进程运行期间修改环境变量不会更新配置。

**严重程度**：HIGH - 状态一致性

**发现轮次**：第3轮·CLI与配置

**修复建议**：环境变量变更后调用 `reload_butler_settings()`；或在 `config_set` 对 API key 相关 key 生效时提示重启。

---

### H25. `reset_sessions_for_chat` 竞态条件

**位置**：`butler/gateway/session_registry.py:165-182`

**问题描述**：Keys 在 `_lock` 下收集，但 `reset(key)` 在锁外调用。`reset` 内部获取 `session_lock(key)`，如果另一个线程正在 `reset_all`，可能发生死锁。

**严重程度**：HIGH - 线程安全

**发现轮次**：第3轮·Session与生命周期

**修复建议**：在锁内执行所有 reset 操作，或使用 try_lock_with_timeout。

---

### H26. Daemon 线程无 shutdown 协调

**位置**：`butler/session/lifecycle.py:654`

**问题描述**：后台提取运行在 daemon 线程中，主进程收到 shutdown 信号时强制杀死而不完成工作。如果在内存同步阶段发生，数据可能未持久化。

**严重程度**：HIGH - 资源管理

**发现轮次**：第3轮·Session与生命周期

**修复建议**：使线程非 daemon 并设置 join timeout，或实现 shutdown flag 让线程定期检查。

---

### H27. `_watermark_store` 状态污染风险

**位置**：`butler/session/lifecycle.py:547-552`

**问题描述**：watermark store 附加到 `orchestrator` 对象。处理多个 chat session 时，旧 session 的 watermark 持久化。新 session 如果 session_id 为空，`_watermark_key("")` 返回 `"_default"`，导致 watermark 状态泄漏。

**严重程度**：HIGH - 状态一致性

**发现轮次**：第3轮·Session与生命周期

**修复建议**：watermark key 必须始终包含有效 session_id，空 session_id 应抛出错误而非回退到 default。

---

### H28. `llm_retry.py:176` 属性名错误

**位置**：`butler/core/llm_retry.py:176`

**问题描述**：`record_provider_success` 使用 `getattr(client, "provider", "")` 但 LLMClient 的属性名是 `provider_name`（见 llm_client.py:33），不是 `provider`。

**严重程度**：HIGH - 功能缺陷

**发现轮次**：第3轮·Transport层

**修复建议**：修正属性名为 `provider_name`。

---

### H29. `create_project` 并发竞争

**位置**：`butler/project/manager.py:214-248`

**问题描述**：`workspace.mkdir()` 与 `refresh()` 之间无原子操作保证。两个进程可能同时通过 `workspace.exists()` 检查并创建同一目录。

**严重程度**：HIGH - 并发安全

**发现轮次**：第4轮·项目系统

**修复建议**：使用原子创建模式（`Path.mkdir(exist_ok=True)` 配合文件锁），或使用数据库级别的约束。

---

### H30. `get_project_manager` 异常被静默吞掉

**位置**：`butler/project/preflight.py:274-275`

**问题描述**：`get_project_manager()` 失败时仅 `logger.debug`，不返回任何 FAIL 项。用户以为检查通过，实际静默跳过。

**严重程度**：HIGH - 可观测性

**发现轮次**：第4轮·项目系统

**修复建议**：至少提升到 `warning` 级别，或在 preflight 结果中标记为 SKIP。

---

### H31. `auto_extract` 无限制递归扫描（目录排除不完整）

**位置**：`butler/project/project_memory.py:535`

**问题描述**：硬编码排除列表可能遗漏常见的大型目录变体（如 `.venv2`、`__pycache__` 的变体）。`rglob` 会扫描到大量无用文件。

**严重程度**：HIGH - 资源耗尽

**发现轮次**：第4轮·项目系统

**修复建议**：使用基于 `.gitignore` 模式的排除，或限制递归深度。

---

### H32. `structured_output` 校验失败仍被覆盖

**位置**：`butler/report/generator.py:296`

**问题描述**：当 schema 校验失败时，`enrich_output_schema` 仍然会将 `parsed` 赋值给 `report.structured_output`。下游代码无法区分"校验失败但有部分数据"和"完全无效"。

**严重程度**：HIGH - 可诊断性

**发现轮次**：第4轮·Report与后处理

**修复建议**：校验失败时应设置 `report.structured_output = None` 或标记 `report._schema_validation_failed = True`。

---

### H33. `on_llm_start` 缺少异常保护

**位置**：`butler/core/llm_retry.py:42-43`

**问题描述**：`on_llm_start` 回调调用无 try 保护，而 `on_llm_complete` 有。如果用户注册的 `on_llm_start` hook 有 bug，会导致整个 agent loop 崩溃。

**严重程度**：HIGH - 稳定性

**发现轮次**：第4轮·Hook与回调

**修复建议**：为 `on_llm_start` 添加 try/except 保护，记录 warning 但不阻断 LLM 调用。

---

### H34. 全局 `_REGISTRY` 非线程安全

**位置**：`butler/gateway/hooks.py:15`

**问题描述**：`_REGISTRY: dict[str, list[HookFn]]` 是全局可变字典，多线程并发 `register_hook`/`invoke_hook` 会产生竞态。`clear_hooks` 只能清空整个 name 的 hook 列表，无法移除单个 hook。

**严重程度**：HIGH - 线程安全

**发现轮次**：第4轮·Hook与回调

**修复建议**：使用 `threading.RLock` 保护 `_REGISTRY`，或使用 `contextvars` 实现线程局部 hook 注册表。

---

### H35. `shell=False` 与 bash 命令语义不匹配

**位置**：`butler/hooks/runner.py:522-523`

**问题描述**：`subprocess.run(["bash", "-c", rule.command], shell=False)` 语义上表示执行不带 shell 包装的原始命令，但 `rule.command` 是 bash 脚本字符串（可能包含管道、重定向）。虽然通过 `bash -c` 能工作，但违背了 `shell=False` 的语义约定。

**严重程度**：HIGH - 可维护性

**发现轮次**：第4轮·Hook与回调

**修复建议**：使用 `shell=True` 或将命令封装为 shell 脚本文件而非字符串。

---

### H36. `ContextPipeline._attached_loop` 形成引用环

**位置**：`butler/core/agent_loop.py:62-63`

**问题描述**：`AgentLoop -> ContextPipeline -> _attached_loop -> AgentLoop` 形成引用环。Python GC 可处理，但会导致内存峰值翻倍、session 结束时 loop 对象无法及时释放。

**严重程度**：HIGH - 内存管理

**发现轮次**：第4轮·循环依赖与边界case

**修复建议**：使用弱引用 `weakref.ref` 替代 `_attached_loop`，或通过回调机制传递必要信息。

---

### H37. `reset_all` 强制清理可能遗漏 finalization

**位置**：`butler/gateway/session_registry.py:205-215`

**问题描述**：timeout 发生时 `items` 收集了但还没做 cleanup，如果 session 仍有未完成的清理工作，后续 `_finalize_loop` 可能失败或产生副作用。

**严重程度**：HIGH - 状态一致性

**发现轮次**：第4轮·循环依赖与边界case

**修复建议**：timeout 时应记录未清理 session 并在日志中警告，而非直接丢弃。

---

## MEDIUM 问题清单

### M1. 多处 `logger.debug` 静默吞噬异常

**位置**：`butler/core/tool_batch.py:135-136` 等多处

**问题描述**：工具批次执行中大量使用 `logger.debug` 吞噬异常，如果 two-phase confirm 检查失败，工具会静默继续而非报错或警告。

**严重程度**：MEDIUM - 可观测性

**发现轮次**：第1轮·代码质量

---

### M2. `_PER_TOOL_THRESHOLDS_CACHE` 竞态条件

**位置**：`butler/core/tool_result_storage.py:72-90`

**问题描述**：无锁保护 read-then-assign 模式。两个线程同时调用时可能同时进入计算分支。

**严重程度**：MEDIUM - 线程安全

**发现轮次**：第1轮·代码质量

---

### M3. `execution_context` 的 fallback 逻辑脆弱

**位置**：`butler/execution_context.py:88-95`

**问题描述**：当 orchestrator 存在但 session_key 为空时返回空字符串 `""`，这会导致 session_key 丢失（空字符串 vs 未设置）。

**严重程度**：MEDIUM - 逻辑缺陷

**发现轮次**：第1轮·架构设计

---

### M4. 压缩状态跨调用持久化可能污染

**位置**：`butler/core/context_pipeline.py:34-35`

**问题描述**：`compression_summary` 和 `consecutive_compact_failures` 在 pipeline 实例上持久化，如果同一实例被多个调用方共享，状态可能互相污染。

**严重程度**：MEDIUM - 状态一致性

**发现轮次**：第1轮·架构设计

---

### M5. Lazy Import 散落掩盖真实依赖

**位置**：多处，如 `butler/core/agent_loop.py:112`

**问题描述**：大量使用 try/except import 规避循环依赖，使代码依赖关系不透明。

**严重程度**：MEDIUM - 可维护性

**发现轮次**：第1轮·架构设计

---

### M6. `_path_outside_workspace` 对 symlink 没有二次解析

**位置**：`butler/permissions/rules.py:88-89`

**问题描述**：只解析一次 symlink，如果 workspace 本身是 symlink 或路径中间包含 symlink，可能导致 bypass。

**严重程度**：MEDIUM - 安全漏洞

**发现轮次**：第1轮·安全与权限

---

### M7. `security_blacklist` 的 re.search 可能 DoS

**位置**：`butler/permissions/rules.py:264-266`

**问题描述**：用户配置的 `pattern_regex` 直接传入 `re.search`，恶意 regex 可能导致 backtracking DoS。

**严重程度**：MEDIUM - 安全漏洞

**发现轮次**：第2轮·Workflow系统

---

### M8. `until_assertion` 错误被 rescue_steps 掩盖

**位置**：`butler/task_orchestrator.py:562-612`

**问题描述**：`_run_rescue_steps` 最终返回的 `error=failed.error or "rescue_completed"`，如果 rescue steps 没有产生新 error，错误信息变成无意义的 "rescue_completed"。

**严重程度**：MEDIUM - 可诊断性

**发现轮次**：第2轮·Workflow系统

---

### M9. `execute_graph` 的 error 合并用分号分隔但 error 可能含分号

**位置**：`butler/task_orchestrator.py:497`

**问题描述**：`graph.error = "; ".join(errors)`，如果某个 error 字符串本身包含分号，解析时无法正确分割。

**严重程度**：MEDIUM - 可诊断性

**发现轮次**：第2轮·Workflow系统

---

### M10. `enforce_lru` 在 `get_or_create` 外部调用

**位置**：`butler/gateway/session_registry.py:69-79`

**问题描述**：在锁外执行 `enforce_lru()`，可能导致刚创建的 session 被驱逐。

**严重程度**：MEDIUM - 逻辑缺陷

**发现轮次**：第2轮·Gateway与队列

---

### M11. `reset_all` 的 `_resetting_all` 标志超时后仍有竞态

**位置**：`butler/gateway/session_registry.py:197-232`

**问题描述**：如果超时后强制 clear，等待中的进入可能继续执行导致不一致状态。

**严重程度**：MEDIUM - 线程安全

**发现轮次**：第2轮·Gateway与队列

---

### M12. `_persist_remove` 低效的逐行文本处理

**位置**：`butler/gateway/message_queue.py:305-324`

**问题描述**：每移除一条消息就要读取整个文件、遍历所有行、然后重写。

**严重程度**：MEDIUM - 性能问题

**发现轮次**：第2轮·Gateway与队列

---

### M13. `schedule_supplementary_reply` 的错误处理静默失败

**位置**：`butler/gateway/outbound_bridge.py:375-403`

**问题描述**：如果消息发送失败，用户不会收到任何提示。

**严重程度**：MEDIUM - 可观测性

**发现轮次**：第2轮·Gateway与队列

---

### M14. `completion_notify.py` 持久化和发送之间没有事务性

**位置**：`butler/gateway/completion_notify.py:249-302`

**问题描述**：极端情况下可能重复推送。

**严重程度**：MEDIUM - 数据一致性

**发现轮次**：第2轮·Gateway与队列

---

### M15. ChromaVectorStore 初始化失败被静默吞掉

**位置**：`butler/memory/vector_store.py:236-244`

**问题描述**：ChromaDB 初始化失败只记录 warning 后 fallback 到内存实现，用户毫无知觉。

**严重程度**：MEDIUM - 可观测性

**发现轮次**：第2轮·记忆系统

---

### M16. `fallback.jsonl` 无原子写保护

**位置**：`butler/memory/vector_store.py:164-167`

**问题描述**：直接 `write_text` 覆盖原文件，无 journaling 或临时文件写入。如果进程在写操作中途崩溃，`fallback.jsonl` 会 partial write。

**严重程度**：MEDIUM - 数据完整性

**发现轮次**：第2轮·记忆系统

---

### M17. `_MAX_FACTS_PER_SESSION` 截断时机错误

**位置**：`butler/memory/fact_extraction.py:51`

**问题描述**：截断在 save 时执行（取最后50条），而非主动管理。如果 dedupe 后超过50条，早期重要上下文会被丢弃。

**严重程度**：MEDIUM - 数据完整性

**发现轮次**：第2轮·记忆系统

---

### M18. 重复 anchor 插入可能污染对话历史

**位置**：`butler/core/post_compact_cleanup.py:165`

**问题描述**：每次 compaction 都插入新的 `[POST-COMPACT ANCHORS]` user 消息，长会话累积增加 token 消耗。

**严重程度**：MEDIUM - 资源浪费

**发现轮次**：第2轮·记忆系统

---

### M19. `_collect_dev_session_changes` 无保护导入

**位置**：`butler/core/post_compact_cleanup.py:211-268`

**问题描述**：直接调用 `get_tool_audit_events` 不在 try/except 内，如果函数不存在或签名变化，整个 anchor 构建失败。

**严重程度**：MEDIUM - 健壮性

**发现轮次**：第2轮·记忆系统

---

### M20. 工具结果存储文件竞争

**位置**：`butler/core/tool_result_storage.py:256-258`

**问题描述**：`path.open("x", ...)` 独占创建，如果两个工具相同 `tool_use_id` 同时 spill，第二个收到 `FileExistsError` 返回 `None`，调用方使用原始巨大文本。

**严重程度**：MEDIUM - 边界问题

**发现轮次**：第2轮·工具系统

---

### M21. `delete_file` 未被分类为 destructive

**位置**：`butler/core/batch_sequence_guard.py:16-21`

**问题描述**：`delete_file` 不在 `DESTRUCTIVE_BATCH_TOOLS` 中也不匹配前缀模式。删除后读取会返回 stale 数据。

**严重程度**：MEDIUM - 功能缺陷

**发现轮次**：第2轮·工具系统

---

### M22. Community trust 只警告不阻止

**位置**：`butler/registry/install_scan.py:73-75`

**问题描述**：`"community_trust"` 不在 `_BLOCK_CODES` 中，即使 `fail_closed=True` 也会继续安装。

**严重程度**：MEDIUM - 安全流程

**发现轮次**：第2轮·工具系统

---

### M23. `_extract_command_paths` 漏掉引号包围的路径

**位置**：`butler/tools/path_safety.py:268-295`

**问题描述**：正则错过空格包围的路径如 `"/path/with spaces/file.txt"`。

**严重程度**：MEDIUM - 功能缺陷

**发现轮次**：第2轮·工具系统

---

### M24. `resolve_api_key` 返回 None 无警告

**位置**：`butler/transport/providers.py:31`

**问题描述**：所有 env_vars 都未设置时返回 `None`，调用方直接使用导致后续 SDK 初始化使用占位符而非报错。

**严重程度**：MEDIUM - 可诊断性

**发现轮次**：第3轮·Transport层

---

### M25. Anthropic default_model 版本号硬编码

**位置**：`butler/transport/providers.py:100`

**问题描述**：带日期的模型名有效期有限，代码部署后模型已下线会直接失败。

**严重程度**：MEDIUM - 可维护性

**发现轮次**：第3轮·Transport层

---

### M26. Timeout 和 ConnectionError 分类为同一 reason

**位置**：`butler/error_classifier.py:122-126`

**问题描述**：两者都归为 `timeout`，但 connection error 通常暗示网络不可达，应立即 fail 并切换而非重试。

**严重程度**：MEDIUM - 错误处理

**发现轮次**：第3轮·Transport层

---

### M27. 超时后线程未 join 导致资源泄漏

**位置**：`butler/interruptible_client.py:43-49`

**问题描述**：`StaleApiCallError` 抛出后 thread 仍是 alive 状态，频繁调用会积累大量 zombie 线程。

**严重程度**：MEDIUM - 资源管理

**发现轮次**：第3轮·Transport层

---

### M28. Anthropic transport 丢失 reasoning 字段

**位置**：`butler/transport/anthropic_transport.py:28-86`

**问题描述**：`AnthropicTransport.convert_messages` 没有处理 `codex_reasoning_items` 和 `codex_message_items`，也没有调用 reasoning replay。

**严重程度**：MEDIUM - 功能完整性

**发现轮次**：第3轮·Transport层

---

### M29. `config_set` 验证 int 但不转换

**位置**：`butler/config_service.py:132-136`

**问题描述**：验证后未转换直接存原字符串，调用方可能期望 int 类型。

**严重程度**：MEDIUM - 类型一致性

**发现轮次**：第3轮·CLI与配置

---

### M30. Provider 预设允许空 model 字符串

**位置**：`butler/provider_presets.py:32`

**问题描述**：内置预设 `minimax-default` 的 model 为空字符串 `""`，语义模糊。

**严重程度**：MEDIUM - 可诊断性

**发现轮次**：第3轮·CLI与配置

---

### M31. 会话列表无 transcript 大小限制

**位置**：`butler/cli/sessions_cli.py:38-52`

**问题描述**：读取每个 transcript 文件的所有行来统计，大会话文件可能数 MB。

**严重程度**：MEDIUM - 资源管理

**发现轮次**：第3轮·CLI与配置

---

### M32. Non-atomic dict operations in enforce_lru

**位置**：`butler/gateway/session_registry.py:268-271`

**问题描述**：四个独立的 `pop()` 操作不是原子的，如果异常发生在中间，session 状态会不一致。

**严重程度**：MEDIUM - 状态一致性

**发现轮次**：第3轮·Session与生命周期

---

### M33. File size TOCTOU in transcript append

**位置**：`butler/core/session_transcript.py:59`

**问题描述**：`path.stat().st_size` 在写完成后检查，期间另一个进程可能修改文件。

**严重程度**：MEDIUM - 竞态条件

**发现轮次**：第3轮·Session与生命周期

---

### M34. `_reset_if_still_idle` 锁处理脆弱

**位置**：`butler/gateway/session_registry.py:289-307`

**问题描述**：`reset()` 在第300行 pop 但 `finalize()` 在第306行锁外调用，存在竞态。

**严重程度**：MEDIUM - 线程安全

**发现轮次**：第3轮·Session与生命周期

---

### M35. `consecutive_compact_failures` 赋值逻辑数据流断裂

**位置**：`butler/core/context_pipeline.py:298-300`

**问题描述**：赋值从 diagnostics 读取，如果 `run_hygiene_preflight` 内部异常未写入 diagnostics，`consecutive_compact_failures` 保持旧值。

**严重程度**：MEDIUM - 状态一致性

**发现轮次**：第2轮·记忆系统

---

### M36. `prepare_messages_for_api` 内部异常被静默吞噬

**位置**：`butler/core/context_pipeline.py:239-243`

**问题描述**：非 `ContextPrecheckOverflow` 的异常被 bare `except Exception` 捕获并返回原始消息，调用方以为成功。

**严重程度**：MEDIUM - 可诊断性

**发现轮次**：第2轮·记忆系统

---

### M37. `parse_structured_output` JSON 提取正则过于宽泛

**位置**：`butler/report/generator.py:151-157`

**问题描述**：正则 `\{[^{}]*\}` 无法处理多层嵌套的 JSON 对象，会错误匹配嵌套对象的部分。

**严重程度**：MEDIUM - 可诊断性

**发现轮次**：第4轮·Report与后处理

---

### M38. `memory_update_is_duplicate` 去重逻辑不完整

**位置**：`butler/session/post_session.py:185-190`

**问题描述**：硬编码的前缀列表是不完整的。如果 LLM 生成的记忆文本使用其他变体，去重机制失效。

**严重程度**：MEDIUM - 数据完整性

**发现轮次**：第4轮·Report与后处理

---

### M39. `_invoke_llm` 异常返回处理过于简单

**位置**：`butler/session/post_session.py:206-213`

**问题描述**：当 `_llm_call` 抛出异常时，`str(result)` 可能丢失重要错误信息。调用方只能通过检查返回空字符串判断出了问题。

**严重程度**：MEDIUM - 可诊断性

**发现轮次**：第4轮·Report与后处理

---

### M40. `PostSessionProcessor.process` 没有超时控制

**位置**：`butler/session/post_session.py:215-260`

**问题描述**：双通道记忆提炼（memory + skill）是串行执行的，且没有 timeout 机制。如果 LLM 调用挂起，整个 `process` 会无限等待。

**严重程度**：MEDIUM - 稳定性

**发现轮次**：第4轮·Report与后处理

---

### M41. `cache_report` 异常时静默失败

**位置**：`butler/report/generator.py:619-620`

**问题描述**：报告缓存失败（内存+磁盘）仅记录 debug 级别日志。在生产环境中用户不会收到任何提示。

**严重程度**：MEDIUM - 可观测性

**发现轮次**：第4轮·Report与后处理

---

### M42. 全局 `_REGISTRY` HookBus 非线程安全

**位置**：`butler/gateway/hooks.py:15`

**问题描述**：多会话 gateway 场景中，一个会话调用 `clear_hooks("pre_gateway_dispatch")` 会误清除其他会话注册的同名 hook。

**严重程度**：MEDIUM - 线程安全

**发现轮次**：第4轮·Hook与回调

---

### M43. `trigger_hooks_mutating` 的 TypeError 重试逻辑异常

**位置**：`butler/gateway/hooks.py:64-66`

**问题描述**：重新传入相同参数调用后丢弃结果，这段代码没有实际作用，且可能让调用方误以为做了降级处理。

**严重程度**：MEDIUM - 逻辑缺陷

**发现轮次**：第4轮·Hook与回调

---

### M44. 30秒超时硬编码，无法按hook配置

**位置**：`butler/hooks/runner.py:530`

**问题描述**：不同 hook 可能需要不同超时，轻量检查 hook 应该更快，长时间运行的 git hook 应该允许更长超时。当前实现缺乏灵活性。

**严重程度**：MEDIUM - 可配置性

**发现轮次**：第4轮·Hook与回调

---

### M45. `telemetry` 双重锁嵌套

**位置**：`butler/hooks/telemetry.py:32-44`

**问题描述**：telemetry 锁内部调用 `runtime_metrics.inc()`，后者内部也会获取锁。如果未来 `runtime_metrics` 改用非重入锁，会立刻死锁。

**严重程度**：MEDIUM - 线程安全

**发现轮次**：第4轮·Hook与回调

---

### M46. `child_callbacks` 未注册到线程局部

**位置**：`butler/core/delegate_context.py:38-47`

**问题描述**：嵌套代理共享父回调，`child_callbacks` 返回新的 `LoopCallbacks` 子集但没有被安装，导致子代理拿到的是父代理的完整回调。

**严重程度**：MEDIUM - 回调隔离

**发现轮次**：第4轮·Hook与回调

---

### M47. `ProviderHealth` 缓存无清理机制

**位置**：`butler/transport/provider_health.py`

**问题描述**：`is_circuit_open` / `record_provider_failure` 使用 dict 缓存 circuit breaker 状态，但没有 TTL 清理。失败的 provider 会永远保持 open 状态。

**严重程度**：MEDIUM - 资源管理

**发现轮次**：第4轮·循环依赖与边界case

---

### M48. `reset_hook_telemetry` 和 `runtime_metrics.reset_session` 双重清理不一致

**位置**：`butler/hooks/telemetry.py:53-66`

**问题描述**：如果 `runtime_metrics.reset_session` 失败（如模块导入问题），`_RECORDS` 已清但 metrics 未清，数据就不一致了。

**严重程度**：MEDIUM - 状态一致性

**发现轮次**：第4轮·Hook与回调

---

### M49. `_session_key_from_payload` 异常处理过于宽泛

**位置**：`butler/hooks/runner.py:60-69`

**问题描述**：`except Exception: return ""` 会捕获所有异常，包括 `KeyboardInterrupt`、`SystemExit` 等。

**严重程度**：MEDIUM - 错误处理

**发现轮次**：第4轮·Hook与回调

---

### M50. `inbound_idempotency` 全局锁竞争

**位置**：`butler/gateway/inbound_idempotency.py:16-18`

**问题描述**：所有 session 共用 `_LOCK`，每个 inbound message 都要竞争锁。当某 session 长时间持锁操作 `_prune_session` 时，其他 session 被阻塞。

**严重程度**：MEDIUM - 并发性能

**发现轮次**：第4轮·循环依赖与边界case

---

### M51. 工具派发闭包捕获可变状态

**位置**：`butler/core/tool_batch.py:115`

**问题描述**：`prefetched: dict[str, str]` 在 `_dispatch_one` 内被修改，且通过 `on_tool_ready` 闭包共享给并发执行的其他 tool call。如果两个 tool call 有相同 `tool_call_id`，会产生数据竞争。

**严重程度**：MEDIUM - 线程安全

**发现轮次**：第4轮·循环依赖与边界case

---

### M52. 单例模式非线程安全

**位置**：`butler/project/manager.py:24-30`

**问题描述**：`_initialized` 标志的检查和设置之间没有锁。多线程可能同时看到 `_initialized = False` 并重复初始化，导致状态覆盖、回调列表被重置。

**严重程度**：MEDIUM - 线程安全

**发现轮次**：第4轮·项目系统

---

### M53. 模糊匹配返回 None 但无提示

**位置**：`butler/project/manager.py:92-95`

**问题描述**：子串匹配匹配到多个项目时返回 `None`，调用方无法区分「项目不存在」和「匹配歧义」两种情况。

**严重程度**：MEDIUM - 可诊断性

**发现轮次**：第4轮·项目系统

---

### M54. 路径安全检查可绕过

**位置**：`butler/project/preflight.py:106-113`

**问题描述**：workspace 通过 symlink 指向 `projects_dir` 外时，`relative_to` 检测可能产生不一致的安全边界判定。

**严重程度**：MEDIUM - 安全漏洞

**发现轮次**：第4轮·项目系统

---

### M55. `_index_project_dir` 异常后无告警

**位置**：`butler/project/reindex.py:155-167`

**问题描述**：项目加载失败仅 `logger.warning`，调用方无法感知。用户以为所有项目都已索引，实际部分被静默跳过。

**严重程度**：MEDIUM - 可观测性

**发现轮次**：第4轮·项目系统

---

## LOW 问题清单

### L1. 多处重复的误导性日志消息

**位置**：多处

**问题描述**：日志消息如 "skipped"、"on delta cb skipped" 被 copy-paste 到不相关的异常处理器，调试时产生误导。

**严重程度**：LOW - 可诊断性

**发现轮次**：第1轮·代码质量

---

### L2. `tool_batch.py` 双重 try 模式

**位置**：`butler/core/tool_result_storage.py:245-261`

**问题描述**：`FileExistsError` handler 检查 `if not path.is_file()` 是冗余的存在检查（如果 FileExistsError 被抛出，文件存在）。

**严重程度**：LOW - 代码质量

**发现轮次**：第1轮·代码质量

---

### L3. `_normalize_path` 静默回退到原始路径

**位置**：`butler/core/parallel_tools.py:19-23`

**问题描述**：对任何 `Path` 异常（包括权限错误）都静默回退，path overlap 检测可能给出错误答案。

**严重程度**：LOW - 可诊断性

**发现轮次**：第1轮·代码质量

---

### L4. Transport 发现机制通过全局函数

**位置**：`butler/transport/llm_client.py:122`

**问题描述**：Transport 实例通过 `get_transport()` 全局发现而非依赖注入，使单元测试需要 mock 全局状态。

**严重程度**：LOW - 可测试性

**发现轮次**：第1轮·架构设计

---

### L5. MagicMock 使用无 spec

**位置**：`tests/test_tool_batch.py:205`

**问题描述**：`boundary = MagicMock()` 没有 spec，任何属性访问都返回另一个 mock，掩盖类型错误。

**严重程度**：LOW - 测试质量

**发现轮次**：第1轮·测试覆盖

---

### L6. `plan mode` blocked tools 缺少 `patch`

**位置**：`butler/plan/mode.py:15-20`

**问题描述**：`patch` 是 mutating 工具但在 plan mode 未被阻止。实际通过 `is_plan_writable_path` 处理，正确。

**严重程度**：LOW - 已处理

**发现轮次**：第1轮·安全与权限

---

### L7. `_env_float` 重复实现

**位置**：`completion_notify.py:23-27` 和 `outbound_bridge.py:40-44`

**问题描述**：完全相同的工具函数在两个地方重复。

**严重程度**：LOW - 代码重复

**发现轮次**：第2轮·Gateway与队列

---

### L8. MCP HTTP private host 检查允许 `0.0.0.0`

**位置**：`butler/mcp/config.py:19-25`

**问题描述**：`0.0.0.0` 是 listen 地址而非 connect 地址，但 `allow_private_http=False` 默认正确阻止。

**严重程度**：LOW - 已处理

**发现轮次**：第1轮·安全与权限

---

### L9. `_match_glob` 不支持中间 `*`

**位置**：`butler/permissions/rules.py:65-71`

**问题描述**：只支持末尾 `*` 前缀匹配，不支持 `/tmp/*.py` 这类中间 `*`。

**严重程度**：LOW - 功能限制

**发现轮次**：第2轮·Workflow系统

---

### L10. `title` 字段无长度约束

**位置**：`butler/memory/observer_queue.py:93`

**问题描述**：当 `norm_path` 非空时 title 可达320+字符，无截断处理。

**严重程度**：LOW - 边界问题

**发现轮次**：第2轮·记忆系统

---

### L11. `_env_float` 和 `env_truthy` 重复实现

**位置**：`env_parse.py:8-13` vs `config_service.py:130`

**问题描述**：判断标准一致但代码重复。

**严重程度**：LOW - 代码重复

**发现轮次**：第3轮·CLI与配置

---

### L12. `load_dotenv()` 在模块级别调用

**位置**：`butler/config.py:21`

**问题描述**：环境变量加载时机依赖导入顺序。

**严重程度**：LOW - 可维护性

**发现轮次**：第3轮·CLI与配置

---

### L13. `_read_rows` 不健壮处理畸形 TSV

**位置**：`butler/experiments/ledger.py:39-48`

**问题描述**：TSV 文件有缺失字段或额外列时，静默跳过畸形行而不记录。

**严重程度**：LOW - 可诊断性

**发现轮次**：第3轮·Session与生命周期

---

### L14. `crash_guard` 使用已废弃的 os.getenv 模式

**位置**：`butler/experiments/crash_guard.py:13`

**问题描述**：使用 `os.getenv("X", "3") or "3"` 模式，如果 env var 设置为空字符串会返回空字符串。

**严重程度**：LOW - 健壮性

**发现轮次**：第3轮·Session与生命周期

---

### L15. `_format_messages` 截断逻辑可能丢失关键信息

**位置**：`butler/session/post_session.py:112-115`

**问题描述**：TOOL 消息被截断到 200 字符后标记长度，但其他角色统一截断到 800 字符。对于包含长决策或分析结果的 assistant 消息，800 字符可能不足。

**严重程度**：LOW - 数据完整性

**发现轮次**：第4轮·Report与后处理

---

### L16. `_normalize_detail_request` 别名匹配优先级问题

**位置**：`butler/gateway/handler_helpers.py:164-165`

**问题描述**：如果用户输入 "/detail 报错信息"，由于 "报错" 被检查但未区分位置，会错误返回 `None`。

**严重程度**：LOW - 逻辑缺陷

**发现轮次**：第4轮·Report与后处理

---

### L17. `AgentReport.from_dict` 类型转换过于宽松

**位置**：`butler/report/generator.py:88-103`

**问题描述**：所有字段都通过 `str()` 强制转换，丢失了原始类型信息。如果收到 `{"issues": {"error": "something"}}`，会静默转换为 `["{'error': 'something'}"]`。

**严重程度**：LOW - 类型安全

**发现轮次**：第4轮·Report与后处理

---

### L18. `should_continue` 回调无类型验证

**位置**：`butler/core/loop_types.py:75`

**问题描述**：`should_continue` 返回类型标注为 `bool`，但调用处直接使用。如果 hook 返回 `None` 或非 bool 值，行为不确定。

**严重程度**：LOW - 类型安全

**发现轮次**：第4轮·Hook与回调

---

### L19. BUTLER_HOOK_INPUT 环境变量截断警告缺失

**位置**：`butler/hooks/runner.py:519`

**问题描述**：`stdin_json[:8000]` 被截断到 8KB，但环境变量传给了 hook 脚本，hook 脚本无法知道数据被截断。

**严重程度**：LOW - 可诊断性

**发现轮次**：第4轮·Hook与回调

---

### L20. `ExperienceStore._ensure_experience_columns` 每次插入都检查

**位置**：`butler/memory/butler_memory.py:198-207`

**问题描述**：每次 insert 都执行 `PRAGMA table_info` 查询表结构，应改为仅在 `_init_db` 时执行一次。

**严重程度**：LOW - 性能问题

**发现轮次**：第4轮·循环依赖与边界case

---

### L21. `AgentLoop` 内部状态不一致风险

**位置**：`butler/core/agent_loop.py:112-114`

**问题描述**：如果 `merge_loop_callbacks` 抛出异常，`saved_callbacks` 未被正确保存则状态会丢失。

**严重程度**：LOW - 状态一致性

**发现轮次**：第4轮·循环依赖与边界case

---

### L22. 路径解析不一致

**位置**：`butler/project/worktree.py:39` / `butler/project/manager.py:40`

**问题描述**：`worktree.py` 中 `effective_workspace` 只用 `expanduser()` 而 `manager.py` 同时用 `expanduser().resolve()`。同样传入 `~/foo`，在不同模块中解析为不同规范路径。

**严重程度**：LOW - 可维护性

**发现轮次**：第4轮·项目系统

---

### L23. `create_project` 写文件后无原子性保证

**位置**：`butler/project/manager.py:239-245`

**问题描述**：`workspace.mkdir()` → `write_project_yaml()` → `ensure_memory_skeleton()` → `refresh()` 序列中途失败会导致部分创建状态。

**严重程度**：LOW - 状态一致性

**发现轮次**：第4轮·项目系统

---

### L24. `ensure_memory_skeleton` 模板硬编码

**位置**：`butler/project/archetypes.py:30-35`

**问题描述**：`_MEMORY_TEMPLATE` 内联在代码中，无法自定义项目级记忆模板。不同项目类型共用同一模板。

**严重程度**：LOW - 可配置性

**发现轮次**：第4轮·项目系统

---

## 按模块分类

### 安全与权限（CRITICAL: 2, HIGH: 3）

| # | 问题 | 位置 | 严重度 |
|---|------|------|--------|
| C1 | 环境变量注入绕过Terminal白名单 | `path_safety.py:48-59` | CRITICAL |
| C2 | MCP community env_hints 诱骗凭据 | `mcp_install.py:46-49` | CRITICAL |
| H3 | permissions.yaml 由 workspace 控制 | `rules.py:42-62` | HIGH |
| H4 | Subagent 工具过滤依赖 workspace | `subagent_permissions.py:22-31` | HIGH |
| H5 | Project-scope MCP 安装无审批 | `mcp_self_service.py:63-74` | HIGH |
| M6 | symlink 未二次解析 | `rules.py:88-89` | MEDIUM |
| M7 | regex 可能 DoS | `rules.py:264-266` | MEDIUM |

### 架构设计（CRITICAL: 2, HIGH: 3）

| # | 问题 | 位置 | 严重度 |
|---|------|------|--------|
| C3 | TaskOrchestrator 职责越界 | `task_orchestrator.py:111-166` | CRITICAL |
| C4 | 创建新 Orchestrator 而非复用 | `task_orchestrator.py:680-689` | CRITICAL |
| H1 | ContextPipeline._attached_loop 耦合 | `context_pipeline.py:35` | HIGH |
| H2 | ButlerOrchestrator God Object | `orchestrator.py:94-113` | HIGH |
| M3 | execution_context fallback 脆弱 | `execution_context.py:88-95` | MEDIUM |
| M4 | 压缩状态跨调用持久化 | `context_pipeline.py:34-35` | MEDIUM |
| M5 | Lazy Import 散落 | 多处 | MEDIUM |
| H22 | fallback.py 硬编码 provider | `fallback.py:58-61` | HIGH |
| H23 | _ROLE_ALIASES 两处定义 | `model_resolve.py` vs `orchestrator.py` | HIGH |
| H24 | 全局配置单例不感知 env 更新 | `config.py:347-356` | HIGH |

### 工具系统（CRITICAL: 2, HIGH: 4）

| # | 问题 | 位置 | 严重度 |
|---|------|------|--------|
| C5 | _doom_soft_nudged 永久记忆 | `tool_guardrails.py:246-252` | CRITICAL |
| C6 | mcp_install 验证异常未捕获 | `mcp_install.py:138` | CRITICAL |
| H9 | 并行执行前未检查 halt | `tool_batch.py:316-325` | HIGH |
| H10 | 工具名覆盖无警告 | `registry.py:56` | HIGH |
| H11 | symlink 绕过敏感路径检查 | `path_safety.py:340-378` | HIGH |
| H12 | IDEMPOTENT_TOOLS 缺少工具 | `tool_guardrails.py:24-36` | HIGH |
| M1 | logger.debug 静默吞噬异常 | 多处 | MEDIUM |
| M20 | 文件竞争导致使用原始文本 | `tool_result_storage.py:256-258` | MEDIUM |
| M21 | delete_file 未分类为 destructive | `batch_sequence_guard.py:16-21` | MEDIUM |
| M22 | community trust 只警告不阻止 | `install_scan.py:73-75` | MEDIUM |
| M23 | _extract_command_paths 漏路径 | `path_safety.py:268-295` | MEDIUM |

### Gateway 与队列（CRITICAL: 0, HIGH: 4）

| # | 问题 | 位置 | 严重度 |
|---|------|------|--------|
| H13 | enqueue_inbound 全量排序 | `message_queue.py:143-149` | HIGH |
| H14 | 模块级 _LOCK 竞争 | `message_queue.py:36-42` | HIGH |
| H15 | evict_idle 嵌套锁死锁风险 | `session_registry.py:234-276` | HIGH |
| H16 | enforce_lru 锁外执行 | `session_registry.py:69-79` | HIGH |
| M10 | enforce_lru 在 get_or_create 外 | `session_registry.py:69-79` | MEDIUM |
| M11 | reset_all 超时后竞态 | `session_registry.py:197-232` | MEDIUM |
| M12 | _persist_remove 低效 | `message_queue.py:305-324` | MEDIUM |
| M13 | supplementary_reply 静默失败 | `outbound_bridge.py:375-403` | MEDIUM |
| M14 | completion_notify 无事务性 | `completion_notify.py:249-302` | MEDIUM |
| M32 | enforce_lru 非原子操作 | `session_registry.py:268-271` | MEDIUM |
| M34 | _reset_if_still_idle 锁处理脆弱 | `session_registry.py:289-307` | MEDIUM |

### Workflow 系统（CRITICAL: 2, HIGH: 2）

| # | 问题 | 位置 | 严重度 |
|---|------|------|--------|
| C7 | DELEGATE_BLOCKED_TOOLS 不同步 | `policy.py` vs `subagent_permissions.py` | CRITICAL |
| C8 | until_assertion 错误被掩盖 | `task_orchestrator.py:533-556` | CRITICAL |
| H20 | delegate_depth +1 逻辑混乱 | `task_orchestrator.py:159` | HIGH |
| H21 | diff_section 追加超长 | `delegate_job.py:199` | HIGH |
| M8 | rescue_completed 掩盖原始错误 | `task_orchestrator.py:562-612` | MEDIUM |
| M9 | error 合并分号分隔 | `task_orchestrator.py:497` | MEDIUM |

### 记忆系统（CRITICAL: 0, HIGH: 3）

| # | 问题 | 位置 | 严重度 |
|---|------|------|--------|
| H17 | query_decompose rank_score 字段不匹配 | `query_decompose.py:100` | HIGH |
| H18 | observer_queue rollback 乱序 | `observer_queue.py:121-128` | HIGH |
| H19 | observation_store dedupe 无效 | `observation_store.py:75-97` | HIGH |
| M15 | ChromaVectorStore 失败静默 | `vector_store.py:236-244` | MEDIUM |
| M16 | fallback.jsonl 无原子写 | `vector_store.py:164-167` | MEDIUM |
| M17 | _MAX_FACTS_PER_SESSION 截断时机错误 | `fact_extraction.py:51` | MEDIUM |
| M18 | 重复 anchor 插入污染历史 | `post_compact_cleanup.py:165` | MEDIUM |
| M19 | _collect_dev_session_changes 无保护 | `post_compact_cleanup.py:211-268` | MEDIUM |

### 测试质量（CRITICAL: 0, HIGH: 2）

| # | 问题 | 位置 | 严重度 |
|---|------|------|--------|
| H7 | ProjectManager._instance 单例泄露 | `test_gateway_handler.py:27-30` | HIGH |
| H8 | reset_queue 清理不完整 | `test_message_queue.py:25-36` | HIGH |

### Transport 层（CRITICAL: 0, HIGH: 2）

| # | 问题 | 位置 | 严重度 |
|---|------|------|--------|
| H22 | fallback.py 硬编码 provider | `fallback.py:58-61` | HIGH |
| H28 | llm_retry 属性名错误 | `llm_retry.py:176` | HIGH |

### Session 与生命周期（CRITICAL: 1, HIGH: 3）

| # | 问题 | 位置 | 严重度 |
|---|------|------|--------|
| C9 | asyncio.run() 从运行中 loop 调用 | `lifecycle.py:604` | CRITICAL |
| H25 | reset_sessions_for_chat 竞态 | `session_registry.py:165-182` | HIGH |
| H26 | Daemon 线程无 shutdown 协调 | `lifecycle.py:654` | HIGH |
| H27 | _watermark_store 状态污染 | `lifecycle.py:547-552` | HIGH |

---

## 第4轮新增模块分类

### 项目系统（CRITICAL: 3, HIGH: 3）

| # | 问题 | 位置 | 严重度 |
|---|------|------|--------|
| C10 | _scan_projects 符号链接绕过边界 | `manager.py:56-67` | CRITICAL |
| C11 | effective_workspace 可逃逸 | `worktree.py:45-47` | CRITICAL |
| C12 | auto_extract rglob 无限制 | `project_memory.py:540-546` | CRITICAL |
| H29 | create_project 并发竞争 | `manager.py:214-248` | HIGH |
| H30 | get_project_manager 静默失败 | `preflight.py:274-275` | HIGH |
| H31 | auto_extract 目录排除不完整 | `project_memory.py:535` | HIGH |
| M52 | 单例模式非线程安全 | `manager.py:24-30` | MEDIUM |
| M53 | 模糊匹配无提示 | `manager.py:92-95` | MEDIUM |
| M54 | 路径安全检查可绕过 | `preflight.py:106-113` | MEDIUM |
| M55 | _index_project_dir 异常无告警 | `reindex.py:155-167` | MEDIUM |

### Report与后处理（CRITICAL: 0, HIGH: 1）

| # | 问题 | 位置 | 严重度 |
|---|------|------|--------|
| H32 | structured_output 校验失败仍覆盖 | `generator.py:296` | HIGH |
| M37 | JSON提取正则过宽 | `generator.py:151-157` | MEDIUM |
| M38 | 去重逻辑不完整 | `post_session.py:185-190` | MEDIUM |
| M39 | _invoke_llm 异常处理过简 | `post_session.py:206-213` | MEDIUM |
| M40 | process 无超时控制 | `post_session.py:215-260` | MEDIUM |
| M41 | cache_report 静默失败 | `generator.py:619-620` | MEDIUM |

### Hook与回调系统（CRITICAL: 0, HIGH: 4）

| # | 问题 | 位置 | 严重度 |
|---|------|------|--------|
| H33 | on_llm_start 无异常保护 | `llm_retry.py:42-43` | HIGH |
| H34 | 全局_REGISTRY 非线程安全 | `hooks.py:15` | HIGH |
| H35 | shell=False 与 bash 命令语义不匹配 | `runner.py:522-523` | HIGH |
| M42 | HookBus _REGISTRY 竞态 | `hooks.py:15` | MEDIUM |
| M43 | trigger_hooks_mutating 重试逻辑异常 | `hooks.py:64-66` | MEDIUM |
| M44 | 30秒超时硬编码 | `runner.py:530` | MEDIUM |
| M45 | telemetry 双重锁嵌套 | `telemetry.py:32-44` | MEDIUM |
| M46 | child_callbacks 未隔离 | `delegate_context.py:38-47` | MEDIUM |
| M48 | 双重清理不一致 | `telemetry.py:53-66` | MEDIUM |
| M49 | _session_key_from_payload 异常过宽 | `runner.py:60-69` | MEDIUM |

### 循环依赖与边界case（CRITICAL: 1, HIGH: 3）

| # | 问题 | 位置 | 严重度 |
|---|------|------|--------|
| C13 | run_interruptible 线程泄漏 | `interruptible_client.py:46-48` | CRITICAL |
| H36 | ContextPipeline._attached_loop 引用环 | `agent_loop.py:62-63` | HIGH |
| H37 | reset_all 强制清理遗漏 finalization | `session_registry.py:205-215` | HIGH |
| M47 | ProviderHealth 缓存无清理 | `provider_health.py` | MEDIUM |
| M50 | inbound_idempotency 全局锁竞争 | `inbound_idempotency.py:16-18` | MEDIUM |
| M51 | 工具派发闭包捕获可变状态 | `tool_batch.py:115` | MEDIUM |

---

## 修复优先级建议（第4轮更新）

### P0 - 立即修复（影响 correctness）

| # | 问题 | 维度 |
|---|------|------|
| C1 | 环境变量注入绕过Terminal白名单 | 安全 |
| C2 | MCP community env_hints 诱骗凭据 | 安全 |
| C5 | _doom_soft_nudged 永久记忆 | 工具 |
| C7 | DELEGATE_BLOCKED_TOOLS 不同步 | Workflow |
| C9 | asyncio.run() 从运行中 loop 调用 | Session |
| C10 | _scan_projects 符号链接绕过 | 项目 |
| C11 | effective_workspace 可逃逸 | 项目 |
| C12 | auto_extract rglob 无限制 | 项目 |
| C13 | run_interruptible 线程泄漏 | 循环依赖 |

### P1 - 尽快修复（影响 reliability）

| # | 问题 | 维度 |
|---|------|------|
| C3 | TaskOrchestrator 职责越界 | 架构 |
| C4 | 创建新 Orchestrator 而非复用 | 架构 |
| C6 | mcp_install 验证异常未捕获 | 工具 |
| C8 | until_assertion 错误被掩盖 | Workflow |
| H11 | symlink 绕过敏感路径检查 | 安全 |
| H13 | enqueue_inbound 全量排序 | Gateway |
| H15 | evict_idle 嵌套锁死锁 | Gateway |
| H17 | query_decompose 去重失效 | 记忆 |
| H20 | delegate_depth +1 逻辑 | Workflow |
| H25 | reset_sessions_for_chat 竞态 | Session |
| H28 | llm_retry 属性名错误 | Transport |
| H29 | create_project 并发竞争 | 项目 |
| H30 | get_project_manager 静默失败 | 项目 |
| H33 | on_llm_start 无异常保护 | Hook |
| H34 | 全局_REGISTRY 非线程安全 | Hook |
| H36 | ContextPipeline 引用环 | 循环依赖 |

### 循环依赖与边界case（CRITICAL: 1, HIGH: 3）

| # | 问题 | 位置 | 严重度 |
|---|------|------|--------|
| C13 | run_interruptible 线程泄漏 | `interruptible_client.py:46-48` | CRITICAL |
| H36 | ContextPipeline._attached_loop 引用环 | `agent_loop.py:62-63` | HIGH |
| H37 | reset_all 强制清理遗漏 finalization | `session_registry.py:205-215` | HIGH |
| M47 | ProviderHealth 缓存无清理 | `provider_health.py` | MEDIUM |
| M50 | inbound_idempotency 全局锁竞争 | `inbound_idempotency.py:16-18` | MEDIUM |
| M51 | 工具派发闭包捕获可变状态 | `tool_batch.py:115` | MEDIUM |

---

## 第5轮·监控可观测性与日志、测试与冒烟、部署运维、SQLite持久化

### 监控可观测性与日志（CRITICAL: 0, HIGH: 1, MEDIUM: 7, LOW: 2）

**[HIGH] 无分布式 tracing / correlation ID 系统**

- **位置**：全局（message_handler.py → AgentLoop → dispatch_tool → report pipeline）
- **问题**：整个请求生命周期中没有 `trace_id`、`correlation_id` 或 `request_id` 传播。从消息入口到内存层无法用唯一 ID 关联日志，生产环境跨组件调试极其困难。
- **修复**：在 `ButlerMessageHandler` 或 `resolve_session_key` 处生成 correlation ID，通过 `execution_context` 传播，并在日志和诊断输出中包含此 ID。
- **严重程度**：HIGH

---

**[MEDIUM] 日志文件无轮转策略**

- **位置**：`butler/logging_config.py:31`
- **问题**：`logging.basicConfig()` 只配置 stream handler，没有 `RotatingFileHandler` 或 `TimedRotatingFileHandler`。日志文件无限增长。
- **修复**：使用 `logging.handlers.RotatingFileHandler` 配合 `maxBytes` 和 `backupCount`，或 `TimedRotatingFileHandler`。

**[MEDIUM] 无 Prometheus `/metrics` HTTP 端点**

- **位置**：`butler/ops/runtime_metrics.py`
- **问题**：模块内部暴露 `snapshot_global()` 和 `snapshot_session()`，命名遵循 Prometheus 规范，但无 HTTP 端点供外部拉取。负载均衡器和 Prometheus 无法采集。
- **修复**：添加 `GET /metrics` 端点，以 Prometheus  exposition 格式返回 snapshot。

**[MEDIUM] Histogram bucket 太小（64 → 建议 1000+）**

- **位置**：`butler/ops/runtime_metrics.py:14` `_HISTOGRAM_MAXLEN = 64`
- **问题**：对于繁忙的网关，百分位计算（p50、p95）可能基于太少样本而失去统计意义。
- **修复**：增加至 1000+ 或通过环境变量配置。

**[MEDIUM] 无结构化日志（JSON）**

- **位置**：`butler/logging_config.py:12`
- **问题**：`_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"` 为纯文本。对于生产日志聚合（ELK、Loki、Datadog），结构化 JSON 日志是标准。纯文本日志难以解析和大规模搜索。
- **修复**：考虑 `python-json-logger` 或 `structlog`。

**[MEDIUM] 度量存储无 TTL / 自动清理**

- **位置**：`butler/ops/runtime_metrics.py`
- **问题**：`_COUNTERS`、`_GAUGES`、`_HISTOGRAMS` 是全局 dict，无驱逐机制。`reset_session()` 需显式调用才会清理。长期运行后度量字典可能累积无限多的 key。
- **修复**：添加周期性清理或基于 TTL 的驱逐。

**[MEDIUM] 异常被静默吞掉降低可调试性**

- **位置**：`butler/ops/rag_diagnostics.py:26-27, 53-54, 59-60, 65-66, 71-72, 80-81`
- **问题**：所有可选功能导入都包装在 `except Exception as exc: logger.debug(...)` 中。当功能开关打开但底层配置损坏时，用户在诊断中看不到任何输出。
- **修复**：至少在 WARNING 级别记录，或在部分诊断失败时输出"diagnostics partial"标志。

**[LOW] 阈值硬编码在健康报告中**

- **位置**：`butler/ops/health_report.py:180`
- **问题**：`stale_lines.append(f"委派 stale: {len(stale)}（>阈值未结束）")` — 阈值被引用但从不显示。用户无法知道当前值是否合适。
- **修复**：在输出中包含实际阈值。

**[LOW] 异常吞掉还出现在多个工具模块**

- **位置**：`butler/ops/rag_diagnostics.py:26, 54, 60, 66, 72, 81`
- **问题**：6 处 `except Exception as exc: logger.debug(...)`，DEBUG 级别无法在生产环境帮助调试。
- **修复**：改用 `logger.warning()` 并在输出中注明"部分诊断不可用"。

---

### SQLite与持久化（CRITICAL: 0, HIGH: 1, MEDIUM: 4, LOW: 1）

**[HIGH] `index_triplets_for_content` 每次创建新 TripletIndex 实例**

- **位置**：`butler/memory/semantic_index.py:401-407`
- **问题**：每次调用都创建新的 `TripletIndex(semantic.db_path)`，触发完整的 `_init_schema()` → 获取锁 → 创建新连接 → 执行 CREATE TABLE/INDEX → 关闭连接。`SemanticMemoryIndex` 和 `TripletIndex` 共享同一 DB 文件但各有独立 RLock，无法协调，存在死锁风险。`ExperienceStore.add()` → `index_experience_row()` → `index_triplets_for_content()` 每插入一条经验都重复此操作。
- **修复**：复用 `SemanticMemoryIndex` 持有的 `TripletIndex` 实例，或传入共享的 lock。
- **严重程度**：HIGH

---

**[MEDIUM] diagnostics.py 直接连接无锁、无 WAL**

- **位置**：`butler/memory/diagnostics.py:38`
- **问题**：`_experience_category_counts` 直接 `sqlite3.connect()` 没有 `check_same_thread=False`、没有 `PRAGMA journal_mode=WAL`、也没有锁保护。与其他 store 的连接模式不一致。
- **修复**：统一使用 `check_same_thread=False` + WAL，或至少添加注释说明为何例外。

**[MEDIUM] 所有 store 使用"每操作新连接"模式**

- **位置**：`butler/memory/observation_store.py:27-31`, `butler_memory.py:145-148`, `semantic_index.py:38-41`, `triplets.py:53-56`, `knowledge_db.py:22-25`
- **问题**：每次操作都调用 `self._connect()` 创建新连接，携带 `check_same_thread=False` + WAL。在高频调用场景下连接创建/销毁开销大，WAL mode 每次重新设置。
- **修复**：考虑连接复用或连接池（虽然 sqlite3 连接本身是进程内轻量对象，此问题优先级较低）。

**[MEDIUM] 两个独立 RLock 保护同一 DB 文件**

- **位置**：`butler/memory/semantic_index.py` 和 `butler/memory/triplets.py`
- **问题**：`SemanticMemoryIndex` 和 `TripletIndex` 共享同一个 `db_path`，但各有独立的 `self._lock = threading.RLock()`。两个 RLock 之间无法协调。
- **修复**：统一锁或通过单一入口协调访问。

**[MEDIUM] Migration 无原子性保证**

- **位置**：`butler/memory/observation_store.py:63-104`
- **问题**：`_migrate_schema_locked` 使用 `conn.executescript()` 执行多语句（DELETE + DROP INDEX + CREATE UNIQUE INDEX），SQLite DDL 隐式提交，无事务包装。中途失败会导致部分更改持久化。
- **修复**：用 `BEGIN TRANSACTION` 包装 migration。

**[MEDIUM] _ensure_experience_columns 未处理 column 已存在的情况**

- **位置**：`butler/memory/butler_memory.py:198-207`
- **问题**：`_ensure_experience_columns` 使用 `ALTER TABLE experiences ADD COLUMN` 添加缺失 column，但如果 column 已存在，SQLite 会报错（非 IF NOT EXISTS 模式）。初次创建 v2 schema 后，再次调用 `_init_db` 会崩溃。
- **修复**：添加 `IF NOT EXISTS` 或捕获 `ALTER` 异常。

**[LOW] check_same_thread=False 的必要性存疑**

- **位置**：所有 SQLite store 的 `_connect()` 方法
- **问题**：几乎所有调用都发生在 `with self._lock` 保护的代码路径内。如果确实所有数据库访问都从同一线程发起，`check_same_thread=False` 是不必要的，设为 `True` 更安全。
- **修复**：验证后设置合理的 `check_same_thread`。

---

### 集成测试与冒烟测试（CRITICAL: 0, HIGH: 2, MEDIUM: 7, LOW: 4）

**[HIGH] test_gateway_acceptance.py 缺少 live_llm gate**

- **位置**：`tests/test_gateway_acceptance.py:82-221`
- **问题**：`TestManualGuide34Dialog` 和 `TestManualGuide35Slash` 类标记为 `@pytest.mark.integration`，但没有 `live_llm` gate。如果这些测试调用真实 LLM 路径，会在 CI 中失败或产生副作用。
- **修复**：添加 `@pytest.mark.no_live` 或确认 mock 完整覆盖了 LLM 路径。
- **严重程度**：HIGH

**[HIGH] test_wechat_ilink_outbound.py 缺少真实 HTTP 响应码测试**

- **位置**：`tests/test_wechat_ilink_outbound.py:63-69`
- **问题**：使用 `SESSION_EXPIRED_ERRCODE` mock 返回值，但没有验证：真实 iLink API 返回非零 errcode 时的重试逻辑、网络超时场景的处理、限流（429）场景的处理。
- **修复**：添加对应场景的 mock 或使用 replay 模式。
- **严重程度**：HIGH

---

**[MEDIUM] test_gateway_acceptance.py (795行) 超过单文件 800 行限制**

- **位置**：`tests/test_gateway_acceptance.py`
- **问题**：根据 `rules/common/coding-style.md`，文件应保持在 800 行以内。此文件应按功能拆分。
- **修复**：拆分为 `test_gateway_acceptance_dialog.py`、`test_gateway_acceptance_slash.py`、`test_gateway_acceptance_delegate.py`。

**[MEDIUM] test_tools_registry.py (1131行) 严重超标**

- **位置**：`tests/test_tools_registry.py`
- **问题**：应拆分为多个模块：`test_tools_registry_core.py`、`test_tools_registry_permissions.py`、`test_tools_registry_audit.py`。
- **修复**：按功能拆分。

**[MEDIUM] butler-pre-release-smoke.sh step 9 缺乏前置检查**

- **位置**：`scripts/butler-pre-release-smoke.sh:49-50`
- **问题**：调用 `butler-demo-pilot-smoke.sh` 但没有检查其执行结果是否有效（项目存在、配置正确）。DemoPilot 项目配置损坏时冒烟仍会通过。
- **修复**：检查 DemoPilot 项目存在性和配置有效性。

**[MEDIUM] butler-runtime-smoke.sh 缺少超时保护**

- **位置**：`scripts/butler-runtime-smoke.sh:38`
- **问题**：执行 `runtime run` 命令时没有超时限制。如果 runtime job 挂起，smoke 脚本会无限期阻塞。
- **修复**：添加 `timeout` 包装。

**[MEDIUM] test_e2e.py E2E 测试数量极少**

- **位置**：`tests/test_e2e.py`
- **问题**：整个项目只有 3 个 `@pytest.mark.e2e` 测试，缺少：完整的 WeChat 消息流 E2E、多项目 session 隔离 E2E、runtime job E2E。
- **修复**：补充关键路径 E2E 测试。

**[MEDIUM] conversational tests 缺少失败场景 E2E**

- **位置**：`tests/conversational/`
- **问题**：测试主要覆盖正常对话流程，缺少：LLM API 超时/失败时的降级处理、工具执行失败时的错误回复、session 过期时的恢复流程。
- **修复**：补充失败场景测试。

**[MEDIUM] tmp_butler_home fixture 使用率分散**

- **位置**：97 个测试文件
- **问题**：部分测试直接使用 `tmp_path` 而非 `tmp_butler_home`，部分 `monkeypatch.setenv("BUTLER_HOME", ...)` 可能覆盖不完全。
- **修复**：创建统一覆盖率检查脚本，验证所有涉及文件系统的测试都使用隔离的 BUTLER_HOME。

**[MEDIUM] 部分 autouse fixture 未在顶层 conftest**

- **位置**：`tests/test_dev_tools_integration.py:14`, `tests/test_orchestration_improvements.py:17`, `tests/test_contacts.py:28`
- **问题**：独立 autouse fixture 导致隔离逻辑分散。
- **修复**：统一到 `tests/conftest.py`。

**[LOW] wechat gateway live smoke 测试标记不一致**

- **位置**：`tests/test_wechat_gateway_live_smoke.py` vs `tests/test_gateway_acceptance.py`
- **问题**：`test_wechat_gateway_live_smoke.py` 有正确的 `pytestmark = pytest.mark.live_llm`，但 `test_gateway_acceptance.py` 的部分测试没有相同标记。
- **修复**：统一标记规范。

**[LOW] project-health-check.sh lint 检查范围过窄**

- **位置**：`scripts/project-health-check.sh:17-24`
- **问题**：只检查 E/F 类 ruff 错误，不检查 W（warnings）或 I（imports）。
- **修复**：添加 `--select E,F,W`。

**[LOW] butler-runtime-smoke.sh 使用 systemctl 而非 butler CLI 检查 timer**

- **位置**：`scripts/butler-runtime-smoke.sh:73`
- **问题**：`systemctl --user list-timers` 而非 `butler runtime timer-status`。
- **修复**：使用 butler CLI 保持一致性。

---

### 部署与运维脚本（CRITICAL: 2, HIGH: 3, MEDIUM: 5, LOW: 5）

**[CRITICAL] 备份脚本排除 .env，但恢复脚本无 .env 迁移机制**

- **位置**：`scripts/backup-butler-data.sh:119`
- **问题**：备份不包含 `.env` 文件（含 API keys），但 `restore-butler-data.sh` 没有任何 .env 恢复或引导机制。完整备份/恢复后 gateway 将因缺少 API keys 无法启动。
- **修复**：在备份/恢复流程中提供 .env 的处理逻辑，或在恢复后引导用户检查 .env 配置。
- **严重程度**：CRITICAL

**[CRITICAL] restore-butler-data.sh 恢复后未验证服务可运行性**

- **位置**：`scripts/restore-butler-data.sh:87-106`
- **问题**：恢复后只验证文件是否存在，不验证 API keys 是否存在、`butler doctor` 是否通过、服务是否能正常启动。用户可能以为恢复成功但服务实际无法启动。
- **修复**：恢复完成后执行 `butler doctor` 或提示用户运行验证命令。
- **严重程度**：CRITICAL

---

**[HIGH] status 命令的进程检测不可靠**

- **位置**：`scripts/butler-gateway-ops.sh:35`
- **问题**：`pgrep -af 'butler.main gateway'` 可能误匹配其他进程，且进程名细微变化会漏检。应该直接查询 systemd 服务状态。
- **修复**：使用 `systemctl --user is-active butler-gateway.service`。

**[HIGH] _cmd_restart() 的等待时间过短**

- **位置**：`scripts/butler-gateway-ops.sh:47`
- **问题**：`sleep 1` 只有 1 秒，对于需要初始化 LLM 连接的 Python 服务远远不够。服务可能已正常启动但 1 秒后检查显示错误。
- **修复**：使用循环检测服务状态，确认后再报告。

**[HIGH] _cmd_upgrade() 的 git pull 可能静默失败**

- **位置**：`scripts/butler-gateway-ops.sh:85-89`
- **问题**：`git pull --ff-only` 在本地有未 push commits、分支 divergence 或未 commit 修改时会失败，但脚本不会停止，继续执行 install 可能导致不一致状态。
- **修复**：检查 git pull 返回值，失败时退出或提示用户。

---

**[MEDIUM] butler-gateway-ops.sh 升级后不验证服务健康**

- **位置**：`scripts/butler-gateway-ops.sh:75-96`
- **问题**：`upgrade` 执行 `git pull` → `install` → `restart` 后，不验证服务是否正常运行。
- **修复**：升级后调用 `_cmd_status` 或等待服务启动后验证其处于 active 状态。

**[MEDIUM] backup-butler-data.sh 未备份 outbox/pending（飞行中消息）**

- **位置**：`scripts/backup-butler-data.sh:63`
- **问题**：`gateway/outbox/pending/` 中的消息在备份期间可能正在被处理，备份可能包含不一致状态。
- **修复**：备份前先暂停服务（`systemctl --user stop`），或使用应用级 snapshot 机制。

**[MEDIUM] 日志轮转配置硬编码 /home/ailearn 路径**

- **位置**：`scripts/logrotate/butler-gateway.conf:2`
- **问题**：路径硬编码。虽然 `install-butler-logrotate.sh` 用 sed 替换了安装时的路径，但模板文件本身的路径会误导阅读代码的人。
- **修复**：使用占位符如 `@WFXM_ROOT@` 保持与其他 systemd 模板一致。

**[MEDIUM] backup-butler-data.sh tar.gz 与 rsync 模式排除规则不一致**

- **位置**：`scripts/backup-butler-data.sh:76-96`
- **问题**：tar.gz 模式使用 `"${EXCLUDES[@]}"` 传递，rsync 模式没有排除 `tenants` 目录。两种模式排除规则应保持一致。
- **修复**：统一排除规则。

**[MEDIUM] install-butler-gateway-service.sh 模板注释包含硬编码路径**

- **位置**：`scripts/systemd/butler-gateway.service:1-9`
- **问题**：注释中硬编码 `$HOME/projects/WFXM` 而非使用 `@WFXM_ROOT@`，误导阅读。
- **修复**：注释也使用占位符。

**[LOW] systemd 服务缺少资源限制**

- **位置**：`scripts/systemd/butler-gateway.service`
- **问题**：服务没有设置 `MemoryMax`、`CPUQuota` 等资源限制。有 bug 的工具调用可能导致内存泄漏或 CPU 占用过高。
- **修复**：添加 `MemoryMax=2G`、`CPUQuota=200%`。

**[LOW] install-butler-gateway-service.sh 未检查 python3 版本**

- **位置**：`scripts/install-butler-gateway-service.sh`
- **问题**：`pyproject.toml` 要求 `requires-python = ">=3.11"`，但安装脚本只检查 python3 是否存在，不检查版本。如果系统只有 Python 3.10，服务安装后会无法运行。
- **修复**：添加 Python 版本检查。

**[LOW] preflight 对 WECHAT_DM_POLICY=open 只警告不阻止**

- **位置**：`scripts/lib/butler-gateway-preflight.sh:94-95`
- **问题**：P0 安全配置但 preflight 不会因此失败。不安全配置可能被部署。
- **修复**：某些关键安全配置应导致 preflight 失败。

**[LOW] restore-butler-data.sh 安全备份可能失败**

- **位置**：`scripts/restore-butler-data.sh:64-66`
- **问题**：如果 BUTLER_HOME 是 symlink 或有特殊权限，备份可能失败但脚本可能不提示。磁盘空间不足时备份可能部分写入。
- **修复**：添加备份验证和磁盘空间检查。

---

## 第6轮·CLI配置系统、多Agent协作、Session队列、Skill系统

### CLI与配置系统（CRITICAL: 0, HIGH: 1, MEDIUM: 7, LOW: 3）

**[HIGH] 启动时无必填参数校验**

- **位置**：`main.py:505-508`
- **问题**：`ButlerOrchestrator` 启动时无 API key 存在性检查，用户得到模糊错误而非友好提示。
- **修复**：在 `_cmd_chat` 或 `ButlerOrchestrator.__init__` 中添加启动校验。
- **严重程度**：HIGH

---

**[MEDIUM] Secrets 文件写入非原子操作**

- **位置**：`config_secrets.py:108-112`
- **问题**：直接 `write_text` 而非原子 rename。写入时崩溃会导致 secrets.yaml 损坏。
- **修复**：先写临时文件，flush 后 rename，再 chmod。

**[MEDIUM] secrets.yaml 加载失败静默**

- **位置**：`config.py:338-343`
- **问题**：secrets.yaml 损坏时系统静默继续，用户不收到警告。
- **修复**：改为 `logger.warning`，或在 doctor 中检测。

**[MEDIUM] dotenv 未指定路径**

- **位置**：`config.py:21`
- **问题**：`load_dotenv()` 不带参数时只从当前工作目录查找 `.env`。从非项目根目录启动会找不到环境变量。
- **修复**：指定 `dotenv_path` 或使用项目根目录。

**[MEDIUM] BUTLER_TENANT 环境变量未被读取**

- **位置**：`config.py:185` + `tenant.py:45-54`
- **问题**：`ButlerSettings.load()` 未从 `BUTLER_TENANT` 环境变量初始化 `default_tenant`。
- **修复**：在 `__post_init__` 中加入 `self.default_tenant = os.getenv("BUTLER_TENANT", ...)`

**[MEDIUM] secrets.yaml 权限检查不完整**

- **位置**：`config_secrets.py:31-42`
- **问题**：首次写入时权限取决于 umask，不是 0600。
- **修复**：写入后立即 chmod。

**[MEDIUM] save_butler_config 只保留两个 key**

- **位置**：`config.py:280-287`
- **问题**：用户添加的其他顶层 key（如 `default_tenant`）保存时会丢失。
- **修复**：改为保留所有非敏感顶层 key。

**[MEDIUM] provider_secrets fallback 行为混乱**

- **位置**：`config_secrets.py:90`
- **问题**：env 设置空字符串时覆盖 secrets.yaml，可能非用户期望。
- **修复**：明确区分"未设置"和"空字符串"。

**[LOW] config.yaml 权限未校验**

- **位置**：`config.py:276-301`
- **问题**：config.yaml 可能包含敏感配置但无权限保护。
- **修复**：添加 chmod 600 检查。

**[LOW] 租户 ID 校验允许 `..`**

- **位置**：`tenant.py:18`
- **问题**：`_TENANT_RE` 允许 `..` 和 `.-`，可能导致路径遍历。
- **修复**：收紧校验规则。

**[LOW] 无 Provider 可用时错误信息不友好**

- **位置**：`config.py:239-243`
- **问题**：providers 全部为空时，用户看到 LLM 调用失败而非明确提示。
- **修复**：添加明确的"无可用 Provider"提示。

---

### 多Agent协作与通信（CRITICAL: 1, HIGH: 1, MEDIUM: 1, LOW: 1）

**[CRITICAL] `asyncio.to_thread` 导致父状态丢失**

- **位置**：`butler/core/delegate_context.py:11-35` + `task_orchestrator.py:211-217`
- **问题**：`threading.local()` 存储父状态，但 `asyncio.to_thread` 创建的新线程有空的 `threading.local()`。父的 callbacks、system_prompt、messages 对子 agent 都不可见。
- **影响**：所有并行 DAG workflow（`spawn_parallel` 等）的子 agent 得到空父状态，`cache_safe_delegate` 功能失效。
- **修复**：将 `threading.local()` 改为 `contextvars.ContextVar`，并使用 `contextvars.copy_context()` 调用线程。
- **严重程度**：CRITICAL

---

**[HIGH] Semaphore slots 直到所有任务完成才释放**

- **位置**：`task_orchestrator.py:449-455`
- **问题**：`asyncio.gather` 中如果一个任务挂起，它的 semaphore slot 永远不会释放，直到 gather 返回。
- **修复**：添加 per-task 超时或 `asyncio.Task` 取消机制。
- **严重程度**：HIGH

---

**[MEDIUM] 空 session key 归一化为共享 `"default"` bucket**

- **位置**：`delegate_context.py:27-28`
- **问题**：空 session key 的所有 delegate 共享同一并发 bucket。
- **修复**：添加 session key 有效性校验。

**[LOW] cache_safe_delegate shared prefix 被截断无警告**

- **位置**：`cache_safe_delegate.py:70-72`
- **问题**：父 system prompt 超过 4096 字符时只共享前 4096 字符，子 agent 用不完整上下文做决策。
- **修复**：添加截断诊断标志。

---

### Session与消息队列（CRITICAL: 0, HIGH: 4, MEDIUM: 9, LOW: 4）

**[HIGH] `reset_all` 在锁外清除状态存在竞态**

- **位置**：`session_registry.py:214-221`
- **问题**：`reset_all` 在 `_lock` 外的 `self._active_sessions.clear()` 等操作与 `get_or_create`、`session_lock` 等并发调用产生竞态，导致 KeyError 或创建后立即放弃的 loop。
- **严重程度**：HIGH

**[HIGH] `complete_inbound` 从不清理 "done" 条目**

- **位置**：`inbound_idempotency.py:90-101`
- **问题**：`_prune_session` 只在 `len(bucket) > _MAX_IDS_PER_SESSION` 时清理，但完成的 external_id 永远留在 dict 中。高流量 session 下内存无限增长。
- **严重程度**：HIGH

**[HIGH] in-flight 条目无时间过期**

- **位置**：`inbound_idempotency.py:18, 43-45`
- **问题**：如果 `inflight` 请求挂起（永不调用 `complete_inbound`），该 external_id 永远阻止后续重复消息。崩溃进程的 inflight 条目永久阻塞重试。
- **严重程度**：HIGH

**[HIGH] `_persist_remove` 在并发写入下不安全**

- **位置**：`message_queue.py:315`
- **问题**：读-过滤-写回操作在并发 `_persist_remove` 调用或 `enqueue_inbound` 追加时可能丢失行，导致恢复后 JSONL 损坏。
- **严重程度**：HIGH

---

**[MEDIUM] `set_evict_notify_hook` 中 hook 抛出的非 Exception 会崩溃 eviction 线程**

- **位置**：`session_registry.py:248-253`
- **问题**：`except Exception` 捕获不了 `SystemExit`、`KeyboardInterrupt`，会直接崩溃 eviction 线程。

**[MEDIUM] `_finalize_loop` 在锁释放后调用**

- **位置**：`session_registry.py:289-306`
- **问题**：如果另一个线程在 finalize 完成前创建同名 session，新 loop 可能被立即清理。

**[MEDIUM] `restore_persisted_queue` 不验证 priority 值**

- **位置**：`message_queue.py:363-378`
- **问题**：持久化的 JSONL 中 malformed priority 导致项静默排序到最低优先级。

**[MEDIUM] `restore_persisted_queue` 不恢复 `_DROP_SUMMARIES`**

- **位置**：`message_queue.py:345-390`
- **问题**：drop-summarize 事件预览在重启后永久丢失。

**[MEDIUM] `_should_dedupe` 2秒窗口可能漏掉重复**

- **位置**：`message_queue.py:38, 59-66`
- **问题**：2 秒内相同文本的消息第二个会被接受，dedupe 返回 False 后静默丢弃。

**[MEDIUM] Durable outbox 状态转换+trim 非原子**

- **位置**：`durable_outbox.py:75-95`
- **问题**：进程崩溃在 `pending.replace(target)` 后、`_trim_state_dir` 完成前，sent/ 目录无限积累。

**[MEDIUM] `_transition_outbox_entry` 无锁**

- **位置**：`durable_outbox.py:75-96`
- **问题**：并发 `mark_outbox_sent` 相同 entry_id 时，后赢的写入会丢失前一个的增量。

**[MEDIUM] LobeHub search 重复 CLI 调用**

- **位置**：`lobehub.py:256-262`
- **问题**：当 `prefer_cli` 为真且 CLI 返回空时，仍在末尾重试 CLI，造成不必要开销。

**[LOW] `enqueue_inbound` 每次重新排序**

- **位置**：`message_queue.py:143-149`
- **问题**：每次入队都 O(n log n) 全量排序，效率低。

**[LOW] `/queue reset` 命令丢弃有效选项**

- **位置**：`queue_settings.py:182-183`
- **问题**：`/queue reset cap:5` 返回 `("reset", {"cap": 5}, None)` 但 `apply_queue_command` 忽略 opts。

**[LOW] outbox_counts 和 list_pending_outbox 全目录扫描**

- **位置**：`durable_outbox.py:107-139`
- **问题**：O(n) 扫描无缓存，高负载时可能引发延迟尖刺。

---

### Skill系统（CRITICAL: 0, HIGH: 1, MEDIUM: 5, LOW: 4）

**[HIGH] `BUTLER_SKILL_TRUSTED_REPOS` 可被环境变量注入绕过**

- **位置**：`butler/registry/skill_sources/github.py:106-112`
- **问题**：`BUTLER_SKILL_TRUSTED_REPOS` 是纯环境变量，攻击者获得环境写权限后可添加恶意 repo 为"trusted"。无密码学 repo 所有权验证。
- **严重程度**：HIGH

---

**[MEDIUM] 内容哈希校验被静默跳过**

- **位置**：`butler/registry/install_scan.py:129-131`
- **问题**：community skill 的 `hit.extra.content_hash` 为空时校验静默跳过，无警告日志。

**[MEDIUM] upgrade 失败无回滚**

- **位置**：`skill_service.py:258-278`
- **问题**：lock 文件先于技能验证更新，write 失败后系统处于不一致状态。

**[MEDIUM] install_pre_scan_fail_closed 承诺不可靠**

- **位置**：`skill_service.py:239-242`
- **问题**：宽 try/except 静默吞掉错误，"fail closed" 承诺无法兑现。

**[MEDIUM] URL safety DNS 解析无缓存**

- **位置**：`url_safety.py:62-69`
- **问题**：每次 URL 验证都调用 `socket.getaddrinfo()`，无缓存。DNS rebinding 攻击风险。

**[MEDIUM] BundledSource trust 默认值问题**

- **位置**：`bundled.py:58`
- **问题**：缺失 trust 值默认为 "builtin"（最高权限），如果索引文件损坏或篡改，危险。

**[LOW] SkillManager.get_skill() 过滤逻辑**

- **位置**：`manager.py:328`
- **问题**：按前缀过滤可能意外暴露内部 key。

**[LOW] ClawHub 硬编码 "community" trust**

- **位置**：`clawhub.py:122`
- **问题**：即使通过安全扫描，trust 仍是 "community"，限制信任路由效用。

**[LOW] GitHub search 返回不存在 repo 的命中**

- **位置**：`github.py:49-69`
- **问题**：search 对任何 `owner/repo` 查询字符串返回命中，即使该路径无 skill。误导用户。

**[LOW] Hub skills 无版本锁定**

- **位置**：`clawhub.py:174-191`
- **问题**：无机制锁定特定版本或回滚到前一版本。

---

## 第7轮·Report系统、Memory系统、Runtime工作流、安全防护

### Report生成与输出系统（CRITICAL: 0, HIGH: 2, MEDIUM: 12, LOW: 3）

**[HIGH] JSON提取正则无法处理嵌套花括号**

- **位置**：`generator.py:151`
- **问题**：`re.finditer(r"\{[^{}]*\}", blob)` 字符类排除 `{` 和 `}`，无法匹配嵌套 JSON。`{"outer": {"inner": "value"}}` 只匹配到 `{"outer": `。
- **影响**：工作流输出嵌套 JSON 时，`parse_structured_output` 会失败，`validate_structured_output` 报错"missing required field"但 JSON 实则存在。
- **修复**：使用递归正则或 `json.JSONDecodeError` catch-and-retry。

**[HIGH] `transcript_enabled()` 在工作完成后才检查**

- **位置**：`transcript_export.py:208`
- **问题**：函数先构建完整 markdown（加载行、构建 markdown），然后才检查 `transcript_enabled()` 返回错误。如果功能被禁用，所有处理都浪费。
- **修复**：在函数开头检查 `transcript_enabled()`。

---

**[MEDIUM] Pydantic 验证异常被静默吞掉**

- **位置**：`generator.py:259-260`
- **问题**：`except ImportError: pass` 时 Pydantic 不可用，系统静默降级，用户得不到反馈。

**[MEDIUM] Schema repair 循环遇异常不传播错误**

- **位置**：`generator.py:395-396`
- **问题**：异常被字符串化追加到 issues，但底层原因丢失，开发者无法区分验证错误和系统错误。

**[MEDIUM] `_schema_validation_failed` 混淆 schema 错误与一般问题**

- **位置**：`generator.py:305-310`
- **问题**：函数含义依赖 `structured_output` 是否存在，语义不清。

**[MEDIUM] 12000 字符截断可能丢失修复所需上下文**

- **位置**：`generator.py:360`
- **问题**：复杂输出包含多字段时，相关结构化数据可能超过 12000 字符限制。

**[MEDIUM] PII scrub 在长度检查前应用**

- **位置**：`completion_notify.py:280` + `outbound_bridge.py:415-418`
- **问题**：先 scrub 后截断，如果 scrub 扩展文本（如 `id: 123456` → `id: ****`），最终文本可能超过 4000 字符。

**[MEDIUM] 诊断输出语言混用**

- **位置**：`completion_notify.py:80-94`
- **问题**：`"完成提醒:开"` + `"委派推:关"` 混用中英文。

**[MEDIUM] `transcript_enabled` 检查浪费计算**

- **位置**：`transcript_export.py:208`
- **问题**：见 HIGH。

**[MEDIUM] `_format_row_markdown` 对未知类型回退到原始 JSON dump**

- **位置**：`transcript_export.py:118-125`
- **问题**：未知事件类型暴露内部字段（如 `tool_call_id`、`session_key`），可能包含敏感信息。

**[MEDIUM] `_tombstone_tail` 全程持锁**

- **位置**：`session_transcript.py:49-60`
- **问题**：大 session 下写操作持锁时间过长。

**[MEDIUM] `_append_line` stat 调用在锁外创建 TOCTOU 竞态**

- **位置**：`session_transcript.py:50-60`
- **问题**：`offset = path.stat().st_size` 在锁外，`path.open("a")` 在锁内，另一线程可能在期间截断文件。

**[MEDIUM] `schedule_completion_push` 错误使用 `run_coroutine_threadsafe`**

- **位置**：`outbound_bridge.py:444`
- **问题**：fire-and-forget 语义，但如果 loop 已关闭或 future 抛异常，调用方得到 `True` 不知道推送是否真正启动。

**[LOW] `cache_report` 静默忽略持久化错误**

- **位置**：`generator.py:619-620`
- **问题**：持久化失败只打 debug 日志，无遥测计数。

**[LOW] `format_for_wechat` 硬编码中文文本**

- **位置**：`generator.py:496`
- **问题**：将 WeChat 命令界面耦合到报告格式化器，非 WeChat 平台时文本无关。

---

### Memory系统（CRITICAL: 1, HIGH: 2, MEDIUM: 10, LOW: 3）

**[CRITICAL] InMemoryVectorStore 重启后向量数据丢失**

- **位置**：`vector_store.py:152-167`
- **问题**：`_load_persisted()` 只加载 `id`，不加载 `embedding` 字段。重启后所有相似度计算返回 0 或错误。
- **影响**：ChromaDB 不可用时，内存向量存储实际无法正常工作。
- **严重程度**：CRITICAL

---

**[HIGH] 长期 experience 条目无淘汰机制**

- **位置**：`butler_memory.py:375-388`
- **问题**：`prune_conversation_older_than` 只清理 `category='conversation'` 的临时会话。长期 experience（`category != 'conversation'`）的 `access_count` 和 `last_accessed_at` 被追踪但从未用于淘汰。数据库只增不减。
- **严重程度**：HIGH

**[HIGH] hybrid_search dedup key 跨项目冲突**

- **位置**：`semantic_index.py:240-256, 350-355`
- **问题**：`_hit_key(hit)` 使用 `source:source_id` 作为去重键，不含 `project`。同一 `source:source_id`（如 `experience:42`）在不同项目下被错误去重。
- **严重程度**：HIGH

---

**[MEDIUM] record_access 逐条 UPDATE 事务效率低**

- **位置**：`butler_memory.py:209-225`
- **问题**：循环内逐条执行 UPDATE，应改为单条批量 UPDATE。

**[MEDIUM] RRF 融合常数 k=60 不可配置**

- **位置**：`semantic_index.py:245, 252`
- **问题**：`vec_weight / (60 + rank + 1)` 硬编码，无法通过环境变量调整向量与 FTS 融合强度。

**[MEDIUM] search 方法 project 过滤逻辑模糊**

- **位置**：`semantic_index.py:170`
- **问题**：`WHERE project = ? OR project = ''` 同时匹配指定项目和全局条目（`project=''`）。

**[MEDIUM] 衰减因子对负年龄返回 > 1.0**

- **位置**：`retrieval_ranking.py:25-28`
- **问题**：`age_days < 0` 时返回 `exp(正数) > 1.0`，导致未来日期条目排名更高。

**[MEDIUM] access_boost_factor 无上界**

- **位置**：`retrieval_ranking.py:31-32`
- **问题**：log1p 增长缓慢但无上界，对极高频条目仍有一定放大作用。

**[MEDIUM] 半衰期只影响排名不淘汰条目**

- **位置**：`retrieval_ranking.py:11-15`
- **问题**：`memory_half_life_days()` 只用于运行时衰减计算，不删除数据库中旧条目。

**[MEDIUM] schedule_prefetch_warm 后台任务无结果保障**

- **位置**：`prefetch_cache.py:76-98`
- **问题**：`daemon=True` 的线程不阻止进程退出，缓存未完成时主线程可能跳过结果。

**[MEDIUM] facade.prefetch 对 linked orchestrator 路径冗余调用**

- **位置**：`facade.py:236-243`
- **问题**：对 linked orchestrator 路径强制 `use_cache=False`，而 `queue_prefetch_after_turn` 已触发预取并写入缓存，导致永远不会命中缓存。

**[MEDIUM] hybrid_experience_search 单 try 块无隔离错误处理**

- **位置**：`session/lifecycle.py:163-177`
- **问题**：semantic index 查询失败时整个 experience 搜索回退到空结果，而非降级到纯 FTS。

**[MEDIUM] 不支持多角色批量预取**

- **位置**：`session/lifecycle.py:120-324`
- **问题**：无批量预取 API，无法在用户交互前并行预热多角色缓存。

**[LOW] text_hash 计算后未使用**

- **位置**：`vector_store.py:81`
- **问题**：死代码。

**[LOW] fetch_by_ids 排序不符合预期**

- **位置**：`butler_memory.py:403`
- **问题**：`ORDER BY created_at DESC` 丢弃调用方传入的 `row_ids` 顺序。

**[LOW] cache key 32位哈希碰撞概率**

- **位置**：相关模块
- **问题**：32 位哈希存在碰撞风险，尤其在高基数数据集上。

---

### Runtime工作流与定时任务（CRITICAL: 2, HIGH: 3, MEDIUM: 4, LOW: 3）

**[CRITICAL] Rescue后继节点被错误取消**

- **位置**：`task_orchestrator.py:473-482`
- **问题**：router 返回非直接依赖节点时只取消直接依赖，间接依赖的非直接子节点不会被取消，导致 DAG 状态不一致。A → B → C 依赖链，router 返回 C 作为 next_id，但 B 不会被取消。
- **严重程度**：CRITICAL

**[CRITICAL] 连击告警逻辑缺陷 - streak>threshold 时不告警**

- **位置**：`runtime/failure_tracker.py:86`
- **问题**：`if streak >= threshold and streak == threshold:` 等价于 `streak == threshold`。threshold=3 时，连续失败 4 次不告警（因为 4 != 3）。
- **修复**：应为 `streak >= threshold` 或拆分逻辑。
- **严重程度**：CRITICAL

---

**[HIGH] Replan循环篡改共享节点状态**

- **位置**：`workflows/runner.py:60-66`
- **问题**：`impl_node.config.task` 在循环内被直接修改，如果 replan 提前退出或后续复用该 node，会导致任务内容错误。
- **修复**：应使用临时变量或循环结束后恢复原始 task。
- **严重程度**：HIGH

**[HIGH] Workflow自动继续存在双重执行风险**

- **位置**：`human_gate.py:318-329`
- **问题**：auto-resume 成功后函数仍返回"请再次发送 /workflow"，如果用户恰好又发了 `/workflow` 命令，会导致重复执行。
- **严重程度**：HIGH

**[HIGH] Cron触发窗口过窄 - 90s窗口边缘失败**

- **位置**：`runtime/schedule.py:27-28`
- **问题**：`delta < 90s` 在处理延迟超过 60s 时会漏过触发。`run_due_jobs_all` 串行处理多项目时累积延迟明显。
- **严重程度**：HIGH

---

**[MEDIUM] 锁的 stale 时间过长无心跳**

- **位置**：`runtime/audit.py:56`
- **问题**：`stale_seconds=7200`（2小时）但无心跳机制。进程崩溃须等 2 小时才能重跑。

**[MEDIUM] Rescue成功但 success=False 阻止下游**

- **位置**：`task_orchestrator.py:601-612`
- **问题**：Ansible rescued 语义导致下游节点看到失败跳过执行，有 rescue 的 workflow 无法自动继续。

**[MEDIUM] Stale 任务检测无进程存活验证**

- **位置**：`runtime/task_store.py:48-57`
- **问题**：只检查文件 mtime，不验证进程是否真正存活。

**[MEDIUM] 任务状态文件无原子写入保护**

- **位置**：`runtime/task_store.py:211-214`
- **问题**：直接 `write_text` 而非原子写入，crash 可能产生损坏的 JSON。

**[LOW] Topo sort 空队列 panic**

- **位置**：`task_orchestrator.py:650-651`
- **问题**：空输入时 `len(result) != len(nodes)` 为 0 != 0 不会错，但语义不清。

**[LOW] 审批 gate 过期后删除未清理 approved 记录**

- **位置**：`human_gate.py:131-134`
- **问题**：pending 删除但 approved 不清理。

**[LOW] `run_due_jobs_all` 串行处理无并发**

- **位置**：`runtime/service.py:338-345`
- **问题**：多项目任务串行处理，累积延迟明显。

---

### 安全防护与边界检查（CRITICAL: 1, HIGH: 2, MEDIUM: 3, LOW: 3）

**[CRITICAL] Default-allow tripwire 未真正阻止**

- **位置**：`io_guardrail.py:49-52, 58-61, 70-73`
- **问题**：`BUTLER_IO_GUARDRAIL_BLOCK=False`（默认）时，检测到 secrets/PII 设置 `tripwire=True` 但 `allowed=True`。调用方看到 `allowed=True` 继续执行，消息带着 secret 送入 LLM。只有 `BLOCK=true` 时才真正阻止。
- **修复**：secret 检测应默认 fail-closed，或调用方独立检查 `tripwire`。
- **严重程度**：CRITICAL

---

**[HIGH] 注入模式绕过通过空格变化**

- **位置**：`butler_memory.py:18-21`
- **问题**：`_reject_injection` 模式是简单字面量正则，无法处理常见混淆技术：
  - `ignore   previous`（多个空格）→ 未检测
  - `ignore\nprevious`（换行）→ 未检测
  - `[INST Hello]`（带内容）→ 未检测
- **修复**：匹配前规范化空白/换行，或使用 word boundaries。
- **严重程度**：HIGH

**[HIGH] 工具路径检查静默吞掉异常**

- **位置**：`path_safety.py:123-124`
- **问题**：`except Exception: logger.debug(...)` 吞掉所有异常。如果 `check_external_path_override` 抛异常，合法路径可能被拒绝，或错误信息泄露内部细节。
- **修复**：至少日志 WARNING 级别。
- **严重程度**：HIGH

---

**[MEDIUM] Schema 验证无 pydantic 时 fail open**

- **位置**：`generator.py:259-262`
- **问题**：pydantic 导入失败时 `pass`，但非 pydantic 路径有 enum 检查。实际上可降级，风险较小。

**[MEDIUM] 工具路径解析无 symlink-jailbreak 保护**

- **位置**：`path_safety.py:261-265`
- **问题**：TOCTOU 竞态——检查和使用之间 symlink 可能被修改。无 symlink 循环检测。
- **修复**：使用 `Path.stat(follow_symlinks=False)` 检查文件类型。

**[MEDIUM] Output schema 验证结果不被强制执行**

- **位置**：`meta_flags.py:22-23`
- **问题**：`output_schema_validate_enabled()` 默认 True，但调用方只记录错误到 `report.issues`，不阻止 workflow 继续。

**[MEDIUM] TOCTOU 竞态窗口在 path_safety.py:261-265**

- **位置**：`path_safety.py:261-265`
- **问题**：检查和使用之间 symlink 可能被修改，无 symlink 循环检测。

**[LOW] ID18 正则有边界误报**

- **位置**：`pii_scrub.py:11`
- **问题**：嵌入式长字母数字字符串可能匹配，为 scrubber 设计如此。

**[LOW] Email PII scrub 默认禁用**

- **位置**：`pii_scrub.py:24-30`
- **问题**：`BUTLER_OUTBOUND_PII_SCRUB_EMAIL=1` 默认 "0"，email 是常见 PII。

---

## 第8轮发现（2026-05-28）

### 数据流与事件系统（CRITICAL: 3, HIGH: 3, MEDIUM: 3, LOW: 3）

**[CRITICAL] Ring buffer 线程不安全**

- **位置**：`item_event_sink.py:21-23`
- **问题**：`_recent.append()` 后 `del _recent[0]` 不是原子操作，多线程并发写入会导致数据丢失或 IndexError。
- **修复**：使用 `collections.deque(maxlen=N)` 替代手动 append/pop。

**[CRITICAL] JSON 文件并发写入竞态**

- **位置**：`media_telemetry.py:32-48`
- **问题**：`read_json()` → 修改 → `write_json()` 无锁保护，并发写入会导致数据丢失。
- **修复**：使用文件锁或 `fcntl.flock()` 保护写操作。

**[CRITICAL] Counter 非原子 get-then-set**

- **位置**：`completion_telemetry.py:6-52`
- **问题**：`_COUNTERS[key] = _COUNTERS.get(key, 0) + int(value)` 不是原子操作，高频并发下丢失计数。
- **修复**：使用 `threading.Lock` 包装或 `collections.Counter`。

**[CRITICAL] 运行时指标 Counter 同样竞态**

- **位置**：`ops/runtime_metrics.py:60`
- **问题**：与 completion_telemetry.py 相同模式，`_COUNTERS[key] = _COUNTERS.get(key, 0) + int(value)` 非原子。

**[HIGH] TokenStore 缓存直接 pop 无锁**

- **位置**：`wechat_ilink.py:1412-1414`
- **问题**：`self._token_store._cache.pop(...)` 直接操作私有缓存，无锁保护。

**[HIGH] 锁粒度过粗导致高并发瓶颈**

- **位置**：`reply_admission.py:37-46`
- **问题**：`try_admit()` 使用全局 `threading.RLock()`，高频场景下所有线程串行化。

**[HIGH] 白名单检查每次都解析环境变量**

- **位置**：`bot_loop_guard.py:36-41`
- **问题**：`_is_whitelisted()` 每次调用都 `os.getenv()` + `split()`，高频路径不必要开销。

**[MEDIUM] emit_threadsafe 检查与操作非原子**

- **位置**：`outbound_bridge.py:207-213`
- **问题**：`_closed` 检查和 `call_soon_threadsafe()` 之间存在竞态窗口。

**[MEDIUM] reply_admission 无 TTL 清理机制**

- **位置**：`reply_admission.py:20-21`
- **问题**：`_ACTIVE` 字典无时间基准清理，异常退出后 AdmissionToken 永久留存。

**[MEDIUM] bot_loop_guard 正则匹配性能差**

- **位置**：`bot_loop_guard.py:44-51`
- **问题**：`re.search(r"@\S*bot\S*", text, re.I)` 在高频路径上性能不佳。

**[LOW] MessageDeduplicator 清理效率低**

- **位置**：`helpers.py:33-35`
- **问题**：每次 `is_duplicate` 调用都重建整个字典的过滤副本。

**[LOW] vision_fallback 每次调用都 split 环境变量**

- **位置**：`vision_fallback.py:15-19`
- **问题**：`_fallback_order()` 未缓存，`functools.lru_cache` 可解决。

**[LOW] llm_retry 日志消息误导**

- **位置**：`llm_retry.py:149,160,180,205,255,277,293`
- **问题**：多处 `except` 块日志消息为 `"on delta cb skipped"`，但实际与 delta cb 无关。

---

### 系统初始化与依赖注入（CRITICAL: 1, HIGH: 2, MEDIUM: 5, LOW: 2）

**[CRITICAL] _MODEL_OVERRIDE_LOCK 锁粒度问题**

- **位置**：`task_orchestrator.py:29`
- **问题**：`get_model_config()` 在释放锁后读取 `_runtime_model_overrides`，可能被其他线程修改。

**[HIGH] API Key 启动时无验证**

- **位置**：`config.py:204-237`
- **问题**：启动时未校验 API Key 有效性，运行时才发现配置错误。

**[HIGH] CLI 无 SIGINT/SIGTERM 处理**

- **位置**：`main.py:121-123`
- **问题**：内存清理在 signal kill 时丢失。

**[MEDIUM] Orchestrator 创建时 lock 未初始化**

- **位置**：`task_orchestrator.py:80-85`
- **问题**： `_lock` 在 `__post_init__` 中初始化，但 `get_model_config()` 在初始化前可能就被调用。

**[MEDIUM] 配置校验不完整**

- **位置**：`config.py:204-237`
- **问题**：只检查 key 存在性，未验证 key 格式、权限范围。

**[MEDIUM] lazy initialization 非线程安全**

- **位置**：`task_orchestrator.py:92`
- **问题**：属性延迟初始化在多线程下可能产生多个实例。

**[MEDIUM] shutdown 无资源清理注册机制**

- **位置**：`main.py:121-123`
- **问题**：signal handler 只做简单 return，资源未清理。

**[MEDIUM] 配置注入缺少 schema 校验**

- **位置**：`config.py`
- **问题**：环境变量直接注入无类型校验。

**[LOW] 配置模块无版本兼容性检查**

- **位置**：`config.py`
- **问题**：新配置项与旧版本不兼容时无提示。

**[LOW] 初始化顺序无文档**

- **位置**：`main.py`
- **问题**：初始化顺序依赖隐式调用，脆弱。

---

### 平台集成（CRITICAL: 1, HIGH: 4, MEDIUM: 7, LOW: 3）

**[CRITICAL] SSRF 风险：上传 URL 未验证**

- **位置**：`wechat_ilink.py:1748-1751`
- **问题**：`upload_full_url` 绕过 `_assert_wechat_cdn_url()` 安全检查。

**[HIGH] 拼写错误：_session 应为 _send_session**

- **位置**：`wechat_ilink.py:1971`
- **问题**：`adapter._session = session` 但类中只有 `_send_session`。

**[HIGH] 重复导入 apprise 模块**

- **位置**：`apprise_adapter.py:28,74`
- **问题**：两次导入风格不一致，增加加载开销。

**[HIGH] 格式化字符串中保留未使用变量**

- **位置**：`apprise_adapter.py:825`
- **问题**：`_qr_exc` 变量以下划线开头但在 f-string 中使用。

**[HIGH] WeChatAdapter 创建时 _typing_cache 未初始化**

- **位置**：`wechat_ilink.py:1976`
- **问题**：临时 adapter 只设置 `_token_store`，未初始化 `_typing_cache`。

**[MEDIUM] 空块分割导致 IndexError**

- **位置**：`wechat_format.py:214`
- **问题**：空字符串 `splitlines()[0]` 会崩溃。

**[MEDIUM] 重复的分块截断逻辑**

- **位置**：`outbound_bridge.py:383-384, 417-418`
- **问题**：两处完全相同的 4000 字符截断逻辑重复。

**[MEDIUM] emit_threadsafe 非原子问题（同上）**

- **位置**：`outbound_bridge.py:207-213`
- **问题**：检查与操作之间存在竞态。

**[MEDIUM] 导入顺序不符合 PEP8**

- **位置**：`wechat_ilink.py:50-56`
- **问题**：条件导入与标准库导入之间空行数不足。

**[MEDIUM] _send_file 返回值覆盖**

- **位置**：`wechat_ilink.py:1779-1792`
- **问题**：caption 消息 ID 被 media 消息 ID 覆盖丢失。

**[MEDIUM] send_wechat_direct token_store._typing_cache 缺失**

- **位置**：`wechat_ilink.py:1976`
- **问题**：见 HIGH 条目。

**[LOW] 临时文件未使用上下文管理器**

- **位置**：`wechat_ilink.py:78-83`
- **问题**：风格可改进。

**[LOW] MessageDeduplicator 清理效率低（同上）**

- **位置**：`helpers.py:33-35`
- **问题**：每次调用都重建过滤副本。

**[LOW] 缺少类型注解**

- **位置**：`helpers.py:11`
- **问题**：`dict` 应使用 `Dict[str, Any]` 保持一致。

---

### 错误处理与恢复（CRITICAL: 0, HIGH: 2, MEDIUM: 5, LOW: 3）

**[HIGH] format_error_card 函数未被生产代码调用**

- **位置**：`error_cards.py:10` + `message_handler.py`
- **问题**：`format_error_card` 定义了4种错误卡片，但生产代码从未调用，用户收不到结构化错误提示。
- **修复**：在 `message_handler.py` 中对接 `format_error_card`。

**[HIGH] format_gateway_user_error 异常参数被忽略**

- **位置**：`user_errors.py:6-9`
- **问题**：`del exc` 丢弃所有错误上下文，用户始终收到通用消息。
- **修复**：利用 `error_cards.py` 的分类逻辑或实现错误类型映射。

**[MEDIUM] tool_error 截断丢失上下文**

- **位置**：`error_cards.py:42`
- **问题**：`error[:200]` 硬截断可能丢失有效错误原因。

**[MEDIUM] _RETRY_MARKERS "429" 字符串匹配过宽**

- **位置**：`tool_error_policy.py:56-70`
- **问题**：纯数字 "429" 会误匹配文档、用户输入中的 "429"。

**[MEDIUM] reply_admission 无 TTL 清理（同上）**

- **位置**：`reply_admission.py:20-21`
- **问题**：stale session 永久占用。

**[MEDIUM] bot_loop_guard 正则性能差（同上）**

- **位置**：`bot_loop_guard.py:44-51`
- **问题**：正则匹配在高频路径上性能不佳。

**[MEDIUM] 错误信息流在最后一公里断裂**

- **位置**：`error_cards.py` vs `user_errors.py`
- **问题**：`format_error_card` 定义丰富，但 `format_gateway_user_error` 返回通用消息。

**[LOW] vision_fallback 未缓存环境变量解析**

- **位置**：`vision_fallback.py:15-19`
- **问题**：应使用 `functools.lru_cache`。

**[LOW] bot_loop_guard 白名单每次解析环境变量**

- **位置**：`bot_loop_guard.py:36-41`
- **问题**：应缓存结果。

**[LOW] llm_retry 日志消息误导（同上）**

- **位置**：`llm_retry.py:149,160,180,205,255,277,293`
- **问题**：日志消息与实际执行操作不符。

---

## 附录：问题统计总表（第8轮更新）

| 维度 | CRITICAL | HIGH | MEDIUM | LOW |
|------|----------|------|--------|-----|
| 安全与权限 | 3 | 5 | 5 | 5 |
| 架构设计 | 2 | 5 | 4 | 2 |
| 工具系统 | 2 | 4 | 6 | 2 |
| Gateway与队列 | 0 | 5 | 10 | 4 |
| Workflow系统 | 2 | 5 | 6 | 4 |
| 记忆系统 | 1 | 5 | 15 | 5 |
| 测试质量 | 0 | 2 | 8 | 4 |
| Transport层 | 0 | 2 | 8 | 2 |
| Session与生命周期 | 1 | 4 | 10 | 4 |
| CLI与配置 | 0 | 2 | 7 | 3 |
| 项目系统 | 3 | 3 | 5 | 4 |
| Report与后处理 | 0 | 3 | 18 | 6 |
| Hook与回调系统 | 0 | 4 | 7 | 2 |
| 循环依赖与边界case | 1 | 3 | 3 | 3 |
| 监控可观测性与日志 | 0 | 1 | 7 | 2 |
| SQLite与持久化 | 0 | 1 | 4 | 1 |
| 部署与运维脚本 | 2 | 3 | 5 | 5 |
| 多Agent协作与通信 | 1 | 2 | 1 | 1 |
| Skill系统 | 0 | 1 | 5 | 4 |
| 数据流与事件系统 | 3 | 3 | 3 | 3 |
| 系统初始化与依赖注入 | 1 | 2 | 5 | 2 |
| 平台集成 | 1 | 4 | 7 | 3 |
| 错误处理与恢复 | 0 | 2 | 5 | 3 |
| **总计** | **24** | **76** | **181** | **102** |

---

*文档版本：1.5*
*最后更新：2026-05-28（第8轮挑刺完成）*
*状态：持续更新中*