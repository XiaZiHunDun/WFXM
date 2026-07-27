# Butler DevEngine — L4 编码知识层

> **层级**：L4 工具与能力 / 编码知识层  
> **父文档**：[`../../AGENTS.md`](../../AGENTS.md)  
> **架构参考**：[`../../docs/architecture/v4-architecture.md`](../../docs/architecture/v4-architecture.md) §7

## 目录结构

```
butler/dev_engine/
├── __init__.py                    # 模块初始化
├── coding_knowledge/              # 编码知识子包
│   ├── __init__.py
│   ├── elements.py                # 编码元素定义
│   ├── theorems.py                # 定理库
│   ├── experience.py              # 经验管理
│   ├── verification.py            # 验证逻辑
│   ├── context.py                 # 上下文管理
│   ├── generation.py              # 代码生成约束
│   └── seed_experiences.py        # 种子经验数据
├── review_closure.py              # 审查闭环
├── dev_tools.py                   # 开发工具
├── gentc_mutation.py              # 测试用例变异
└── （其他开发引擎模块）
```

## 子目录说明

| 子目录 | 职责 | 说明 |
|--------|------|------|
| `coding_knowledge/` | 编码知识层 | 编码元素、定理、经验、验证、生成约束 |

## 关键模块速查

| 模块 | 说明 | 行数 |
|------|------|------|
| `coding_knowledge/elements.py` | 编码元素定义 | 核心模块 |
| `coding_knowledge/theorems.py` | 定理库实现 | 核心模块 |
| `coding_knowledge/generation.py` | 代码生成约束 | 核心模块 |
| `review_closure.py` | 审查闭环 | 开发流程 |
| `gentc_mutation.py` | 测试用例变异 | 测试增强 |

## 核心类与函数

| 类/函数 | 路径 | 说明 |
|---------|------|------|
| `CodingElement` | `coding_knowledge/elements.py` | 编码元素枚举 |
| `TheoremLibrary` | `coding_knowledge/theorems.py` | 定理库 |
| `decompose_task` | `coding_knowledge/elements.py` | 任务分解 |

## 数据流

```
编码任务 → decompose_task → 编码元素 → 定理检查 → 代码生成约束
```

## 注意事项

1. **编码知识层**：基于 CA1-CA4 / CT1-CT5 / H6/H8/H11 理论构建
2. **经验系统**：`experience.py` 管理编码经验的积累和检索
3. **种子经验**：`seed_experiences.py` 包含预定义的经验数据

## 相关目录

- L3 核心：[`../core/`](../core/)
- L4 工具：[`../tools/`](../tools/)
