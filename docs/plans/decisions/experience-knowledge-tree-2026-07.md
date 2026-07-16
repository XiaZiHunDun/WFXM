# 经验-知识二层管理机制设计文档

> 版本: v1.0 | 日期: 2026-07-15 | 状态: 设计阶段

## 1. 背景与问题分析

### 1.1 现状

WFXM (Butler v4) 当前记忆/工具体系存在以下问题：

| 问题 | 现状 | 影响 |
|------|------|------|
| 经验无分类 | `unified_recall.py` 做 experience+project+coding 三路混合检索，但经验本身无领域归属 | skill 一多就产生混乱，类似 Claude Code 的问题 |
| 图谱与三元组割裂 | `triplets.py`(旧) 和 `knowledge_graph.py`(新) 两套并行 | 三元组只做展示，图谱只在 chapter_summary 时写入，不参与推理路由 |
| 工具选择无经验指导 | `skill_tool_bridge.py` 从注入文本中提取 preferred_tools，不从历史经验中学习 | 每次都从零开始选择工具，不利用成功经验 |
| 新经验无法融入 | 新 skill/tool 接入后，产生的经验没有自动归类机制 | 经验堆积无序，越用越乱 |

### 1.2 目标

建立一个 **树型经验-知识管理机制**：

```
推理请求
  │
  ▼
┌─────────────┐     命中     ┌─────────────┐
│  经验层查找  │ ──────────▶ │  使用经验   │
│  (Layer 1)  │              │  指导推理   │
└──────┬──────┘              └─────────────┘
       │ 未命中
       ▼
┌─────────────┐              ┌─────────────┐
│  工具层查找  │ ──────────▶ │  调用工具   │
│  (Layer 2)  │              │  执行任务   │
└─────────────┘              └──────┬──────┘
                                    │ 执行完成
                                    ▼
                             ┌─────────────┐
                             │  经验提取    │
                             │  自动归类    │
                             └─────────────┘
```

## 2. 领域划分设计 (Layer 1)

### 2.1 领域 taxonomy

基于 WFXM 的使用场景分析，设计以下 8 个一级领域：

| 领域 ID | 领域名称 | 覆盖场景 | 示例 |
|--------|---------|---------|------|
| `daily_life` | 日常生活 | 用户偏好、习惯、提醒、日程 | "用户喜欢早上9点开始工作" |
| `agent_dev` | Agent 开发 | LLM 编排、prompt 工程、工具集成 | "使用 ReAct 模式时，先 reasoning 再 action" |
| `database` | 数据库使用 | SQL/NoSQL 操作、迁移、性能调优 | "PostgreSQL JSONB 查询用 GIN 索引" |
| `llm_usage` | 大模型使用 | 模型选择、参数调优、prompt 优化 | "DeepSeek 对长文本用 map-reduce 摘要" |
| `network_info` | 网络信息查找 | 搜索策略、信息抽取、事实核查 | "技术文档查询优先用 WebSearch + WebFetch" |
| `dev_ops` | 开发运维 | CI/CD、容器化、监控、部署 | "Docker 多阶段构建减小镜像 40%" |
| `code_engineering` | 代码工程 | 架构设计、重构、测试、代码审查 | "重构前先跑 mypy strict gate" |
| `project_mgmt` | 项目管理 | 需求拆解、进度追踪、优先级排序 | "黑卡交接时必须更新 state.md" |

### 2.2 领域路由器 (DomainRouter)

```
用户输入 → DomainRouter → 领域匹配 → 经验检索
              │
              ├── 关键词匹配（快速，O(1)）
              ├── 语义匹配（准确，~50ms）
              └── 历史频率（自适应，基于访问统计）
```

路由策略：
1. **快速路径**：关键词命中 → 直接路由（<1ms）
2. **语义路径**：关键词未命中 → embedding 相似度（~50ms）
3. **混合路径**：多领域命中 → 按权重排序取 top-2

## 3. 类别划分设计 (Layer 2)

### 3.1 类别 taxonomy

每个领域下统一划分以下 8 个类别：

| 类别 ID | 类别名称 | 存储内容 | 后端选型 | 与现有模块的关系 |
|--------|---------|---------|---------|----------------|
| `skills` | 技能 | 已注册的 Skill 定义、使用经验、触发条件 | SQLite + ChromaDB | 对接 `skill_tool_bridge.py` |
| `tools` | 工具 | 已注册的 Tool 定义、调用经验、参数模板 | SQLite + ChromaDB | 对接 `tools/registry.py` |
| `mcp` | MCP 服务 | MCP 服务器列表、能力声明、调用记录 | SQLite | 对接 `mcp_self_service.py` |
| `workflows` | 工作流 | 多步骤编排模板、执行经验、检查点 | SQLite + YAML | 对接 `workflow` 模块 |
| `user_profile` | 用户画像 | 偏好、技能水平、工作习惯 | SQLite | 对接 `owner_experience_seed.py` |
| `local_products` | 本地产品 | 已接入的产品实例、配置、使用经验 | SQLite | Redis、Langfuse、ChromaDB 等 |
| `recent_conversations` | 近期对话 | 章节摘要、关键决策、技术栈 | ChromaDB + SQLite | 对接 `conversation_state.py` |
| `knowledge_facts` | 知识事实 | 领域知识点、三元组、最佳实践 | KnowledgeGraph + SQLite | 对接 `triplets.py` + `knowledge_graph.py` |

### 3.2 完整树结构示例

```
experience_tree/
├── daily_life/
│   ├── user_profile/
│   │   └── "用户偏好早上9点工作，使用Python 3.13"
│   ├── recent_conversations/
│   │   └── "2026-07-15 讨论了项目进度安排"
│   └── knowledge_facts/
│       └── "用户时区为 UTC+8"
│
├── agent_dev/
│   ├── skills/
│   │   └── "ReAct 模式: reasoning → action → observation"
│   ├── tools/
│   │   └── "delegate_task 适用于跨模块委派"
│   ├── knowledge_facts/
│   │   └── (FastAPI) —使用→ (Pydantic) —依赖→ (Python 3.13)
│   ├── local_products/
│   │   └── "Langfuse 追踪 turn 级 LLM 调用"
│   └── recent_conversations/
│       └── "实现了四层记忆架构（热/温/冷/图）"
│
├── database/
│   ├── tools/
│   │   └── "terminal 执行 psql -c '...' 查询 PostgreSQL"
│   ├── knowledge_facts/
│   │   └── (PostgreSQL) —支持→ (JSONB) —索引→ (GIN)
│   ├── local_products/
│   │   └── "Redis 用于缓存层，端口 6379"
│   └── workflows/
│       └── "数据库迁移: backup → migrate → verify → rollback_if_fail"
│
├── llm_usage/
│   ├── tools/
│   │   └── "call_llm_with_retry 最多3次，指数退避"
│   ├── knowledge_facts/
│   │   └── "DeepSeek-Coder 适合代码生成，MiniMax 适合中文对话"
│   ├── local_products/
│   │   └── "ChromaDB 本地嵌入，无需 API"
│   └── skills/
│       └── "长文本摘要用 map-reduce: 分段摘要 → 合并"
│
├── network_info/
│   ├── tools/
│   │   └── "WebSearch → WebFetch 链式调用获取网页内容"
│   ├── workflows/
│   │   └── "信息核查: search → fetch → extract → compare → conclude"
│   └── knowledge_facts/
│       └── "技术文档优先查官方文档，再查 Stack Overflow"
│
├── dev_ops/
│   ├── tools/
│   │   └── "terminal: docker build -t ... && docker push ..."
│   ├── workflows/
│   │   └── "CI/CD: lint → test → build → deploy → health_check"
│   ├── local_products/
│   │   └── "Docker registry 在 127.0.0.1:5001"
│   └── knowledge_facts/
│       └── "多阶段构建可减小镜像 40%"
│
├── code_engineering/
│   ├── skills/
│   │   └── "重构前先跑 mypy strict gate"
│   ├── tools/
│   │   └── "butler-pytest-fast-gate.sh: smoke + attach + CC harness"
│   ├── workflows/
│   │   └── "代码审查: read → analyze → feedback → verify"
│   └── knowledge_facts/
│       └── "九层依赖矩阵: 1218文件、0违规基线"
│
└── project_mgmt/
    ├── workflows/
    │   └── "黑卡交接: state.md → shift card → backlog.yaml → commit"
    ├── user_profile/
    │   └── "用户倾向敏捷开发，快速迭代"
    ├── recent_conversations/
    │   └── "Phase 9 完成了记忆架构优化"
    └── knowledge_facts/
        └── "P0/P2/P3 多义 — 见 docs/plans/README.md"
```

## 4. 数据模型设计

### 4.1 核心数据结构

```python
@dataclass
class ExperienceNode:
    """经验树节点"""
    node_id: str               # 唯一标识，如 "agent_dev/tools/delegate_task"
    domain: str                # 领域 ID
    category: str              # 类别 ID
    name: str                  # 节点名称
    node_type: str             # leaf | branch
    content: str               # 经验内容（leaf 节点）
    metadata: dict             # 附加元数据
    embedding_id: str          # ChromaDB 中的 embedding ID
    kg_entity_id: str          # 知识图谱中的实体 ID（如有）
    hit_count: int             # 命中次数
    success_rate: float        # 成功率
    last_used: float            # 最后使用时间戳
    created_at: float
    children: list[str]        # 子节点 ID 列表
```

### 4.2 SQLite Schema

```sql
-- 领域表
CREATE TABLE experience_domains (
    domain_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    keywords TEXT,           -- JSON array: ["agent", "LLM", "prompt"]
    hit_count INTEGER DEFAULT 0,
    created_at REAL NOT NULL
);

-- 类别表
CREATE TABLE experience_categories (
    category_id TEXT PRIMARY KEY,
    domain_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    backend TEXT,             -- sqlite | chromadb | knowledge_graph
    created_at REAL NOT NULL,
    FOREIGN KEY (domain_id) REFERENCES experience_domains(domain_id)
);

-- 经验节点表
CREATE TABLE experience_nodes (
    node_id TEXT PRIMARY KEY,
    domain_id TEXT NOT NULL,
    category_id TEXT NOT NULL,
    name TEXT NOT NULL,
    node_type TEXT DEFAULT 'leaf',   -- leaf | branch
    content TEXT,
    metadata_json TEXT DEFAULT '{}',
    embedding_id TEXT,
    kg_entity_id TEXT,
    hit_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    last_used REAL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (domain_id) REFERENCES experience_domains(domain_id),
    FOREIGN KEY (category_id) REFERENCES experience_categories(category_id)
);

-- 经验关联表（跨领域引用）
CREATE TABLE experience_links (
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    relation TEXT NOT NULL,    -- related_to | depends_on | supersedes
    weight REAL DEFAULT 1.0,
    PRIMARY KEY (source_node_id, target_node_id, relation)
);

-- 索引
CREATE INDEX idx_nodes_domain ON experience_nodes(domain_id);
CREATE INDEX idx_nodes_category ON experience_nodes(category_id);
CREATE INDEX idx_nodes_hit ON experience_nodes(hit_count DESC);
CREATE INDEX idx_nodes_last_used ON experience_nodes(last_used DESC);
```

## 5. 推理路由设计

### 5.1 二层路由流程

```
用户请求
  │
  ▼
┌─────────────────────────────────┐
│ Step 1: DomainRouter.route()    │
│  - 关键词匹配 (8个领域 × 关键词表) │
│  - 语义匹配 (embedding 相似度)    │
│  - 历史频率 (hit_count 加权)     │
│  → 输出: domain_id + confidence  │
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│ Step 2: ExperienceRetriever     │
│  .retrieve(domain, query)       │
│  - 在该领域的8个类别中检索        │
│  - ChromaDB 语义检索             │
│  - KnowledgeGraph 图遍历         │
│  - SQLite 结构化查询             │
│  → 输出: ranked experience list  │
└───────────────┬─────────────────┘
                │
        ┌───────┴───────┐
        │ confidence >  │
        │ 0.7?          │
        ├──── Yes ──────┤──── No ────┐
        ▼               ▼            ▼
┌─────────────┐ ┌─────────────┐ ┌──────────────┐
│ 使用经验    │ │ 经验+工具    │ │ ToolSelector │
│ 指导推理    │ │ 混合模式    │ │ .select()    │
└─────────────┘ └─────────────┘ └──────┬───────┘
                                       │
                                       ▼
                                ┌──────────────┐
                                │ 调用工具执行  │
                                └──────┬───────┘
                                       │
                                       ▼
                                ┌──────────────┐
                                │ ExperienceWriter │
                                │ .write()     │
                                │ - 提取经验   │
                                │ - 自动归类   │
                                │ - 写入树     │
                                └──────────────┘
```

### 5.2 置信度策略

| 置信度 | 范围 | 行为 |
|--------|------|------|
| 高 | > 0.7 | 直接使用经验指导推理，跳过工具选择 |
| 中 | 0.4 - 0.7 | 经验 + 工具混合模式，经验指导工具选择 |
| 低 | < 0.4 | 跳过经验层，直接进入工具层 |

## 6. 与现有模块的集成方案

### 6.1 集成映射

```
新模块                           → 现有模块
─────────────────────────────────────────────
ExperienceTree (新)              → 替代 unified_recall.py 的 experience 部分
  ├── DomainRouter (新)          → 新增，领域路由
  ├── ExperienceRetriever (新)   → 整合 semantic_memory.py + knowledge_graph.py
  ├── ExperienceWriter (新)      → 整合 experience_consolidation.py + triplets.py
  └── ToolSelector (增强)        → 增强 skill_tool_bridge.py
```

### 6.2 数据流

```
agent_loop.py
  │
  ├── 用户消息到达
  │     │
  │     ▼
  │   ExperienceTree.retrieve(query)
  │     ├── DomainRouter → domain_id
  │     ├── ExperienceRetriever → experiences[]
  │     │     ├── SemanticMemory.search() (ChromaDB)
  │     │     ├── KnowledgeGraph.search() (NetworkX)
  │     │     └── SQLite structured query
  │     └── 返回 ranked experiences
  │
  ├── 经验命中 (confidence > 0.7)
  │     → 注入 system_prompt
  │     → 跳过工具选择
  │
  ├── 经验部分命中 (0.4 < confidence < 0.7)
  │     → 注入经验到 system_prompt
  │     → ToolSelector 使用经验指导工具选择
  │
  └── 经验未命中 (confidence < 0.4)
        → ToolSelector.select(tools, query)
        → 执行工具
        → ExperienceWriter.write(执行结果)
              ├── DomainClassifier 自动归类
              ├── TripletExtractor 提取三元组
                                              └── 写入 ExperienceTree
```

### 6.3 不替换的模块

以下模块保持不变，新系统通过调用而非替换来集成：

| 现有模块 | 角色 | 新系统如何调用 |
|---------|------|--------------|
| `semantic_memory.py` | ChromaDB 向量检索 | ExperienceRetriever 调用 |
| `knowledge_graph.py` | NetworkX 图存储 | ExperienceRetriever 调用 |
| `conversation_store.py` | SQLite 会话持久化 | recent_conversations 类别使用 |
| `triplets.py` | 三元组提取 | ExperienceWriter 调用 |
| `tools/registry.py` | 工具注册 | ToolSelector 查询可用工具 |
| `skill_tool_bridge.py` | 技能-工具桥接 | ToolSelector 增强而非替换 |

## 7. 产品选型

### 7.1 存储层选型

| 组件 | 选型 | 理由 | 已安装 |
|------|------|------|--------|
| 结构化存储 | **SQLite** | 零配置、跨平台、支持 JSON | ✅ Python 内置 |
| 向量检索 | **ChromaDB** | 本地部署、自动 embedding、已集成 | ✅ 已安装 |
| 图数据库 | **NetworkX** | 轻量级、纯 Python、SQLite 持久化 | ✅ 已安装 |
| 全文检索 | **SQLite FTS5** | 内置全文索引、无需额外服务 | ✅ Python 内置 |
| 可观测性 | **Langfuse** | LLM 追踪、指标监控 | ⬜ 待安装 |
| 配置管理 | **YAML** | 人类可读、支持注释 | ✅ PyYAML 已安装 |

### 7.2 不选 Neo4j 的理由

| 维度 | Neo4j | NetworkX + SQLite |
|------|-------|-------------------|
| 部署 | 需要独立服务 | 零配置 |
| 性能 (10万节点) | 优秀 | 足够（<100ms 查询） |
| 性能 (百万节点) | 优秀 | 可能需要优化 |
| 运维 | 需要独立管理 | 无额外运维 |
| WFXM 场景 | 过重 | 合适（单机+微信场景） |

**决策**：WFXM 作为微信管家运行在单机上，NetworkX + SQLite 足够。如果未来节点超过 10 万，可迁移到 Neo4j，接口设计兼容。

## 8. 新增模块设计

### 8.1 模块清单

```
butler/memory/experience/
├── __init__.py
├── tree.py              # ExperienceTree 核心类
├── domain_router.py     # DomainRouter 领域路由器
├── retriever.py         # ExperienceRetriever 经验检索器
├── writer.py            # ExperienceWriter 经验写入器
├── classifier.py        # DomainClassifier 领域分类器
├── taxonomy.py          # 领域+类别 taxonomy 定义
└── store.py             # ExperienceStore SQLite 持久化
```

### 8.2 核心接口

```python
# butler/memory/experience/tree.py

class ExperienceTree:
    """经验-知识树，二层管理机制的核心入口"""

    def retrieve(self, query: str, top_k: int = 5) -> list[ExperienceHit]:
        """检索经验：领域路由 → 类别检索 → 排序"""
        # 1. DomainRouter.route(query) → domain_id
        # 2. ExperienceRetriever.retrieve(domain_id, query) → hits
        # 3. 按 confidence 排序返回

    def write(self, query: str, result: str, metadata: dict) -> str:
        """写入新经验：领域分类 → 类别归类 → 存储"""
        # 1. DomainClassifier.classify(query, result) → domain + category
        # 2. ExperienceStore.save(node) → node_id
        # 3. 更新 ChromaDB + KnowledgeGraph

    def get_domain_stats(self, domain_id: str) -> dict:
        """获取领域统计信息"""

    def link_experience(self, source_id: str, target_id: str, relation: str):
        """建立经验间的关联"""

    def promote_to_workflow(self, experience_id: str) -> str:
        """将高频经验提升为工作流模板"""
```

### 8.3 领域路由器

```python
# butler/memory/experience/domain_router.py

class DomainRouter:
    """基于关键词+语义+频率的领域路由"""

    DOMAIN_KEYWORDS: dict[str, list[str]] = {
        "daily_life": ["日程", "提醒", "偏好", "习惯", "天气", ...],
        "agent_dev": ["agent", "loop", "prompt", "tool", "skill", "llm", ...],
        "database": ["sql", "postgres", "redis", "index", "migration", ...],
        "llm_usage": ["model", "deepseek", "minimax", "token", "embedding", ...],
        "network_info": ["search", "web", "fetch", "url", "爬取", ...],
        "dev_ops": ["docker", "ci", "cd", "deploy", "kubernetes", ...],
        "code_engineering": ["refactor", "test", "lint", "review", "architecture", ...],
        "project_mgmt": ["task", "progress", "backlog", "priority", "deadline", ...],
    }

    def route(self, query: str) -> tuple[str, float]:
        """返回 (domain_id, confidence)"""
        # 1. 关键词匹配 → 快速路径
        # 2. 语义匹配 → 准确路径
        # 3. 频率加权 → 自适应
```

## 9. 实现计划

### 9.1 分阶段实施

| 阶段 | 内容 | 优先级 |
|------|------|--------|
| Phase 1 | 核心: taxonomy + store + tree + domain_router | P0 |
| Phase 2 | 检索: retriever + classifier | P0 |
| Phase 3 | 写入: writer + 自动归类 | P1 |
| Phase 4 | 集成: agent_loop + tool_selector | P1 |
| Phase 5 | 测试: 单元测试 + 100轮对话验证 | P0 |
| Phase 6 | 迁移: 现有经验数据迁移到树结构 | P2 |
| Phase 7 | 增强: Langfuse 追踪 + 工作流提升 | P2 |

### 9.2 验收标准

| 指标 | 目标 |
|------|------|
| 领域路由准确率 | > 85% |
| 经验检索延迟 | < 100ms (P99) |
| 100轮对话记忆召回率 | > 95% |
| 新经验自动归类准确率 | > 80% |
| 工具选择准确率（有经验指导） | > 90% |

## 10. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 领域分类错误 | 经验写入错误领域 | 支持手动修正 + 定期重分类 |
| ChromaDB 数据增长 | 查询变慢 | 定期 GC + 分 collection |
| 与现有 unified_recall 冲突 | 双系统并行 | 经验树作为 unified_recall 的上层路由 |
| NetworkX 内存增长 | OOM | 限制节点数 + 冷数据归档到 SQLite |

## 11. 后续演进

1. **跨会话经验迁移**：不同项目的经验可以共享和隔离
2. **经验质量评分**：基于使用结果自动调整经验权重
3. **经验失效检测**：长期未命中或低成功率的经验自动降级
4. **联邦学习**：多实例间的经验共享（如果未来支持多实例）
5. **可视化**：CLI 工具可视化经验树结构
