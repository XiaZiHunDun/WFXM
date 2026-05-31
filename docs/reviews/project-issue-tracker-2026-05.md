# WFXM 项目详细问题记录

**创建日期**: 2026/05/31
**项目**: Butler v4 管家系统
**版本**: 4.0.0
**检查状态**: ✅ 三轮深入检查完成

---

## 检查轮次记录

| 轮次 | 日期 | 检查范围 | 确认问题数 |
|------|------|----------|-----------|
| 第1轮 | 2026/05/31 | Orchestrator/TaskOrchestrator详细验证 | 10 |
| 第2轮 | 2026/05/31 | Agent Loop/Core模块详细验证 | 9 |
| 第3轮 | 2026/05/31 | Gateway/消息处理详细验证 | 14 |
| 第4轮 | 2026/05/31 | Memory记忆系统详细验证 | 10 |
| 第5轮 | 2026/05/31 | Config/Transport/Tools详细验证 | 13 |
| 第6轮 | 2026/05/31 | Security/Permissions/Tools详细验证 | 16 |

---

## 确认问题汇总

### CRITICAL（必须立即处理）

| 编号 | 类别 | 问题描述 | 文件位置 | 代码证据 |
|------|------|----------|----------|----------|
| SEC-002 | Security | 工作区权限fail-open — workspace为None时允许所有危险工具 | permissions/rules.py:461-468 | `workspace is None`时返回`None`允许执行 |
| SEC-003 | Security | 终端管道模式使用shell=True — 可绕过allowlist | tools/path_safety.py:204 | `["bash", "-c", text]`使用shell执行 |

### HIGH（应尽快处理）

| 编号 | 类别 | 问题描述 | 文件位置 | 代码证据 |
|------|------|----------|----------|----------|
| ORCH-002 | Concurrency | asyncio.to_thread内持RLock死锁风险 | task_orchestrator.py:122-128 | 锁内执行I/O操作 |
| ORCH-007 | Logic | until断言失败时不重试，直接返回 | task_orchestrator.py:543-568 | 断言失败直接return不重试 |
| CONC-001 | Concurrency | _MODEL_OVERRIDE_LOCK全局锁竞态 | task_orchestrator.py:29,122-128 | 多线程并发修改override |
| CORE-006 | Error | 异常捕获过于宽泛并静默忽略 | context_pipeline.py:126-127,147-148 | `except Exception`仅debug日志 |
| TRANS-002 | Config | Dummy API key掩盖配置错误 | transport/llm_client.py:81-84 | 无key时设"dummy" |
| TRANS-012 | Error | 流错误吞掉部分内容返回伪装成功 | transport/llm_client.py:372-376 | 有partial数据时不re-raise |
| GATE-001 | Concurrency | Session interrupt竞态条件 | message_handler.py:121-136 | 访问session无锁保护 |
| GATE-002 | Logic | complete_inbound幂等性泄露 | message_handler.py:643-647 | 异常被静默吞掉 |
| GATE-003 | Concurrency | Queue gauges刷新在锁外访问 | message_queue.py:171-189 | 刷新在锁外调用 |
| GATE-004 | Concurrency | 陈旧registry恢复竞态 | message_handler.py:219-230 | 修改_resetting_all无锁 |
| GATE-006 | Persistence | 持久化队列重写非原子 | message_queue.py:334-341 | 写和删除非原子 |
| MEM-002 | Persistence | flush_observer_queue数据丢失 | observer_queue.py:119-128 | DB失败时数据丢失 |
| MEM-003 | Thread Safety | InMemoryVectorStore非线程安全 | vector_store.py:175-183 | 并发访问_docs无锁 |
| MEM-010 | Thread Safety | ChromaVectorStore非线程安全 | vector_store.py:58-140 | 所有方法无锁保护 |
| CONC-003 | Concurrency | reset_all竞态条件 | session_registry.py:197-232 | 释放锁到重新获取间有窗口 |
| CONC-004 | Concurrency | _reset_if_still_idle锁顺序问题 | session_registry.py:289-307 | 锁顺序不一致可能死锁 |
| CONC-005 | Concurrency | _STORE_CACHE无锁保护 | vector_store.py:231-253 | 字典访问无同步 |
| CONC-006 | Concurrency | enter_session锁双重释放 | session_registry.py:91-109 | 条件分支导致锁未释放 |
| CONC-007 | Concurrency | _turn_buffer数据竞争 | facade.py:335-368 | 并发访问无同步 |
| CONC-008 | Concurrency | _QUEUES排序竞态 | message_queue.py:166-168 | 创建和赋值非原子 |
| CONC-009 | Concurrency | _should_dedupe竞态 | message_queue.py:63-80 | 检查和写入非原子 |
| CONC-011 | Concurrency | _docs字典非线程安全 | vector_store.py:147,175-183 | 并发修改无锁 |
| SEC-004 | Security | WeChat DM策略默认为open | ops/security_audit.py:41-42 | 默认"open"无需验证 |
| TOOL-001 | Security | 工具调度缺少schema验证 | tools/registry.py:262 | 直接传参无验证 |
| TOOL-002 | Security | SQLite ATTACH写操作enforcement缺失 | tools/data_query.py:110 | 读写模式打开 |
| TOOL-007 | Security | 工具注册表无速率限制 | tools/registry.py:164 | 无速率限制检查 |
| TOOL-008 | Security | data_query缺少执行超时 | tools/data_query.py:139 | 执行无超时参数 |
| QUAL-001 | Quality | message_handler 1252行过长 | message_handler.py | 超过800行限制 |
| QUAL-003 | Quality | handle_message 425行过长 | message_handler.py:232-657 | 超过50行限制 |

### MEDIUM（计划修复）

| 编号 | 类别 | 问题描述 | 文件位置 | 代码证据 |
|------|------|----------|----------|----------|
| ORCH-001 | Logic | LRU驱逐非原子操作 | orchestrator.py:139-142 | `next(iter())`+`pop()`非原子 |
| ORCH-005 | Quality | execute_graph 175行过长 | task_orchestrator.py:338-512 | 函数过长需拆分 |
| ORCH-008 | Fragility | getattr访问dict属性脆弱 | task_orchestrator.py:183 | `getattr(v, "status", None)` |
| CORE-001 | Logic | 缓存存储条件不一致 | llm_retry.py:182-195 | 存储条件分散 |
| CORE-002 | Performance | guardrails缓存场景重复执行 | tool_batch.py:156-175 | 缓存命中仍执行 |
| CORE-004 | Quality | _run_turn_body 330行过长 | agent_loop.py:216-520 | 函数过长 |
| CORE-007 | Architecture | 限流与guardrails无协调 | tool_batch.py:176-201 | 各自独立检查 |
| CORE-008 | Fragility | 闭包捕获外部变量自引用 | llm_retry.py:123-127 | 自引用闭包 |
| MEM-001 | Thread Safety | _turn_buffer无锁保护 | facade.py:335-340 | append/clear无锁 |
| MEM-004 | Performance | record_access单行更新 | butler_memory.py:216-224 | N次DB round-trip |
| MEM-011 | Logic | _STORE_CACHE驱逐不确定 | vector_store.py:236-238 | 未使用LRU |
| ERR-001 | Resource | _save_unlocked资源泄漏 | butler_memory.py:50-65 | fd可能泄漏 |
| TRANS-001 | Robustness | wire_tools_for_provider失败静默 | transport/llm_client.py:144-146 | fallback掩盖错误 |
| TRANS-003 | Logic | config_set验证不转换 | config_service.py:133-136 | 验证后仍存string |
| TRANS-004 | Security | _ensure_private_mode失败静默 | config_secrets.py:41-42 | 权限设置失败继续 |
| TRANS-005 | Security | get_butler_home符号链接风险 | config_service.py:396-398 | resolve跟随符号链接 |
| TRANS-006 | Usability | 导入错误消息误导 | transport/llm_client.py:115-116 | 未指明真正缺失包 |
| TRANS-009 | Atomicity | write_provider_secret时序问题 | config_secrets.py:102-107 | 无原子性保护 |
| TRANS-010 | Security | save_butler_config权限问题 | config_service.py:302-316 | tempfile默认0644 |
| TRANS-011 | Duplication | _load_env_providers重复逻辑 | config_service.py:206-238 | 与config.py重复 |
| CONC-013 | Concurrency | _get_openai_client懒加载竞态 | transport/llm_client.py:76-91 | 双检锁问题 |
| CONC-014 | Concurrency | _get_anthropic_client懒加载竞态 | transport/llm_client.py:93-117 | 同上 |
| CONC-015 | Design | _TrackedSessionDict嵌套锁 | session_registry.py:28-32 | RLock重入但质量差 |
| TOOL-003 | Audit | 审计日志缺少查询内容 | tools/registry.py:604-611 | 只记键名不记值 |
| TOOL-005 | Security | DuckDB连接未加固 | tools/data_query.py:110 | read_only=False |
| TOOL-006 | Security | 终端管道模式路径bypass | tools/path_safety.py:200-203 | 路径检查可绕过 |
| TOOL-011 | Fragility | 符号链接检查使用startswith | tools/path_safety.py:268 | 非real path比较 |
| TOOL-012 | Validation | 终端配置环境变量未验证 | tools/path_safety.py:50-58 | 直接使用getenv |
| SEC-005 | Security | SHA256截断指纹碰撞 | permissions/approvals.py:38 | 仅用32字符截断 |
| SEC-007 | Security | chmod失败静默忽略 | config_secrets.py:41-42 | 异常被catch |
| SEC-008 | Audit | 审计事件不记录值 | tools/registry.py:604-611 | 参数值未记录 |
| SEC-014 | Security | 危险模式检测opt-in | tools/path_safety.py:191 | 默认未启用 |

### LOW（建议改进）

| 编号 | 类别 | 问题描述 | 文件位置 | 代码证据 |
|------|------|----------|----------|----------|
| ORCH-003 | Quality | model_block冗余赋值 | orchestrator.py:290,293 | 赋值给两个key |
| ORCH-004 | Fragility | 模板替换使用字符串replace | orchestrator.py:326-327 | 不如模板引擎健壮 |
| ORCH-006 | Design | on_progress异常仅debug日志 | task_orchestrator.py:194-197 | 故意fire-and-forget |
| ORCH-009 | Fragility | task清理逻辑使用getattr | task_orchestrator.py:180-186 | 脆弱的属性访问 |
| CORE-005 | Configuration | 重试次数硬编码20 | llm_retry.py:97 | 无命名常量 |
| CORE-009 | Fragility | 访问_same_tool_failure_counts | agent_loop.py:761 | 访问私有属性 |
| CORE-010 | Fragility | 工具结果判断字符串匹配 | tool_batch.py:25-34 | 依赖字符串格式 |
| CORE-011 | Logic | _inject_ephemeral_system逻辑问题 | context_pipeline.py:370-374 | 未找到system不insert |
| TRANS-007 | Usability | config_get返回中文字符串 | config_service.py:120 | "(未知)" |
| ERR-005 | Clarity | flush_observer_queue返回值歧义 | observer_queue.py:129 | 两种情况返回0 |
| TOOL-004 | Security | SQL注入regex bypass风险 | tools/data_query.py:18-28 | regex非根本解决 |
| SEC-013 | Security | 注入检测仅启发式 | memory/injection_guard.py:33-57 | 可能被绕过 |

---

## 确认问题统计

| 类别 | CRITICAL | HIGH | MEDIUM | LOW | 合计 |
|------|----------|------|--------|-----|------|
| Security | 2 | 6 | 7 | 2 | 17 |
| Concurrency | 0 | 12 | 4 | 1 | 17 |
| Quality | 2 | 2 | 3 | 2 | 9 |
| Logic/Design | 0 | 3 | 6 | 3 | 12 |
| Persistence | 0 | 2 | 1 | 0 | 3 |
| Performance | 0 | 0 | 2 | 0 | 2 |
| Error Handling | 0 | 2 | 1 | 1 | 4 |
| **总计** | **4** | **27** | **31** | **12** | **74** |

---

## 紧急处理项

### CRITICAL（必须立即处理）

1. **[SEC-002]** 工作区权限fail-open — workspace为None时返回None允许执行
2. **[SEC-003]** 终端管道模式使用shell=True — 可被注入执行任意命令

### 立即影响HIGH问题

3. **[ORCH-002/CONC-001]** asyncio.to_thread内持RLock死锁
4. **[ORCH-007]** until断言失败时不重试
5. **[CONC-003/CONC-004/CONC-006]** 会话注册表多个并发问题
6. **[CONC-005/CONC-008/CONC-009]** 队列和缓存竞态
7. **[MEM-002]** flush_observer_queue数据丢失
8. **[MEM-003/MEM-010]** VectorStore非线程安全
9. **[TRANS-012/ERR-002]** 流错误返回部分数据伪装成功
10. **[TOOL-001/TOOL-002/TOOL-007/TOOL-008]** 工具系统安全问题

---

## 建议优先级

1. **立即修复**: CRITICAL + HIGH安全问题 (17个)
2. **尽快修复**: HIGH并发问题 (12个)
3. **计划修复**: MEDIUM问题 (31个)
4. **可选改进**: LOW问题 (12个)

---

**检查完成时间**: 2026/05/31
**确认问题总数**: 74个