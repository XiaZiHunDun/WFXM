"""Seed data — pre-populated knowledge materials for all domains."""

from __future__ import annotations

from typing import Any, Dict, List

SEED_MATERIALS: List[Dict[str, Any]] = [
    # ========== agent_dev ==========
    {
        "source_type": "text",
        "domain_hint": "agent_dev",
        "title": "ReAct模式基础",
        "content": """ReAct模式是一种让大语言模型通过"推理+行动"循环来解决问题的范式。
工作流程：Reasoning → Action → Observation → Repeat
关键要点：
1. 先进行推理思考，分析当前状态和下一步需要做什么
2. 然后调用工具执行行动
3. 根据观察结果调整下一步策略
4. 重复直到任务完成
适用场景：复杂问题解决、多步骤任务、需要外部工具的任务""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "agent_dev",
        "title": "对话记忆管理策略",
        "content": """四层记忆架构：
热层（Hot）：最近20轮滚动窗口，快速访问
温层（Warm）：每10轮生成章节摘要，结构化知识提取
冷层（Cold）：ChromaDB语义检索，全量历史上下文
图层（Graph）：KnowledgeGraph知识图谱，实体关系推理

记忆压缩策略：
- 轮次级：保留用户意图和助手行动摘要
- 章节级：每10轮生成结构化章节摘要
- 项目级：关键决策和技术栈持久化""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "agent_dev",
        "title": "工具选择策略",
        "content": """工具选择优先级：
1. 先查经验树（置信度>0.7直接使用经验）
2. 经验+工具混合模式（置信度0.4-0.7）
3. 纯工具模式（置信度<0.4）

工具调用原则：
- 执行前验证参数正确性
- 执行后检查结果有效性
- 失败时记录失败原因用于经验学习
- 成功时提取经验写入经验树""",
        "priority": 2,
    },
    # ========== database ==========
    {
        "source_type": "text",
        "domain_hint": "database",
        "title": "PostgreSQL JSONB索引",
        "content": """PostgreSQL JSONB类型适合存储半结构化数据。
索引策略：
- 查询JSONB字段中的键值对时，使用GIN索引
- 创建索引：CREATE INDEX idx_name ON table USING GIN (jsonb_column);
- 查询示例：SELECT * FROM table WHERE jsonb_column @> '{"key": "value"}';

性能优化：
- 对于简单的键值查询，GIN索引效果最好
- 对于路径查询（如data->>'key'），考虑使用btree索引
- 避免在JSONB字段上使用LIKE查询""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "database",
        "title": "Redis缓存最佳实践",
        "content": """Redis作为缓存层的使用策略：
1. 缓存穿透：使用布隆过滤器或空值缓存
2. 缓存击穿：热点key设置永不过期或使用分布式锁
3. 缓存雪崩：设置不同的过期时间

数据结构选择：
- 字符串：缓存简单值
- Hash：缓存对象
- List：消息队列
- Set：去重和交集操作
- Sorted Set：排行榜""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "database",
        "title": "SQL查询优化",
        "content": """SQL查询优化技巧：
1. 使用EXPLAIN ANALYZE分析执行计划
2. 在WHERE和JOIN条件的列上创建索引
3. 避免SELECT *，只查询需要的列
4. 使用LIMIT限制返回行数
5. 避免在WHERE子句中对列进行函数操作
6. 合理使用JOIN，避免笛卡尔积
7. 对于大数据量，考虑分批处理""",
        "priority": 2,
    },
    # ========== llm_usage ==========
    {
        "source_type": "text",
        "domain_hint": "llm_usage",
        "title": "模型选择策略",
        "content": """不同场景的模型选择：
代码生成：DeepSeek-Coder、CodeLlama
中文对话：MiniMax、Qwen、Yi
长文本处理：Qwen-Long、Yi-Long
数学推理：Wolfram Alpha API + LLM
多模态：GPT-4V、Qwen-VL

模型参数调优：
- temperature：创造性（0.1-0.9），越低越确定
- top_p：核采样，控制输出多样性
- max_tokens：限制输出长度
- system_prompt：设定角色和行为准则""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "llm_usage",
        "title": "长文本处理技巧",
        "content": """处理超过模型上下文窗口的文本：
方法1：Map-Reduce
- 将文本分成多个chunk
- 对每个chunk单独摘要
- 将所有摘要合并成最终结果

方法2：滑动窗口
- 使用固定大小的滑动窗口遍历文本
- 每个窗口生成摘要
- 合并相邻窗口的重叠部分

方法3：分层摘要
- 先进行粗粒度摘要
- 再对摘要进行细粒度处理""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "llm_usage",
        "title": "Prompt工程最佳实践",
        "content": """Prompt编写原则：
1. 明确任务和期望输出格式
2. 提供上下文和示例（Few-shot）
3. 设定角色和专业程度
4. 使用结构化格式（JSON、XML）
5. 避免模糊的指令

迭代优化流程：
- 编写初始prompt
- 测试并收集反馈
- 分析失败案例
- 逐步改进prompt
- A/B测试验证效果""",
        "priority": 2,
    },
    # ========== network_info ==========
    {
        "source_type": "text",
        "domain_hint": "network_info",
        "title": "信息检索策略",
        "content": """信息检索流程：
1. WebSearch：获取初步信息和链接
2. WebFetch：获取网页完整内容
3. 信息提取：提取关键信息
4. 事实核查：验证信息准确性

搜索技巧：
- 使用精确匹配（引号）
- 使用site:限定域名
- 使用filetype:限定文件类型
- 使用-排除关键词
- 使用"最新"获取最新信息""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "network_info",
        "title": "技术文档查询优先级",
        "content": """查询技术问题的优先级：
1. 官方文档（最权威）
2. GitHub仓库README和Wiki
3. Stack Overflow（实际问题解决方案）
4. 技术博客（深度解析）
5. 官方示例代码

注意事项：
- 检查文档版本是否匹配
- 注意代码示例的语言版本
- 查看更新时间，避免过时信息""",
        "priority": 2,
    },
    # ========== dev_ops ==========
    {
        "source_type": "text",
        "domain_hint": "dev_ops",
        "title": "Docker多阶段构建",
        "content": """多阶段构建可以显著减小镜像大小：
阶段1：构建阶段（包含所有构建工具）
阶段2：运行阶段（只包含运行时依赖）

示例：
FROM python:3.13 AS builder
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.13-slim
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY . .
CMD ["python", "app.py"]

效果：通常可减小镜像40-70%""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "dev_ops",
        "title": "CI/CD流程",
        "content": """标准CI/CD流程：
1. Lint：代码风格检查（flake8、mypy）
2. Test：自动化测试（pytest、unittest）
3. Build：构建产物
4. Deploy：部署到环境
5. Health Check：验证服务健康

本地开发门禁：
- butler-pytest-fast-gate.sh：快速门禁（3-5分钟）
- butler-mypy-strict-gate.sh：类型检查
- butler-layer-import-gate.sh：依赖层检查""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "dev_ops",
        "title": "日志管理",
        "content": """日志管理最佳实践：
1. 结构化日志：使用JSON格式
2. 日志分级：DEBUG、INFO、WARNING、ERROR、CRITICAL
3. 日志轮转：避免日志文件过大
4. 集中收集：使用ELK或Loki
5. 关键日志：记录请求ID便于追踪

日志内容：
- 时间戳
- 日志级别
- 请求ID
- 模块/函数名
- 详细信息""",
        "priority": 2,
    },
    # ========== code_engineering ==========
    {
        "source_type": "text",
        "domain_hint": "code_engineering",
        "title": "代码审查流程",
        "content": """代码审查标准流程：
1. Read：理解代码变更意图
2. Analyze：分析实现正确性和质量
3. Feedback：提供具体反馈和改进建议
4. Verify：验证修改后的代码

审查要点：
- 代码可读性和命名规范
- 类型安全和错误处理
- 性能和资源使用
- 测试覆盖率
- 架构一致性""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "code_engineering",
        "title": "重构原则",
        "content": """重构原则（SOLID）：
SRP：单一职责原则
OCP：开闭原则
LSP：里氏替换原则
ISP：接口隔离原则
DIP：依赖倒置原则

重构步骤：
1. 编写测试（确保现有功能）
2. 小步重构（每步验证）
3. 运行测试（确保没有破坏）
4. 重复直到完成

重构前先跑门禁：mypy strict + pytest""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "code_engineering",
        "title": "测试分层策略",
        "content": """测试分层：
L0：快速单元测试（<1秒）
L1：集成测试（<30秒）
L2：场景测试（<5分钟）
L3：真实LLM端到端测试（按需）

运行策略：
- 开发时：高频跑L0+L1
- PR时：跑L0+L1+L2
- 发布时：跑全量测试

测试覆盖率目标：
- 核心模块：>80%
- 工具模块：>60%
- 集成模块：>70%""",
        "priority": 2,
    },
    # ========== project_mgmt ==========
    {
        "source_type": "text",
        "domain_hint": "project_mgmt",
        "title": "黑卡交接流程",
        "content": """黑卡交接标准流程：
1. 更新 state.md：当前状态快照
2. 创建 shift card：班次交接卡
3. 更新 backlog.yaml：待办状态
4. Commit：提交变更

交接卡内容：
- 当前进度
- 已完成工作
- 待办事项
- 阻塞问题
- 下一步计划

验证命令：butler blackboard validate --shift-id <id>""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "project_mgmt",
        "title": "需求拆解原则",
        "content": """需求拆解原则：
1. 单一性：每个任务只做一件事
2. 可测试：能够明确验证完成
3. 独立性：任务之间相互独立
4. 可估计：能够估算工作量

拆解步骤：
- 用户故事 → 功能点 → 技术任务 → 代码变更
- 使用INVEST原则检查每个任务

优先级排序：
- P0：阻塞性问题
- P1：核心功能
- P2：重要功能
- P3：优化和改进""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "project_mgmt",
        "title": "进度追踪方法",
        "content": """进度追踪方法：
1. 燃尽图：剩余工作量随时间变化
2. 看板：任务状态可视化
3. 每日站会：同步进展和阻塞
4. 周报：汇总一周工作

关键指标：
- 完成率：已完成任务/总任务
- 速度：每个迭代完成的故事点数
- 阻塞率：被阻塞任务的比例
- 返工率：需要修改的任务比例""",
        "priority": 2,
    },
    # ========== daily_life ==========
    {
        "source_type": "text",
        "domain_hint": "daily_life",
        "title": "工作时间管理",
        "content": """工作时间管理技巧：
- 番茄工作法：25分钟工作+5分钟休息
- 任务优先级：重要且紧急优先
- 批量处理：相似任务一起处理
- 避免干扰：关闭通知，专注工作

时间分配：
- 核心工作：60%时间
- 会议沟通：20%时间
- 学习成长：10%时间
- 灵活处理：10%时间""",
        "priority": 1,
    },
    {
        "source_type": "text",
        "domain_hint": "daily_life",
        "title": "信息整理方法",
        "content": """信息整理方法：
- 分类归档：按主题组织信息
- 定期清理：每周清理无效信息
- 标签系统：使用标签快速检索
- 摘要记录：记录关键要点而非全文

工具选择：
- 笔记：Notion、Obsidian
- 待办：TodoList、项目看板
- 文档：Markdown、Confluence""",
        "priority": 1,
    },
]


def load_seed_data(ingestor) -> None:
    """Load seed materials into the knowledge warehouse."""
    results = ingestor.bulk_ingest(SEED_MATERIALS)
    added = sum(1 for _, was_added in results if was_added)
    skipped = len(results) - added
    print(f"Loaded {added} seed materials (skipped {skipped} duplicates)")
    return results
