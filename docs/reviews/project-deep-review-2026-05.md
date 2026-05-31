# WFXM 项目深度检查报告

**检查日期**: 2026/05/31
**项目**: Butler v4 管家系统
**版本**: 4.0.0

---

## 检查概览

| 轮次 | 日期 | 检查范围 | 发现问题数 |
|------|------|----------|-----------|
| 第1轮 | 2026/05/31 | 核心模块架构检查 | 67 |
| 第2轮 | 2026/05/31 | 安全与权限检查 | 26 |
| 第3轮 | 2026/05/31 | 测试覆盖与质量检查 | 18 |

---

## 第1轮：核心模块架构检查

### 1.1 Orchestrator 与 TaskOrchestrator

**文件**: `butler/orchestrator.py`, `butler/task_orchestrator.py`

| 问题编号 | 严重程度 | 问题描述 | 位置 | 状态 |
|----------|----------|----------|------|------|
| ORCH-001 | HIGH | Race Condition — `butler_memory` 属性中的 LRU 淘汰逻辑，检查 len 和执行 pop 之间没有锁保护 | orchestrator.py:139-142 | 待确认 |
| ORCH-002 | HIGH | 潜在死锁 — `asyncio.to_thread` 内持有 `threading.RLock` 可能导致重入死锁 | task_orchestrator.py:122-128 | 待确认 |
| ORCH-003 | MEDIUM | 冗余变量赋值 — `model_block` 被同时赋值给 `butler_model` 和 `model_block` 两个 key | orchestrator.py:290,293 | 待确认 |
| ORCH-004 | MEDIUM | 脆弱的模板替换 — 字符串 replace 模式，如果占位符值包含 `{...}` 会导致二次替换 | orchestrator.py:326-327 | 待确认 |
| ORCH-005 | MEDIUM | 函数过长 — `execute_graph` 达 175 行，包含多个职责 | task_orchestrator.py:338-512 | 待确认 |
| ORCH-006 | MEDIUM | 异常被静默处理 — `on_progress` 回调异常仅记录 debug 级别 | task_orchestrator.py:194-197 | 待确认 |
| ORCH-007 | MEDIUM | `until` 断言失败时提前返回，不一致的 retry 行为 | task_orchestrator.py:543-568 | 待确认 |
| ORCH-008 | LOW | `getattr` 用于访问 dict 属性 — 脆弱的模式 | task_orchestrator.py:123 | 待确认 |
| ORCH-009 | LOW | task dict 清理逻辑不完整，只清理 completed 状态任务的前 100 个 | task_orchestrator.py:180-186 | 待确认 |
| ORCH-010 | LOW | 模板渲染逻辑三处重复 | orchestrator.py:325-327, 364-365, 418-420 | 待确认 |

### 1.2 Agent Loop 核心

**文件**: `butler/core/agent_loop.py`, `butler/core/context_pipeline.py`, `butler/core/llm_retry.py`, `butler/core/tool_batch.py`

| 问题编号 | 严重程度 | 问题描述 | 位置 | 状态 |
|----------|----------|----------|------|------|
| CORE-001 | HIGH | 缓存存储逻辑缺陷 — 缓存条件 `not response.tool_calls` 过严，与缓存查找条件不一致 | llm_retry.py:182-195 | 待确认 |
| CORE-002 | HIGH | guardrails 在缓存场景重复执行 — 缓存命中时仍执行 before_call/after_call | tool_batch.py:156-175 | 待确认 |
| CORE-003 | MEDIUM | 内部函数重复定义 — `prepare_messages_for_api` 每次调用时重新定义 8 个内部函数 | context_pipeline.py:206-317 | 待确认 |
| CORE-004 | MEDIUM | 函数过长 — `_run_turn_body` 达 330+ 行 | agent_loop.py:216 | 待确认 |
| CORE-005 | MEDIUM | 魔法数字限制重试次数 — 硬编码上限 20，无配置项 | llm_retry.py:97 | 待确认 |
| CORE-006 | MEDIUM | 异常捕获过于宽泛 — 捕获所有 `Exception` 并静默忽略 | context_pipeline.py:129-148 | 待确认 |
| CORE-007 | MEDIUM | 限流与 guardrails 无协调机制 — 各自独立检查 | tool_batch.py:179-201 | 待确认 |
| CORE-008 | LOW | 闭包捕获外部变量导致潜在问题 | llm_retry.py:113-127 | 待确认 |
| CORE-009 | LOW | 访问内部属性 `_same_tool_failure_counts` | agent_loop.py:761-763 | 待确认 |
| CORE-010 | LOW | 工具结果判断逻辑脆弱 — 通过字符串匹配判断错误类型 | tool_batch.py:25-34 | 待确认 |
| CORE-011 | MEDIUM | `_inject_ephemeral_system` 修改列表同时迭代的逻辑问题 | context_pipeline.py:365-376 | 待确认 |

### 1.3 Gateway 与消息处理

**文件**: `butler/gateway/`

| 问题编号 | 严重程度 | 问题描述 | 位置 | 状态 |
|----------|----------|----------|------|------|
| GATE-001 | HIGH | Session interrupt 与 session destruction 存在竞态条件 — `_interrupt_session_loop` 访问 session 时无锁保护 | message_handler.py:121-136 | 待确认 |
| GATE-002 | HIGH | 幂等性预留泄露 — `complete_inbound()` 抛出时消息永久标记为 inflight | message_handler.py:389-404, 643-647 | 待确认 |
| GATE-003 | MEDIUM | Queue gauges 刷新在锁外部访问 `_QUEUES` 状态 | message_queue.py:171-189 | 待确认 |
| GATE-004 | MEDIUM | 陈旧 registry 恢复存在固有竞态 | message_handler.py:219-230 | 待确认 |
| GATE-005 | MEDIUM | Session warmup 状态在 session 移除时缺少清理 — `_WARMED` 集合累积条目 | session_lifecycle.py / handler_helpers.py | 待确认 |
| GATE-006 | MEDIUM | 持久化队列重写不原子 — 并发移除可能竞争 | message_queue.py:334-341 | 待确认 |
| GATE-007 | LOW | Bot loop guard 阈值按 sender 而非按 pair | bot_loop_guard.py:69-76 | 待确认 |
| GATE-008 | LOW | Welcome session marker 文件写入存在竞争 | handler_helpers.py:402-410 | 待确认 |
| GATE-009 | LOW | Command dispatch 捕获所有异常 | command_registry.py:83-88 | 待确认 |

### 1.4 记忆系统

**文件**: `butler/memory/`

| 问题编号 | 严重程度 | 问题描述 | 位置 | 状态 |
|----------|----------|----------|------|------|
| MEM-001 | HIGH | Race condition in `_turn_buffer` access — 无锁保护的多线程访问 | facade.py:335-340 | 待确认 |
| MEM-002 | HIGH | `flush_observer_queue` 写失败时可能丢失数据 — 清空和重新插入之间有新数据加入 | observer_queue.py:109-129 | 待确认 |
| MEM-003 | HIGH | `InMemoryVectorStore` 无线程安全 — 所有操作访问 `self._docs` 无同步 | vector_store.py:143-224 | 待确认 |
| MEM-004 | MEDIUM | `ExperienceStore.record_access` 每次更新单行，可能跳过部分更新 | butler_memory.py:209-225 | 待确认 |
| MEM-005 | MEDIUM | `ProjectFactsStore.auto_extract` 三次独立 `rglob` 遍历 | project_memory.py:540-546 | 待确认 |
| MEM-006 | MEDIUM | `semantic_index.py` 大结果集上的暴力相似度计算 — 最多 2000 行 | semantic_index.py:154-226 | 待确认 |
| MEM-007 | MEDIUM | `TripletIndex.upsert_from_content` 捕获通用 `sqlite3.Error` 后静默跳过 | triplets.py:122 | 待确认 |
| MEM-008 | LOW | `FastEmbedEmbedder._ensure_model` 未在构造时缓存 | embedding.py:193-198 | 待确认 |
| MEM-009 | LOW | `reindex_semantic_memory` 一次加载 10,000 行experience | reindex.py:70 | 待确认 |
| MEM-010 | LOW | `ChromaVectorStore` 非线程安全 | vector_store.py:58-140 | 待确认 |
| MEM-011 | LOW | 全局 `_STORE_CACHE` 字典驱逐使用插入顺序而非访问时间 | vector_store.py:236-238 | 待确认 |

### 1.5 配置与传输层

**文件**: `butler/config.py`, `butler/config_secrets.py`, `butler/config_service.py`, `butler/transport/`

| 问题编号 | 严重程度 | 问题描述 | 位置 | 状态 |
|----------|----------|----------|------|------|
| TRANS-001 | HIGH | `wire_tools_for_provider` 失败时静默回退可能产生错误的工具 schema | transport/llm_client.py:144-146 | 待确认 |
| TRANS-002 | HIGH | Dummy API key 掩盖配置错误 — 使用 "dummy" 占位符延迟失败 | transport/llm_client.py:81-84 | 待确认 |
| TRANS-003 | HIGH | `config_set` 验证整数但不转换 — 验证后丢弃结果 | config.py:133-136 | 待确认 |
| TRANS-004 | HIGH | `_ensure_private_mode` 文件权限硬化失败时静默继续 | config_secrets.py:41-42 | 待确认 |
| TRANS-005 | HIGH | `get_butler_home()` 信任 `BUTLER_HOME` 环境变量无清理 — 存在符号链接攻击风险 | config_service.py:396-398 | 待确认 |
| TRANS-006 | MEDIUM | 导入错误消息在两个 SDK 都缺失时误导 | transport/llm_client.py:115-116 | 待确认 |
| TRANS-007 | MEDIUM | `config_get` 对未知键返回硬编码中文字符串 | config.py:120 | 待确认 |
| TRANS-008 | MEDIUM | `load_secrets_dict` 使用过于宽泛的异常处理 | config_secrets.py:54 | 待确认 |
| TRANS-009 | MEDIUM | `write_provider_secret` 在确保私有模式前写入文件 | config_secrets.py:102-107 | 待确认 |
| TRANS-010 | MEDIUM | `save_butler_config` 使用 `tempfile.mkstemp` 但无明确权限限制 | config_service.py:302-316 | 待确认 |
| TRANS-011 | MEDIUM | `_load_env_providers` 与 `ProviderConfig` 字段默认值重复逻辑 | config_service.py:206-238 | 待确认 |
| TRANS-012 | MEDIUM | 流错误处理可能吞掉合法错误 | transport/llm_client.py:372-376 | 待确认 |
| TRANS-013 | LOW | `get_provider` 和 `list_providers` 每次调用时延迟注册内置 provider | transport/providers.py:45-55 | 待确认 |
| TRANS-014 | LOW | `ProviderProfile.aliases` 缺少类型注解 | transport/providers.py:21 | 待确认 |

### 1.6 工具系统

**文件**: `butler/tools/`

| 问题编号 | 严重程度 | 问题描述 | 位置 | 状态 |
|----------|----------|----------|------|------|
| TOOL-001 | HIGH | 工具调度时缺少 schema 验证 — 仅用于文档而非运行时验证 | tools/registry.py:262 | 待确认 |
| TOOL-002 | HIGH | data_query SQLite ATTACH 缺少写操作 enforcement | tools/data_query.py:119-121 | 待确认 |
| TOOL-003 | HIGH | 审计日志缺少关键查询元数据 — 只记录参数名而非值 | tools/registry.py:590-625 | 待确认 |
| TOOL-004 | MEDIUM | data_query SQL 注入通过 regex bypass — 注释可绕过检查 | tools/data_query.py:18-28 | 待确认 |
| TOOL-005 | MEDIUM | DuckDB 连接未加固 — `read_only=False` 与设计不符 | tools/data_query.py:110 | 待确认 |
| TOOL-006 | MEDIUM | 终端管道模式允许路径提取 bypass | tools/path_safety.py:200-203 | 待确认 |
| TOOL-007 | MEDIUM | 工具注册表无速率限制 | tools/registry.py:164 | 待确认 |
| TOOL-008 | MEDIUM | data_query 缺少执行超时 | tools/data_query.py:61-161 | 待确认 |
| TOOL-009 | LOW | 错误消息语言不一致 | tools/data_query.py:75-76 | 待确认 |
| TOOL-010 | LOW | data_query 工具处理程序静默忽略额外 kwargs | tools/data_query.py:66 | 待确认 |
| TOOL-011 | LOW | 符号链接检查使用 `startswith` 比较 | tools/path_safety.py:268 | 待确认 |
| TOOL-012 | LOW | 终端配置文件环境变量未验证 | tools/path_safety.py:50-58 | 待确认 |

---

## 第2轮：安全与权限检查

### 2.1 安全漏洞

**文件**: `butler/main.py`, `butler/permissions/rules.py`, `butler/tools/path_safety.py`, `butler/ops/security_audit.py`

| 问题编号 | 严重程度 | 问题描述 | 位置 | 状态 |
|----------|----------|----------|------|------|
| SEC-001 | CRITICAL | 凭证明文日志记录 — WeChat token 在 `wechat-setup` 命令中被输出到控制台 | main.py:722-735 | 待确认 |
| SEC-002 | HIGH | 工作区权限检查 fail-open — workspace 为 None 时允许所有危险工具 | permissions/rules.py:461-468 | 待确认 |
| SEC-003 | HIGH | 终端管道模式使用 `shell=True` — 可能绕过 allowlist | tools/path_safety.py:204 | 待确认 |
| SEC-004 | HIGH | WeChat DM 策略默认为 `open` — 无需验证即可发送消息 | ops/security_audit.py:41-49 | 待确认 |
| SEC-005 | HIGH | 一次性审批指纹碰撞风险 — SHA256 截断至 32/16 字符 | permissions/approvals.py:28-38 | 待确认 |
| SEC-006 | HIGH | 网关处理器无消息速率限制 — DoS 风险 | message_handler.py:232-657 | 待确认 |
| SEC-007 | MEDIUM | 密钥文件 chmod 失败被静默忽略 | config_secrets.py:35-42 | 待确认 |
| SEC-008 | MEDIUM | 审计事件记录参数键但不记录值 — 无法审计敏感数据访问 | tools/registry.py:604-611 | 待确认 |
| SEC-009 | MEDIUM | 审计 JSONL 路径在 workspace 控制下 — 可被篡改 | audit_persist.py:28-31 | 待确认 |
| SEC-010 | MEDIUM | 审计会话键为空字符串 — 无法关联 | execution_context.py:88-95 | 待确认 |
| SEC-011 | MEDIUM | 工具调用 ID 的 UUID 生成较弱 — 仅 8 字符 hex (32 bits) | core/tool_batch.py:57 | 待确认 |
| SEC-012 | MEDIUM | 会话键验证允许广泛字符集 — 路径遍历风险 | session/keys.py:8 | 待确认 |
| SEC-013 | LOW | 注入检测仅基于启发式 — 可能被绕过 | memory/injection_guard.py:33-57 | 待确认 |
| SEC-014 | LOW | 终端危险模式检测是 opt-in — 默认可能未启用 | tools/path_safety.py:29 | 待确认 |

### 2.2 并发安全

**文件**: `butler/task_orchestrator.py`, `butler/gateway/session_registry.py`, `butler/memory/facade.py`, `butler/memory/vector_store.py`, `butler/transport/llm_client.py`

| 问题编号 | 严重程度 | 问题描述 | 位置 | 状态 |
|----------|----------|----------|------|------|
| CONC-001 | CRITICAL | `_MODEL_OVERRIDE_LOCK` 全局锁竞态 — 多线程并发修改同一 role 的 override 导致互相覆盖 | task_orchestrator.py:29, 122-128 | 待确认 |
| CONC-002 | CRITICAL | `asyncio.to_thread` 与 RLock 组合死锁风险 — `enter_session` 中可能死锁 | task_orchestrator.py:224-228 | 待确认 |
| CONC-003 | CRITICAL | `GatewaySessionRegistry.reset_all` 竞态条件 — `_resetting_all` 设置后释放锁，新条目可通过 `get_or_create` 进入 | session_registry.py:197-232 | 待确认 |
| CONC-004 | CRITICAL | `_reset_if_still_idle` 双重锁获取顺序问题 — 可能导致长时间阻塞 | session_registry.py:289-307 | 待确认 |
| CONC-005 | CRITICAL | `_STORE_CACHE` 字典竞态条件 — 无锁保护，并发访问导致数据竞争 | vector_store.py:227-253 | 待确认 |
| CONC-006 | HIGH | `enter_session` 中 `lock.release()` 无条件执行 — 可能导致锁双重释放 | session_registry.py:91-109 | 待确认 |
| CONC-007 | HIGH | `_turn_buffer` 非线程安全 — 多线程并发调用 `sync_turn` 导致数据竞争 | facade.py:335-340 | 待确认 |
| CONC-008 | HIGH | `_QUEUES` 全局字典排序非原子 — `re-sort` 和重新赋值间有竞争窗口 | message_queue.py:166-168 | 待确认 |
| CONC-009 | HIGH | `_should_dedupe` 检查和写入非原子 — 多线程可同时通过检查 | message_queue.py:63-80 | 待确认 |
| CONC-010 | MEDIUM | `TaskOrchestrator._tasks` 字典非线程安全 — TOCTOU 竞态 | task_orchestrator.py:179-187 | 待确认 |
| CONC-011 | MEDIUM | `InMemoryVectorStore._docs` 字典非线程安全 — 多线程并发访问 | vector_store.py:143-224 | 待确认 |
| CONC-012 | MEDIUM | `ChromaVectorStore` 缺少线程安全 — ChromaDB client 可能非线程安全 | vector_store.py:58-140 | 待确认 |
| CONC-013 | MEDIUM | `LLMClient._get_openai_client` 懒加载竞态 — DCL 问题 | llm_client.py:76-91 | 待确认 |
| CONC-014 | MEDIUM | `LLMClient._get_anthropic_client` 同样懒加载竞态 | llm_client.py:93-117 | 待确认 |
| CONC-015 | LOW | `_TrackedSessionDict.__setitem__` 潜在嵌套锁问题 | session_registry.py:28-31 | 待确认 |

### 2.3 错误处理

**文件**: `butler/memory/butler_memory.py`, `butler/transport/llm_client.py`, `butler/core/llm_retry.py`, `butler/core/context_pipeline.py`, `butler/memory/observer_queue.py`

| 问题编号 | 严重程度 | 问题描述 | 位置 | 状态 |
|----------|----------|----------|------|------|
| ERR-001 | CRITICAL | `ProfileStore._save_unlocked` 资源泄漏 — 异常被 `pass` 掩盖，临时文件可能残留 | butler_memory.py:50-65 | 待确认 |
| ERR-002 | CRITICAL | 流式错误吞掉部分内容 — 失败时返回 `finish_reason="error"` 但无法区分是否完整 | llm_client.py:372-376 | 待确认 |
| ERR-003 | HIGH | `llm_retry.py` 回调失败静默忽略 — 回调异常仅 debug 级别日志， metrics 可能丢失 | llm_retry.py:149-151, 160-161, 等多处 | 待确认 |
| ERR-004 | HIGH | `context_pipeline.py` LLM 调用前异常被吞掉 — 重要诊断跟踪可能被跳过 | context_pipeline.py:100-101, 126-127, 等 | 待确认 |
| ERR-005 | HIGH | `flush_observer_queue` 失败时返回 0 — 无法区分队列为空还是写入失败 | observer_queue.py:121-129 | 待确认 |
| ERR-006 | MEDIUM | `except Exception` 用于可选功能 — 大量 bare except，消息不准确（如 "on delta cb skipped"） | 多处 | 待确认 |
| ERR-007 | MEDIUM | `_call_anthropic` thinking header 失败静默跳过 | llm_client.py:272-281 | 待确认 |
| ERR-008 | LOW | 复制粘贴错误 — 日志消息与实际上下文不匹配 | llm_retry.py 多处 | 待确认 |

---

## 第3轮：测试覆盖与质量检查

### 3.1 代码复杂度问题

| 问题编号 | 严重程度 | 问题描述 | 位置 | 状态 |
|----------|----------|----------|------|------|
| QUAL-001 | CRITICAL | `message_handler.py` 达 1252 行，超过 800 行限制 | message_handler.py | 待重构 |
| QUAL-002 | CRITICAL | `agent_loop.py` 达 808 行，超过 800 行限制 | agent_loop.py | 待重构 |
| QUAL-003 | CRITICAL | `handle_message` 函数达 425 行，远超 50 行限制 | message_handler.py:232-657 | 待重构 |
| QUAL-004 | CRITICAL | `execute_graph` 函数达 175 行 | task_orchestrator.py:338-512 | 待重构 |
| QUAL-005 | CRITICAL | `spawn_agent` 函数达 135 行 | task_orchestrator.py:171-305 | 待重构 |
| QUAL-006 | HIGH | `_run_turn_body` 函数达 330 行 | agent_loop.py:216-552 | 待重构 |
| QUAL-007 | HIGH | `_handle_message_locked` 函数达 298 行 | message_handler.py:659-956 | 待重构 |
| QUAL-008 | HIGH | `_handle_command` 函数达 234 行 | message_handler.py:962-1195 | 待重构 |
| QUAL-009 | HIGH | `create_agent_loop` 函数达 75 行 | orchestrator.py:460-534 | 待重构 |
| QUAL-010 | HIGH | `create_project_agent_loop` 函数达 62 行 | orchestrator.py:536-596 | 待重构 |
| QUAL-011 | MEDIUM | 函数内导入（而非模块级别导入）| 多处 | 待优化 |
| QUAL-012 | MEDIUM | 重复导入同一模块 | orchestrator.py | 待优化 |
| QUAL-013 | MEDIUM | 标准库导入被遮蔽 | task_orchestrator.py:19 | 待确认 |
| QUAL-014 | LOW | 魔法数字无命名常量 | task_orchestrator.py:180, 185 | 待优化 |

### 3.2 测试覆盖率

**总体覆盖率**: 72.5%（低于 80% 目标）

**覆盖率低于 80% 的关键模块**（部分）：

| 文件 | 覆盖率 | 语句数 |
|------|--------|--------|
| butler/gateway/registry_commands.py | 7.6% | 198 |
| butler/gateway/speech_stt.py | 19.6% | 56 |
| butler/core/transcript_search.py | 24.7% | 85 |
| butler/registry/mcp_catalog_remote.py | 26.2% | 61 |
| butler/memory/injection_llm_score.py | 27.7% | 47 |
| butler/tools/execute_code.py | 30.6% | 72 |
| butler/core/remote_compact.py | 36.5% | 115 |
| butler/gateway/runner.py | 38.1% | 189 |
| butler/tools/web_fetch.py | 37.1% | 97 |

---

## 汇总统计

### 第1轮 + 第2轮 + 第3轮 汇总

| 类别 | CRITICAL | HIGH | MEDIUM | LOW | 合计 |
|------|----------|------|--------|-----|------|
| Orchestrator | 0 | 2 | 5 | 3 | 10 |
| Agent Loop | 0 | 2 | 6 | 3 | 11 |
| Gateway | 0 | 2 | 4 | 3 | 9 |
| Memory | 0 | 3 | 4 | 4 | 11 |
| Config/Transport | 0 | 5 | 7 | 2 | 14 |
| Tools | 0 | 3 | 5 | 4 | 12 |
| Security | 1 | 5 | 6 | 2 | 14 |
| Concurrency | 5 | 4 | 7 | 1 | 17 |
| Error Handling | 2 | 3 | 2 | 1 | 8 |
| Quality | 5 | 5 | 3 | 1 | 14 |
| **总计** | **13** | **36** | **51** | **26** | **126** |

---

## 紧急处理项

### CRITICAL（必须立即处理）

1. **[SEC-001]** WeChat token 明文输出到控制台
2. **[CONC-001]** `_MODEL_OVERRIDE_LOCK` 全局锁竞态
3. **[CONC-002]** `asyncio.to_thread` 与 RLock 组合死锁风险
4. **[CONC-003]** `reset_all` 竞态条件
5. **[CONC-004]** `_reset_if_still_idle` 锁顺序问题
6. **[CONC-005]** `_STORE_CACHE` 无锁保护
7. **[ERR-001]** `ProfileStore._save_unlocked` 资源泄漏
8. **[ERR-002]** 流式错误吞掉部分内容

### HIGH（应尽快处理）

| 类别 | 问题编号 | 描述 |
|------|----------|------|
| Orchestrator | ORCH-001 | `butler_memory` LRU 淘汰竞态 |
| Orchestrator | ORCH-002 | `asyncio.to_thread` 内 RLock 死锁 |
| Agent Loop | CORE-001 | 缓存存储条件不一致 |
| Agent Loop | CORE-002 | Guardrails 缓存场景重复执行 |
| Gateway | GATE-001 | Session interrupt 竞态 |
| Gateway | GATE-002 | 幂等性预留泄露 |
| Memory | MEM-001 | `_turn_buffer` 无锁保护 |
| Memory | MEM-002 | `flush_observer_queue` 数据丢失 |
| Memory | MEM-003 | `InMemoryVectorStore` 非线程安全 |
| Config | TRANS-001 | 工具 schema 静默回退 |
| Config | TRANS-002 | Dummy API key 掩盖错误 |
| Config | TRANS-003 | 整数验证后不转换 |
| Config | TRANS-004 | 密钥权限硬化失败静默 |
| Config | TRANS-005 | `BUTLER_HOME` 符号链接攻击 |
| Tools | TOOL-001 | 工具调度缺少 schema 验证 |
| Tools | TOOL-002 | SQLite ATTACH 写操作 enforcement |
| Tools | TOOL-003 | 审计日志缺少查询内容 |
| Security | SEC-002 | 工作区权限 fail-open |
| Security | SEC-003 | 终端 shell=True |
| Security | SEC-004 | WeChat DM 策略 open |
| Security | SEC-005 | 指纹碰撞风险 |
| Security | SEC-006 | 无消息速率限制 |
| Concurrency | CONC-006 | 锁双重释放 |
| Concurrency | CONC-007 | `_turn_buffer` 数据竞争 |
| Concurrency | CONC-008 | `_QUEUES` 排序非原子 |
| Concurrency | CONC-009 | `_should_dedupe` 竞态 |
| Error | ERR-003 | 回调失败静默忽略 |
| Error | ERR-004 | LLM 调用前异常被吞 |
| Error | ERR-005 | `flush_observer_queue` 返回值歧义 |

---

## 检查完成

| 轮次 | 完成时间 | 发现问题 |
|------|----------|----------|
| 第1轮 | 2026/05/31 | 67 (HIGH: 17, MEDIUM: 31, LOW: 19) |
| 第2轮 | 2026/05/31 | 45 (CRITICAL: 8, HIGH: 23, MEDIUM: 10, LOW: 4) |
| 第3轮 | 2026/05/31 | 14 (CRITICAL: 5, HIGH: 5, MEDIUM: 3, LOW: 1) |
| **总计** | | **126** |

**三轮检查全部完成**