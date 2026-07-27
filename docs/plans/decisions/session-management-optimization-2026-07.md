# Session 管理优化计划（2026-07）

## 现状分析

### 当前架构

```
会话生命周期
    │
    ├─→ new_session.py          # /new 边界：清理、格式化、快照
    │       └─→ clear_session_boundary_memory()
    │
    ├─→ lifecycle.py            # 共享边界钩子：turn 内存同步
    │       └─→ sync_turn_memory()
    │
    ├─→ memory_prefetch.py      # 每轮内存预取、注入、缓存
    │       └─→ prefetch_turn_memory()
    │       └─→ inject_turn_memory()
    │       └─→ build_memory_pre_llm_transform()
    │
    └─→ post_session.py         # 会话结束后双通道提取
            └─→ PostSessionProcessor.process()
```

### 识别的问题

#### 1. 循环依赖问题（高优先级）

**问题描述**：`memory_prefetch.py` 与 `memory/diagnostics.py` 存在间接循环依赖：

```
memory_prefetch.py:64 → from butler.memory.diagnostics import _resolve_project_memory
                     ↑
                     │
memory/diagnostics.py:19 → from butler.session.lifecycle import CONVERSATION_CATEGORY
                     ↑
                     │
session/lifecycle.py:192 → from butler.session import memory_prefetch as _mp
```

**当前 workaround**：将 `_resolve_project_memory` 的导入放在函数内部（第 64 行），这只是临时解决方案，不是根本修复。

**影响**：
- 代码结构不够清晰，维护困难
- 延迟导入增加了运行时错误的可能性
- 测试时难以 mock 和隔离

#### 2. 会话生命周期管理不完善（高优先级）

**问题描述**：当前的 `lifecycle.py` 主要处理 turn 级别的内存同步，缺少完整的会话生命周期管理：

- 缺少会话创建时的初始化钩子
- 缺少会话运行期间的状态监控
- 缺少会话销毁时的资源清理（ChromaDB 连接、SQLite 句柄、后台线程）

**影响**：
- 资源泄漏风险（特别是 ChromaDB 连接）
- 会话异常终止时可能丢失数据
- 无法跟踪会话的完整状态变化

#### 3. 状态持久化和恢复机制不足（中优先级）

**问题描述**：`new_session.py` 的 `write_session_summary_snapshot()` 只保存了基本的会话摘要，缺少：

- 对话状态（ConversationState）的完整持久化
- 会话中断后的恢复机制
- 会话状态的版本管理

**影响**：
- 会话意外中断后无法恢复
- 跨会话的上下文连续性不足

#### 4. post_session 与新优化模块的兼容性（中优先级）

**问题描述**：`post_session.py`（16KB）包含复杂的双路提取逻辑，但与 P1 阶段新增的经验写入逻辑可能存在冲突：

- `post_session.py` 的 `_persist_experience_memory()` 写入 experience
- `agent_loop/` 的经验写入也写入 experience
- 可能导致重复写入或不一致

**影响**：
- 经验数据重复
- 内存存储效率低下

## 优化目标

### 短期目标（P0）
1. **解决循环依赖**：通过接口抽象或依赖反转从根本上解决 `memory_prefetch` ↔ `diagnostics` 的循环依赖
2. **增强资源清理**：在会话销毁时确保 ChromaDB 连接、SQLite 句柄、后台线程正确释放
3. **统一经验写入**：协调 `post_session.py` 和 `agent_loop/` 的经验写入逻辑

### 中期目标（P1）
1. **完善生命周期管理**：创建统一的会话生命周期管理模块，覆盖创建→运行→销毁全流程
2. **增强状态持久化**：实现对话状态的完整持久化和恢复机制

### 长期目标（P2）
1. **会话状态版本管理**：实现会话状态的版本控制和回滚机制
2. **会话迁移**：支持会话在不同实例间迁移

## 详细方案

### P0-1: 循环依赖根本修复

**策略**：通过接口抽象解耦 `memory_prefetch` 和 `diagnostics`

**修改文件**：

1. **`butler/memory/diagnostics.py`**
   - 将 `_resolve_project_memory` 函数移动到 `butler/memory/facade.py` 或新建 `butler/memory/project_resolver.py`
   - `diagnostics.py` 改为调用新位置的函数

2. **`butler/session/memory_prefetch.py`**
   - 从新位置导入 `_resolve_project_memory`，移除延迟导入模式

3. **`butler/session/lifecycle.py`**
   - 检查是否存在其他循环依赖点

**代码结构变化**：

```
# 优化前
session/memory_prefetch.py → memory/diagnostics.py → session/lifecycle.py → session/memory_prefetch.py

# 优化后
session/memory_prefetch.py → memory/facade.py (无反向依赖)
memory/diagnostics.py → memory/facade.py (无反向依赖)
```

### P0-2: 资源清理增强

**策略**：在 `new_session.py` 的 `clear_session_boundary_memory()` 中添加资源清理逻辑

**修改文件**：

1. **`butler/session/new_session.py`**
   - 在 `clear_session_boundary_memory()` 中添加：
     - ChromaDB 连接池清理
     - SQLite 连接关闭
     - 后台线程停止（prefetch_warm 等）
     - 缓存清理（prefetch_cache、tool_result_cache）

2. **`butler/memory/vector_store.py`**
   - 添加 `close()` 方法用于显式关闭连接

3. **`butler/memory/semantic_memory.py`**
   - 添加 `close()` 方法用于显式关闭连接

**代码示例**：

```python
# new_session.py - clear_session_boundary_memory() 增强
def clear_session_boundary_memory(orchestrator, session_id=""):
    # ... 现有逻辑 ...
    
    # 新增：资源清理
    from butler.session.new_session_ops import (
        close_chromadb_connections_safe,
        close_sqlite_connections_safe,
        stop_background_threads_safe,
    )
    
    close_chromadb_connections_safe()
    close_sqlite_connections_safe(session_id)
    stop_background_threads_safe(session_id)
    
    return {"removed": removed, "session_tag": tag}
```

### P0-3: 统一经验写入

**策略**：创建经验写入的统一入口，避免重复写入

**修改文件**：

1. **`butler/memory/experience/writer.py`**
   - 增强 `write()` 方法，添加去重逻辑
   - 添加 `batch_write()` 方法支持批量写入

2. **`butler/session/post_session.py`**
   - 修改 `_persist_experience_memory()` 使用 `ExperienceWriter` 的去重功能

3. **`butler/core/agent_loop/`**
   - 修改经验写入逻辑使用同一 `ExperienceWriter` 实例

**代码示例**：

```python
# experience/writer.py - 增强去重
def write(self, query, result, metadata=None):
    # 检查是否已存在相同内容
    if self._is_duplicate(query, result):
        logger.debug("Skipping duplicate experience: %s", query[:50])
        return None
    
    # ... 现有写入逻辑 ...
```

### P1-1: 完善生命周期管理

**策略**：创建 `SessionLifecycleManager` 类统一管理会话生命周期

**新增文件**：

1. **`butler/session/lifecycle_manager.py`**（新建）
   - `SessionLifecycleManager` 类
   - 方法：`create_session()`、`start_session()`、`end_session()`、`destroy_session()`
   - 钩子系统：`on_session_create`、`on_session_start`、`on_session_end`、`on_session_destroy`

**修改文件**：

1. **`butler/session/lifecycle.py`**
   - 将 `sync_turn_memory()` 集成到 `SessionLifecycleManager`
   - 保留向后兼容的导出

2. **`butler/session/new_session.py`**
   - 使用 `SessionLifecycleManager` 管理 `/new` 边界

3. **`butler/session/post_session.py`**
   - 使用 `SessionLifecycleManager` 管理会话结束

**架构变化**：

```
SessionLifecycleManager
    │
    ├─→ create_session()      # 创建会话（初始化状态）
    ├─→ start_session()       # 开始会话（注册钩子）
    ├─→ sync_turn()           # 同步单轮（现有 sync_turn_memory）
    ├─→ end_session()         # 结束会话（运行 post-session 提取）
    └─→ destroy_session()     # 销毁会话（资源清理）
```

### P1-2: 增强状态持久化

**策略**：扩展 `write_session_summary_snapshot()`，添加完整的对话状态持久化

**修改文件**：

1. **`butler/session/new_session.py`**
   - 增强 `write_session_summary_snapshot()`：
     - 保存完整的 `ConversationState`
     - 保存最近的会话消息摘要
     - 添加时间戳和版本号

2. **`butler/core/conversation_state.py`**
   - 添加 `serialize()` 和 `deserialize()` 方法

3. **`butler/session/memory_prefetch.py`**
   - 添加 `restore_session_context()` 方法用于恢复会话上下文

**代码示例**：

```python
# conversation_state.py - 序列化/反序列化
def serialize(self) -> dict:
    return {
        "version": "1.0",
        "turn_summaries": [ts.serialize() for ts in self.turn_summaries],
        "file_changes": self.file_changes,
        "chapter_summaries": self.chapter_summaries,
        "timestamp": datetime.now().isoformat(),
    }

@classmethod
def deserialize(cls, data: dict) -> "ConversationState":
    state = cls()
    # ... 反序列化逻辑 ...
    return state
```

## 优先级排序

| 优先级 | 优化项 | 复杂度 | 影响范围 | 预期收益 |
|--------|--------|--------|----------|----------|
| P0-1 | 循环依赖根本修复 | 低 | 中 | 代码结构清晰，消除运行时风险 |
| P0-2 | 资源清理增强 | 低 | 中 | 避免资源泄漏，提升稳定性 |
| P0-3 | 统一经验写入 | 中 | 中 | 减少重复数据，提升存储效率 |
| P1-1 | 完善生命周期管理 | 高 | 高 | 统一管理，便于扩展 |
| P1-2 | 增强状态持久化 | 中 | 中 | 支持会话恢复，提升可靠性 |

## 实施计划

### 第一阶段：P0 修复（预计 1-2 天）

1. **循环依赖修复**（半天）
   - 移动 `_resolve_project_memory` 到 `memory/facade.py`
   - 更新 `memory_prefetch.py` 和 `diagnostics.py` 的导入

2. **资源清理增强**（半天）
   - 在 `vector_store.py` 和 `semantic_memory.py` 添加 `close()` 方法
   - 增强 `new_session.py` 的清理逻辑

3. **统一经验写入**（1天）
   - 增强 `ExperienceWriter` 的去重功能
   - 协调 `post_session.py` 和 `agent_loop/` 的写入

### 第二阶段：P1 增强（预计 2-3 天）

1. **生命周期管理器**（1天）
   - 创建 `SessionLifecycleManager` 类
   - 集成现有生命周期逻辑

2. **状态持久化增强**（1-2天）
   - 添加 `ConversationState` 序列化/反序列化
   - 扩展会话快照功能

## 风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 循环依赖修复引入新问题 | 低 | 高 | 充分测试，保留向后兼容导出 |
| 资源清理导致连接问题 | 中 | 中 | 使用 safe_best_effort 模式 |
| 统一经验写入导致数据丢失 | 低 | 高 | 添加写入日志和验证 |
| 生命周期重构影响现有流程 | 中 | 高 | 渐进式重构，保持接口兼容 |

## 验证方案

### P0-1 验证
- 运行 `bash scripts/butler-layer-import-gate.sh` 确认无循环依赖
- 运行 `PYTHONPATH=. python3 -c "from butler.session.memory_prefetch import prefetch_turn_memory"` 确认导入正常

### P0-2 验证
- 运行会话后检查资源占用（内存、线程数）
- 测试 `/new` 命令后资源是否释放

### P0-3 验证
- 运行包含工具调用的会话
- 检查经验树中是否有重复条目

### P1-1 验证
- 测试完整会话生命周期（创建→运行→结束→销毁）
- 验证钩子系统正常工作

### P1-2 验证
- 测试会话中断后恢复功能
- 验证会话快照文件内容完整

## 后续工作

完成本计划后，建议继续以下优化方向：

1. **会话状态版本管理**：实现会话状态的版本控制和回滚机制
2. **会话迁移**：支持会话在不同实例间迁移
3. **会话监控**：添加会话级别的监控指标和告警

---

**文档状态**：草案  
**创建日期**：2026-07-16  
**最后更新**：2026-07-16  
**负责人**：claude-code
