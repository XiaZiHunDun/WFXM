# WFXM Agent Loop 主要流程优化计划

> 版本: v1.0 | 日期: 2026-07-16 | 状态: 规划阶段

## 1. 现状分析

### 1.1 当前架构

```
用户消息 → Gateway → AgentLoop.run() → _run_turn_body()
                                              │
                      ┌───────────────────────┼───────────────────────┐
                      ▼                       ▼                       ▼
              _phase_init()            _phase_call_llm()       _phase_dispatch_tools()
                      │                       │                       │
                      ▼                       ▼                       ▼
            _prepare_user_message()     LLM API调用            _process_tool_calls()
                      │                                           │
              ┌───────┴───────┐                          ┌──────────┴──────────┐
              ▼               ▼                          ▼                     ▼
    _phase_resolve_user_text()  _phase_enrich_user_text()  工具执行         文本响应
              │               │                          │                     │
              ▼               ▼                          ▼                     ▼
         消息清理         select_tools_for_context()    dispatch_tool()     输出处理
```

### 1.2 问题识别

| 问题 | 现状 | 影响 | 优先级 |
|------|------|------|--------|
| 工具选择无经验指导 | `select_tools_for_context()` 仅基于关键词+语义，不从经验树学习 | 无法利用历史成功经验指导工具选择 | 高 |
| 上下文压缩无语义感知 | 压缩时只保护system+尾部，不考虑语义相关性 | 重要上下文可能被压缩掉 | 高 |
| 预回合无经验注入 | 只有会话状态提醒，无跨会话经验注入 | 无法利用历史项目经验 | 中 |
| 对话状态与经验树割裂 | ConversationState和ExperienceTree并行，无桥接 | 经验积累无法反馈到对话 | 中 |
| 工具执行无智能优化 | 每次调用都重新执行，无缓存/去重 | 重复调用浪费资源 | 中 |

### 1.3 技术债务

```
registry.py ←→ tool_service.py 循环依赖 (已修复，但需重新设计集成方式)
```

## 2. 优化目标

建立智能化的 Agent Loop 流程，实现：
1. 基于经验的工具选择
2. 语义感知的上下文压缩
3. 预回合经验注入
4. 对话状态与经验树桥接

## 3. 优化方案

### 3.1 架构设计

```
用户消息
  │
  ▼
┌─────────────────────────────────────────────────┐
│  Pre-Turn Phase (新增)                           │
│  ├── 经验检索 (ExperienceTree.retrieve())        │
│  ├── 领域路由 (DomainRouter.route())             │
│  └── 经验注入 (ephemeral_system)                 │
└─────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────┐
│  Phase Init                                      │
│  ├── _phase_resolve_user_text()                  │
│  └── _phase_enrich_user_text()                   │
│      └── 智能工具选择 (ToolService.recommend_tools)│
└─────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────┐
│  Phase Call LLM                                  │
│  ├── 语义感知压缩 (context_compressor + 记忆)      │
│  └── LLM API调用                                 │
└─────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────┐
│  Phase Dispatch Tools                            │
│  └── 工具执行 (带优化: 缓存/去重/监控)            │
└─────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────┐
│  Post-Turn Phase (增强)                           │
│  ├── 经验写入 (ExperienceTree.write())           │
│  ├── 对话状态更新                                 │
│  └── 经验树桥接                                   │
└─────────────────────────────────────────────────┘
```

### 3.2 Phase 1: 智能工具选择集成

**目标**: 在 `_phase_enrich_user_text` 中集成基于经验的工具推荐

**集成点**: `butler/core/agent_loop_phases.py` → `_phase_enrich_user_text()`

**方案**:
```python
# 现有逻辑: select_tools_for_context(keywords + semantic)
# 新增逻辑: ToolService.recommend_tools() → 经验+语义+分类

def _phase_enrich_user_text(loop, user_content, steer_session):
    turn_tools = list(loop.tools or [])
    
    # 新增: 从ToolService获取推荐工具
    try:
        from butler.tools.tool_service import recommend_tools
        recommended = recommend_tools(user_content, top_k=10)
        recommended_names = {rec["tool_name"] for rec in recommended if rec["score"] > 0.3}
        
        # 将推荐工具加入pinned
        if recommended_names:
            skill_preferred_tools = skill_preferred_tools or set()
            skill_preferred_tools |= recommended_names
            loop.diagnostics["experience_recommended_tools"] = len(recommended_names)
    except Exception:
        pass
    
    # 原有逻辑继续
    selected, sel_diag = select_tools_for_context(
        tools,
        user_hint=user_content,
        skill_preferred_tools=skill_preferred_tools,
    )
```

**文件变更**:
- `butler/core/agent_loop_phases.py` - 修改 `_phase_enrich_user_text()`

### 3.3 Phase 2: 语义感知上下文压缩

**目标**: 在上下文压缩时，利用语义记忆判断哪些内容重要

**集成点**: `butler/core/context_compressor.py` → `compress_messages()`

**方案**:
```python
def compress_messages(messages, ...):
    # 原有逻辑: 保护system + 尾部N条 + 摘要中间
    
    # 新增: 语义相关性检测
    try:
        from butler.memory.experience.tree import get_experience_tree
        tree = get_experience_tree()
        
        # 获取最近用户消息作为查询
        last_user_msg = None
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break
        
        if last_user_msg:
            # 检索相关经验
            hits = tree.retrieve(last_user_msg, top_k=5)
            relevant_topics = {hit.node.domain for hit in hits}
            
            # 在压缩时，保留与相关领域匹配的消息
            for msg in messages:
                if _message_relevant_to_topics(msg, relevant_topics):
                    # 标记为保护
                    pass
    except Exception:
        pass
    
    # 原有压缩逻辑继续
```

**文件变更**:
- `butler/core/context_compressor.py` - 修改 `compress_messages()`

### 3.4 Phase 3: 预回合经验注入

**目标**: 在回合开始前，从经验树检索相关经验并注入到ephemeral_system

**集成点**: `butler/core/agent_loop.py` → `_build_turn_ephemeral_system()`

**方案**:
```python
def _build_turn_ephemeral_system(self, ephemeral_system):
    parts = []
    
    # 原有逻辑: conversation_state提醒
    if self._conversation_state:
        reminder = build_conversation_reminder(self._conversation_state, token_budget=2000)
        if reminder:
            parts.append(reminder)
    
    # 新增: 经验树检索
    try:
        from butler.memory.experience.tree import get_experience_tree
        from butler.memory.experience.domain_router import DomainRouter
        
        # 获取最近用户消息
        if self._messages:
            last_msg = self._messages[-1]
            if last_msg.get("role") == "user":
                query = last_msg.get("content", "")
                
                # 路由到领域
                router = DomainRouter()
                domain_id, confidence = router.route(query)
                
                if confidence > 0.5:
                    # 检索该领域的相关经验
                    tree = get_experience_tree()
                    hits = tree.retrieve(query, top_k=3)
                    
                    # 构建经验注入文本
                    experience_injection = _build_experience_injection(hits)
                    if experience_injection:
                        parts.append(experience_injection)
                        self.diagnostics["experience_injected"] = len(hits)
    except Exception as e:
        logger.debug("Experience injection failed: %s", e)
    
    if ephemeral_system:
        parts.insert(0, str(ephemeral_system))
    
    if not parts:
        return None
    return "\n\n".join(parts)
```

**文件变更**:
- `butler/core/agent_loop.py` - 修改 `_build_turn_ephemeral_system()`

### 3.5 Phase 4: 对话状态与经验树桥接

**目标**: 在回合结束后，将对话结果写入经验树

**集成点**: `butler/core/agent_loop.py` → `_update_conversation_state()`

**方案**:
```python
def _update_conversation_state(self, user_message, result):
    # 原有逻辑: 更新conversation_state
    
    # 新增: 写入经验树
    try:
        from butler.memory.experience.tree import get_experience_tree
        from butler.memory.experience.domain_router import DomainRouter
        
        tree = get_experience_tree()
        router = DomainRouter()
        
        # 路由领域
        domain_id, confidence = router.route(user_message)
        
        # 获取工具调用详情
        diag = result.diagnostics if result.diagnostics else {}
        tool_calls_detail = diag.get("tool_calls_detail", [])
        
        # 提取关键信息
        tools_used = [tc.get("name") for tc in tool_calls_detail]
        success = result.status == LoopStatus.COMPLETED
        
        # 构建经验内容
        experience_content = f"任务: {user_message[:200]}\n"
        if tools_used:
            experience_content += f"使用工具: {', '.join(tools_used)}\n"
        experience_content += f"结果: {'成功' if success else '失败'}"
        if result.final_response:
            experience_content += f"\n摘要: {result.final_response[:300]}"
        
        # 写入经验树
        tree.write(
            query=user_message,
            result=experience_content,
            metadata={
                "domain": domain_id,
                "category": "recent_conversations",
                "tools_used": tools_used,
                "success": success,
                "turn_count": self._turn_count,
            },
        )
        
        self.diagnostics["experience_written"] = True
        
    except Exception as e:
        logger.debug("Failed to write experience: %s", e)
```

**文件变更**:
- `butler/core/agent_loop.py` - 修改 `_update_conversation_state()`

### 3.6 Phase 5: 工具执行优化（重新设计）

**目标**: 在工具执行层面添加缓存和监控，但避免循环依赖

**方案**: 将优化逻辑放在 `tool_service.py` 的 `execute_tool` 中，让外部调用者使用 ToolService 而非直接调用 registry

```python
# tool_service.py
def execute_tool(self, tool_name, args, handler=None):
    # 如果没有handler，直接调用registry.dispatch_tool
    # 由于registry不再调用ToolService，不会有循环依赖
    
    if handler is None:
        from butler.tools.registry import dispatch_tool
        result = dispatch_tool(tool_name, args)
    else:
        # 使用handler执行，并应用优化
        cached = self._optimizer.check_cache(tool_name, args)
        if cached is not None:
            return cached, {"cached": True}
        
        # 去重检测
        if self._optimizer.check_duplicate(tool_name, args):
            return '{"ok": false, "code": "DUPLICATE_BLOCKED"}', {"blocked": True}
        
        result = handler()
        self._optimizer.set_cache(tool_name, args, result)
    
    # 记录指标
    self._metrics.record(tool_name, ...)
    return result, {"cached": False}
```

**集成方式**: 在 agent_loop.py 的 `_dispatch_tool` 中使用 ToolService

```python
def _dispatch_tool(self, name, args):
    def _inner(n, a):
        # 使用ToolService执行，带优化和监控
        try:
            from butler.tools.tool_service import get_tool_service
            service = get_tool_service()
            result, meta = service.execute_tool(n, a)
            return result
        except Exception:
            # 降级到直接调用
            return cast(str, dispatch_tool_with_envelope(self.tool_dispatcher, n, a))
    
    with self._tool_execution_context():
        return cast(str, self._plugins.wrap_tool_call(name, args, _inner))
```

**文件变更**:
- `butler/tools/tool_service.py` - 修改 `execute_tool()`
- `butler/core/agent_loop.py` - 修改 `_dispatch_tool()`

## 4. 优先级排序

| 优先级 | 优化项 | 预期收益 | 复杂度 |
|--------|--------|----------|--------|
| P0 | 智能工具选择集成 | 工具选择准确率提升30% | 低 |
| P0 | 工具执行优化 | 重复调用减少10%，响应时间降低15% | 低 |
| P1 | 预回合经验注入 | 上下文相关性提升，减少重复提问 | 中 |
| P1 | 对话状态与经验树桥接 | 经验积累加速，跨会话知识复用 | 中 |
| P2 | 语义感知上下文压缩 | 重要上下文保留率提升20% | 高 |

## 5. 实施计划

### 5.1 第一阶段（P0）

| 任务 | 描述 | 依赖 |
|------|------|------|
| 1 | 修改 `_phase_enrich_user_text` 集成工具推荐 | ToolService |
| 2 | 修改 `_dispatch_tool` 使用 ToolService | tool_service.py |
| 3 | 更新 `tool_service.execute_tool` 支持registry调用 | 无 |
| 4 | 添加测试用例 | 无 |

### 5.2 第二阶段（P1）

| 任务 | 描述 | 依赖 |
|------|------|------|
| 1 | 修改 `_build_turn_ephemeral_system` 添加经验注入 | ExperienceTree |
| 2 | 修改 `_update_conversation_state` 添加经验写入 | ExperienceTree |
| 3 | 添加测试用例 | 无 |

### 5.3 第三阶段（P2）

| 任务 | 描述 | 依赖 |
|------|------|------|
| 1 | 修改 `context_compressor.compress_messages` 添加语义感知 | ExperienceTree |
| 2 | 添加测试用例 | 无 |

## 6. 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 经验注入增加token消耗 | 每个回合增加~500 tokens | 限制注入条数和长度 |
| 语义检索增加延迟 | 每次检索增加~50ms | 异步检索，超时降级 |
| 经验树写入失败 | 经验丢失 | try/except包装，日志记录 |
| 工具推荐质量不佳 | 推荐错误工具 | 可配置开关，支持回退到原有逻辑 |

## 7. 验证方案

### 7.1 功能验证

| 验证项 | 方法 | 预期结果 |
|--------|------|----------|
| 工具推荐集成 | 发送"读取文件"查询，检查diagnostics | `experience_recommended_tools > 0` |
| 经验注入 | 发送与历史任务相关的查询 | `experience_injected > 0` |
| 经验写入 | 完成一个工具调用后检查经验树 | 新节点写入成功 |
| 工具缓存 | 连续两次调用read_file | 第二次返回缓存结果 |

### 7.2 性能验证

| 指标 | 方法 | 预期提升 |
|------|------|----------|
| 工具选择准确率 | 人工评估推荐结果 | +30% |
| 缓存命中率 | 运行测试套件 | >30% |
| 响应时间 | 对比优化前后 | -15% |

## 8. 代码清单

```
butler/core/
├── agent_loop.py              # 修改: _build_turn_ephemeral_system, _update_conversation_state, _dispatch_tool
├── agent_loop_phases.py       # 修改: _phase_enrich_user_text
├── context_compressor.py      # 修改: compress_messages
└── tool_selector.py           # 保持不变（新增逻辑在ToolService）

butler/tools/
├── tool_service.py            # 修改: execute_tool
├── experience_selector.py     # 保持不变
├── tool_taxonomy.py           # 保持不变
├── tool_discovery.py          # 保持不变
├── tool_call_optimizer.py     # 保持不变
├── tool_metrics.py            # 保持不变
└── registry.py                # 保持不变（已移除循环依赖代码）

tests/
├── test_agent_loop_intelligence.py  # 新增: 智能工具选择、经验注入、经验写入测试
```

## 9. 总结

本计划针对 WFXM Agent Loop 的主要流程进行优化，核心改进包括：

1. **智能工具选择** - 从经验树学习，提升工具选择准确率
2. **语义感知压缩** - 利用记忆判断上下文重要性
3. **预回合经验注入** - 跨会话知识复用
4. **经验树桥接** - 对话结果自动积累为经验
5. **工具执行优化** - 缓存、去重、监控

所有优化均采用 `safe_best_effort` 模式，失败时自动降级到原有逻辑，确保系统稳定性。