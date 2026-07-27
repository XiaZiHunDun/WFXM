# Butler Memory — L5 记忆与知识

> **层级**：L5 记忆与知识  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/memory/
├── __init__.py                    # 模块初始化
├── experience/                    # 经验管理子包
├── knowledge_warehouse/           # 知识仓库
├── butler_memory.py               # 全局记忆（ProfileStore + ExperienceStore）
├── project_memory.py              # 项目记忆
├── semantic_index.py              # 语义索引
├── vector_store.py                # 向量存储
├── embedding.py                   # 嵌入处理
├── experience_mining.py           # 经验挖掘
├── recall_router.py               # 召回路由
├── unified_recall.py              # 统一召回
├── hybrid_retriever.py            # 混合检索器
└── （其他辅助模块）
```

## 子目录说明

| 子目录 | 职责 | 说明 |
|--------|------|------|
| `experience/` | 经验管理 | 经验数据的存储、检索、清理 |
| `knowledge_warehouse/` | 知识仓库 | 知识库管理、种子数据 |

## 关键模块速查

| 模块 | 说明 | 行数 |
|------|------|------|
| `butler_memory.py` | 全局记忆管理 | ~29810 |
| `project_memory.py` | 项目记忆管理 | ~26320 |
| `semantic_index.py` | 语义索引核心 | ~24090 |
| `experience_mining.py` | 经验挖掘 | ~22160 |
| `facade.py` | 记忆门面接口 | ~20840 |
| `embedding.py` | 嵌入处理 | ~16390 |
| `knowledge_graph.py` | 知识图谱 | ~15520 |
| `recall_router.py` | 召回路由 | ~12700 |
| `observation_store.py` | 观测存储 | ~12340 |
| `diagnostics.py` | 诊断工具 | ~12210 |
| `chunking.py` | 分块处理 | ~11860 |
| `vector_store.py` | 向量存储 | ~9340 |

## 核心类与函数

| 类/函数 | 路径 | 说明 |
|---------|------|------|
| `ButlerMemory` | `butler_memory.py` | 全局记忆主类 |
| `ProjectMemory` | `project_memory.py` | 项目记忆主类 |
| `SemanticIndex` | `semantic_index.py` | 语义索引 |
| `VectorStore` | `vector_store.py` | 向量存储 |
| `ExperienceMiner` | `experience_mining.py` | 经验挖掘 |

## 数据流

```
用户查询 → recall_router
              │
              ├→ semantic_index       # 语义检索
              ├→ vector_store         # 向量检索
              ├→ hybrid_retriever     # 混合检索
              ├→ observation_store    # 观测检索
              └→ unified_recall       # 统一召回结果
```

## 注意事项

1. **记忆层次**：`butler_memory.py` 是全局记忆，`project_memory.py` 是项目级记忆
2. **经验系统**：`experience/` 子包管理经验数据的生命周期
3. **语义检索**：`semantic_index.py` 和 `vector_store.py` 是语义检索的核心
4. **诊断工具**：`diagnostics.py` 和 `diagnostics_collect.py` 用于记忆系统诊断

## 相关目录

- L3 核心：[`../core/`](../core/)
- L6 模型：[`../transport/`](../transport/)
