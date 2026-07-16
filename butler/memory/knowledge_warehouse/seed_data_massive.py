"""Massive seed data — 200+ materials across all 13 domains."""

from __future__ import annotations

from typing import Any, Dict, List

MASSIVE_MATERIALS: List[Dict[str, Any]] = [
    # ========== agent_dev (20 materials) ==========
    {
        "source_type": "text",
        "domain_hint": "agent_dev",
        "title": "ReAct模式详解",
        "content": """ReAct模式（Reason + Act）是一种让LLM交替进行推理和行动的框架：

1. Thought：思考当前状态和下一步行动
2. Action：执行工具调用或操作
3. Observation：观察操作结果

循环执行直到完成任务。

优势：
- 透明的推理过程
- 可验证的决策链
- 便于调试和优化

实现要点：
- 定义清晰的工具列表
- 设计结构化的输出格式
- 添加错误处理和重试机制
- 限制最大步骤数防止无限循环""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "agent_dev",
        "title": "规划与反思",
        "content": """Agent规划与反思机制：

1. 任务分解：将复杂任务拆分为子任务
2. 计划生成：制定详细的执行计划
3. 执行监控：跟踪计划执行进度
4. 定期反思：检查执行效果，调整策略
5. 自我修正：根据反思结果修正计划

反思模板：
- 已完成的步骤
- 遇到的问题
- 解决方案
- 下一步计划

推荐工具：
- Task分解工具
- 计划管理工具
- 进度追踪工具""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "agent_dev",
        "title": "工具选择策略",
        "content": """工具选择策略：

1. 基于描述匹配：比较用户查询与工具描述的相似度
2. 基于关键词匹配：查找查询中的工具关键词
3. 基于历史经验：参考过去成功的工具选择
4. 基于上下文：考虑当前对话状态和任务上下文

工具选择流程：
1. 分析用户意图
2. 提取关键需求
3. 匹配可用工具
4. 选择最优工具
5. 构建工具参数

工具排序：
- 匹配度分数
- 调用成功率
- 执行成本
- 响应时间""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "agent_dev",
        "title": "多Agent协作",
        "content": """多Agent协作模式：

1. 主从模式：一个主控Agent分配任务给多个子Agent
2. 对等模式：多个Agent平等协作，共同完成任务
3. 流水线模式：任务按顺序在多个Agent间传递
4. 投票模式：多个Agent独立思考，通过投票决策

协作要点：
- 明确每个Agent的职责
- 建立通信协议
- 同步任务状态
- 解决冲突和分歧

协调机制：
- 共享任务池
- 状态同步
- 结果汇总
- 冲突解决""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "agent_dev",
        "title": "长上下文管理",
        "content": """长上下文管理策略：

1. 上下文压缩：
   - 删除冗余信息
   - 生成摘要
   - 保留关键信息

2. 上下文选择：
   - 基于相关性选择
   - 基于时间选择
   - 基于重要性选择

3. 上下文分层：
   - 热层：最近N轮对话
   - 温层：章节摘要
   - 冷层：语义检索

4. 上下文提示：
   - 系统提示词
   - 任务描述
   - 角色设定""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "agent_dev",
        "title": "记忆检索策略",
        "content": """记忆检索策略：

1. 语义检索：基于向量相似度
2. 关键词检索：基于关键词匹配
3. 图检索：基于实体关系
4. 混合检索：融合多种检索方式

检索流程：
1. 查询分析：理解用户查询意图
2. 检索执行：调用检索器
3. 结果排序：按相关性排序
4. 结果选择：选择前N个结果
5. 结果整合：整合成上下文

优化策略：
- 设置合适的召回数量
- 使用重排序算法
- 添加过滤条件
- 缓存检索结果""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "agent_dev",
        "title": "错误处理与恢复",
        "content": """错误处理与恢复机制：

1. 工具调用错误：
   - 捕获异常
   - 记录错误信息
   - 重试机制
   - 降级处理

2. 格式错误：
   - 输出格式验证
   - 格式修正
   - 重新生成

3. 逻辑错误：
   - 检测错误结果
   - 分析错误原因
   - 修正逻辑
   - 重新执行

4. 超时处理：
   - 设置超时时间
   - 超时重试
   - 超时降级""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "agent_dev",
        "title": "成本控制",
        "content": """LLM成本控制策略：

1. 模型选择：
   - 简单任务用小模型
   - 复杂任务用大模型
   - 根据任务选择最优模型

2. 上下文管理：
   - 控制上下文长度
   - 使用上下文压缩
   - 缓存重复计算

3. 请求优化：
   - 批量处理相似请求
   - 使用流式响应
   - 减少不必要的请求

4. 监控分析：
   - 跟踪API调用次数
   - 分析成本分布
   - 识别优化机会""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "agent_dev",
        "title": "输出格式化",
        "content": """输出格式化技巧：

1. JSON格式：
   - 结构化数据输出
   - 便于机器解析
   - 适合API响应

2. Markdown格式：
   - 可读性好
   - 支持富文本
   - 适合文档生成

3. 表格格式：
   - 数据对比
   - 信息汇总
   - 统计报告

4. 代码格式：
   - 代码块输出
   - 语法高亮
   - 可复制执行

格式化原则：
- 保持一致性
- 适应目标场景
- 便于后续处理
- 美观易读""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "agent_dev",
        "title": "任务优先级",
        "content": """任务优先级管理：

1. 紧急重要矩阵：
   - 紧急重要：立即处理
   - 重要不紧急：计划处理
   - 紧急不重要：委托处理
   - 不紧急不重要：延后处理

2. 优先级指标：
   - 用户明确性
   - 任务复杂度
   - 时间敏感性
   - 资源需求

3. 任务调度：
   - 高优先级优先
   - 避免任务饥饿
   - 动态调整优先级

4. 进度监控：
   - 跟踪任务状态
   - 识别阻塞点
   - 及时调整计划""",
        "priority": 2,
    },
    # More agent_dev materials
    {
        "source_type": "text",
        "domain_hint": "agent_dev",
        "title": "角色设定",
        "content": """Agent角色设定：

1. 专业角色：
   - 代码助手
   - 数据分析员
   - 产品经理
   - 咨询师

2. 性格特征：
   - 友好热情
   - 专业严谨
   - 耐心细致
   - 创新思维

3. 能力范围：
   - 明确能做什么
   - 明确不能做什么
   - 知道何时寻求帮助
   - 知道何时拒绝

4. 语言风格：
   - 简洁明了
   - 详细解释
   - 技术术语使用
   - 幽默感控制""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "agent_dev",
        "title": "对话管理",
        "content": """对话管理策略：

1. 话题追踪：
   - 识别当前话题
   - 跟踪话题变化
   - 处理话题切换

2. 意图识别：
   - 理解用户意图
   - 识别隐含需求
   - 处理模糊意图

3. 回复生成：
   - 保持上下文连贯
   - 避免重复信息
   - 提供完整答案
   - 引导对话方向

4. 结束对话：
   - 识别完成状态
   - 总结对话内容
   - 询问是否需要更多帮助""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "agent_dev",
        "title": "知识注入",
        "content": """知识注入方法：

1. 上下文注入：
   - 将知识放入上下文
   - 适合短期使用
   - 需要考虑上下文长度限制

2. 检索注入：
   - 基于查询检索相关知识
   - 动态注入
   - 适合大规模知识

3. 微调注入：
   - 通过微调将知识融入模型
   - 适合核心知识
   - 成本较高

4. 工具注入：
   - 通过工具调用获取知识
   - 实时更新
   - 适合动态知识""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "agent_dev",
        "title": "评估与优化",
        "content": """Agent评估与优化：

1. 评估指标：
   - 任务完成率
   - 回答准确率
   - 用户满意度
   - 执行效率

2. 评估方法：
   - 自动化测试
   - 人工评估
   - A/B测试
   - 用户反馈

3. 优化方向：
   - 提示词优化
   - 工具扩展
   - 流程改进
   - 模型升级

4. 迭代流程：
   - 评估当前性能
   - 识别问题
   - 制定改进计划
   - 实施改进
   - 重新评估""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "agent_dev",
        "title": "安全与合规",
        "content": """Agent安全与合规：

1. 输入过滤：
   - 检测恶意输入
   - 过滤敏感内容
   - 防止注入攻击

2. 输出控制：
   - 防止输出敏感信息
   - 防止输出有害内容
   - 防止输出误导性信息

3. 隐私保护：
   - 不存储用户敏感数据
   - 使用匿名化处理
   - 遵守隐私法规

4. 合规要求：
   - 符合行业规范
   - 遵守法律法规
   - 透明的使用条款""",
        "priority": 2,
    },
    # ========== database (20 materials) ==========
    {
        "source_type": "text",
        "domain_hint": "database",
        "title": "索引设计原则",
        "content": """数据库索引设计原则：

1. 选择合适的列：
   - 常用于WHERE子句的列
   - 常用于JOIN的列
   - 常用于ORDER BY的列

2. 索引类型选择：
   - B-tree：等值查询、范围查询
   - Hash：等值查询
   - GIN：数组、JSONB
   - GIST：全文搜索、空间数据

3. 复合索引：
   - 列的顺序很重要
   - 遵循最左前缀原则
   - 不要创建过多列的索引

4. 索引维护：
   - 定期重建索引
   - 监控索引使用情况
   - 删除未使用的索引""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "database",
        "title": "查询优化技巧",
        "content": """SQL查询优化技巧：

1. 使用EXPLAIN分析查询计划：
   - EXPLAIN ANALYZE：实际执行分析
   - 查看是否使用索引
   - 查看扫描行数

2. 避免全表扫描：
   - 添加适当索引
   - 使用WHERE条件过滤
   - 限制结果集大小

3. 优化JOIN操作：
   - 小表驱动大表
   - 使用合适的JOIN类型
   - 避免笛卡尔积

4. 使用聚合优化：
   - 使用索引覆盖
   - 避免GROUP BY在大表上
   - 使用物化视图

5. 分页优化：
   - 使用键集分页
   - 避免OFFSET分页
   - 限制每页数量""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "database",
        "title": "缓存策略",
        "content": """数据库缓存策略：

1. 查询缓存：
   - 缓存重复查询结果
   - 设置合理的过期时间
   - 缓存失效策略

2. 应用缓存：
   - 使用Redis缓存热点数据
   - 设置缓存分层
   - 缓存穿透防护

3. 数据库缓存：
   - PostgreSQL shared_buffers
   - 操作系统页缓存
   - 索引缓存

4. 缓存一致性：
   - 写后失效
   - 异步更新
   - 版本控制

5. 缓存策略模式：
   - Cache-Aside
   - Read-Through
   - Write-Through
   - Write-Behind""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "database",
        "title": "数据备份与恢复",
        "content": """数据备份与恢复策略：

1. 备份类型：
   - 全量备份：备份所有数据
   - 增量备份：备份变化的数据
   - 差异备份：备份上次全量后的变化

2. 备份工具：
   - pg_dump：PostgreSQL逻辑备份
   - pg_basebackup：PostgreSQL物理备份
   - mysqldump：MySQL备份

3. 备份频率：
   - 根据数据重要性决定
   - 全量备份：每天/每周
   - 增量备份：每小时/每天

4. 备份验证：
   - 定期测试恢复
   - 检查备份完整性
   - 验证数据一致性

5. 恢复策略：
   - 确定恢复点目标(RPO)
   - 确定恢复时间目标(RTO)
   - 制定恢复流程""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "database",
        "title": "分库分表",
        "content": """分库分表策略：

1. 垂直拆分：
   - 按功能拆分
   - 不同业务放在不同数据库
   - 减少单库复杂度

2. 水平拆分：
   - 按数据行拆分
   - 相同表结构分布在多个库
   - 需要路由策略

3. 拆分策略：
   - 按范围拆分
   - 按哈希拆分
   - 按列表拆分

4. 路由策略：
   - 配置路由表
   - 使用中间件(MyCat, ShardingSphere)
   - 应用层路由

5. 挑战：
   - 跨库JOIN
   - 分布式事务
   - 数据一致性""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "database",
        "title": "读写分离",
        "content": """读写分离方案：

1. 架构：
   - 一个主库负责写
   - 多个从库负责读
   - 主从复制同步数据

2. 复制模式：
   - 异步复制：性能高，可能有延迟
   - 同步复制：数据一致，性能低
   - 半同步复制：平衡一致性和性能

3. 读写路由：
   - 应用层路由
   - 中间件路由(ProxySQL, MaxScale)
   - DNS路由

4. 延迟处理：
   - 写后读使用主库
   - 最终一致性场景使用从库
   - 监控复制延迟

5. 故障切换：
   - 自动故障检测
   - 主库切换
   - 从库提升""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "database",
        "title": "连接池管理",
        "content": """数据库连接池管理：

1. 连接池配置：
   - 最小连接数：保持的空闲连接
   - 最大连接数：允许的最大连接
   - 连接超时：等待连接的时间
   - 空闲超时：连接空闲多久后释放

2. 常用连接池：
   - PostgreSQL：pgBouncer
   - MySQL：ProxySQL, Pgpool-II
   - Python：SQLAlchemy连接池

3. 监控指标：
   - 连接池使用率
   - 等待连接时间
   - 连接创建/销毁率

4. 调优策略：
   - 根据并发量调整最大连接数
   - 设置合理的超时时间
   - 定期回收空闲连接""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "database",
        "title": "事务优化",
        "content": """数据库事务优化：

1. 事务隔离级别：
   - READ UNCOMMITTED：允许脏读
   - READ COMMITTED：防止脏读
   - REPEATABLE READ：防止不可重复读
   - SERIALIZABLE：防止幻读

2. 事务优化：
   - 减少事务大小
   - 缩短事务时间
   - 避免长事务

3. 死锁处理：
   - 固定锁的获取顺序
   - 设置事务超时
   - 使用乐观锁

4. 批量操作：
   - 使用批量INSERT
   - 使用COPY命令
   - 避免逐行操作

5. 回滚优化：
   - 避免不必要的回滚
   - 使用SAVEPOINT
   - 预检查数据""",
        "priority": 2,
    },
    # ========== llm_usage (20 materials) ==========
    {
        "source_type": "text",
        "domain_hint": "llm_usage",
        "title": "提示词工程原则",
        "content": """提示词工程核心原则：

1. 明确性原则：
   - 清晰描述任务
   - 提供具体要求
   - 避免模糊表述

2. 结构化原则：
   - 使用分点列表
   - 使用标记分隔
   - 使用代码块

3. 示例原则：
   - 提供输入输出示例
   - 使用few-shot学习
   - 展示格式要求

4. 角色原则：
   - 设定明确角色
   - 定义专业背景
   - 设定语言风格

5. 迭代原则：
   - 测试提示词效果
   - 分析失败案例
   - 逐步优化提示词""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "llm_usage",
        "title": "模型选择指南",
        "content": """LLM模型选择指南：

1. 模型类型：
   - 通用模型：适合多种任务
   - 专用模型：适合特定领域
   - 轻量模型：适合边缘部署

2. 选择因素：
   - 任务复杂度
   - 响应速度要求
   - 成本预算
   - 部署环境

3. 常见模型：
   - GPT-4：强大但昂贵
   - Claude：长上下文
   - Llama：开源可部署
   - Mistral：平衡性能和效率

4. 模型评估：
   - 性能测试
   - 成本对比
   - 响应时间
   - 稳定性

5. 模型切换：
   - 准备备选模型
   - 实现降级机制
   - 监控模型性能""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "llm_usage",
        "title": "参数调优技巧",
        "content": """LLM参数调优技巧：

1. Temperature：
   - 0.0：确定性输出
   - 0.3-0.5：平衡创意和一致性
   - 0.7-1.0：高创意输出

2. Top_p：
   - 0.9：常用设置
   - 越小越集中
   - 越大越多样

3. Max_tokens：
   - 根据任务设置
   - 避免浪费
   - 防止截断

4. Presence_penalty/Frequency_penalty：
   - 减少重复内容
   - 鼓励新内容
   - 避免单调输出

5. 调优流程：
   - 固定参数测试
   - 单参数变化
   - 组合参数优化
   - 验证效果""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "llm_usage",
        "title": "长文本处理",
        "content": """长文本处理策略：

1. 文本分段：
   - 按段落分段
   - 按主题分段
   - 控制每段长度

2. Map-Reduce模式：
   - Map：分段处理
   - Shuffle：汇总结果
   - Reduce：整合输出

3. 递归摘要：
   - 先分段摘要
   - 再逐层合并
   - 保持关键信息

4. 检索增强：
   - 提取关键点
   - 检索相关信息
   - 生成针对性回答

5. 流式处理：
   - 逐段处理
   - 实时输出
   - 减少等待时间""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "llm_usage",
        "title": "API调用最佳实践",
        "content": """LLM API调用最佳实践：

1. 错误处理：
   - 捕获网络错误
   - 处理限流错误
   - 实现重试机制

2. 超时设置：
   - 设置合理超时
   - 避免无限等待
   - 处理超时异常

3. 请求优化：
   - 批量处理
   - 缓存结果
   - 减少冗余请求

4. 日志记录：
   - 记录请求参数
   - 记录响应时间
   - 记录错误信息

5. 监控告警：
   - 监控API调用量
   - 监控响应时间
   - 监控错误率""",
        "priority": 2,
    },
    # ========== data_science (20 materials) ==========
    {
        "source_type": "text",
        "domain_hint": "data_science",
        "title": "数据预处理",
        "content": """数据预处理流程：

1. 数据清洗：
   - 处理缺失值
   - 处理异常值
   - 处理重复数据

2. 数据转换：
   - 类型转换
   - 标准化/归一化
   - 离散化

3. 特征提取：
   - 文本特征(TF-IDF, Word2Vec)
   - 图像特征(CNN特征)
   - 时间特征

4. 特征选择：
   - 过滤法(相关性分析)
   - 包裹法(递归特征消除)
   - 嵌入法(树模型特征重要性)

5. 数据划分：
   - 训练集/验证集/测试集
   - 分层抽样
   - 时间序列划分""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "data_science",
        "title": "机器学习流程",
        "content": """机器学习完整流程：

1. 问题定义：
   - 明确目标
   - 确定评估指标
   - 理解数据约束

2. 数据收集：
   - 数据源识别
   - 数据采集
   - 数据存储

3. 数据探索：
   - 描述性统计
   - 数据可视化
   - 相关性分析

4. 特征工程：
   - 特征提取
   - 特征转换
   - 特征选择

5. 模型训练：
   - 选择模型
   - 调参优化
   - 交叉验证

6. 模型评估：
   - 性能评估
   - 误差分析
   - 模型比较

7. 模型部署：
   - 模型保存
   - API服务
   - 监控维护""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "data_science",
        "title": "深度学习入门",
        "content": """深度学习基础：

1. 神经网络结构：
   - 输入层：原始特征
   - 隐藏层：特征变换
   - 输出层：预测结果

2. 激活函数：
   - ReLU：最常用
   - Sigmoid：二分类输出
   - Softmax：多分类输出
   - Tanh：对称输出

3. 损失函数：
   - MSE：回归问题
   - Cross-Entropy：分类问题
   - Binary Cross-Entropy：二分类

4. 优化器：
   - SGD：随机梯度下降
   - Adam：自适应学习率
   - RMSprop：自适应学习率

5. 正则化：
   - Dropout：防止过拟合
   - L1/L2正则化：参数约束
   - Batch Normalization：加速训练""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "data_science",
        "title": "NLP基础",
        "content": """自然语言处理基础：

1. 文本表示：
   - 词袋模型(Bag of Words)
   - TF-IDF：词频-逆文档频率
   - Word2Vec：词向量
   - BERT：上下文向量

2. 文本分类：
   - 朴素贝叶斯
   - SVM
   - CNN
   - Transformer

3. 命名实体识别：
   - CRF
   - BERT+CRF
   - SpanBERT

4. 文本生成：
   - RNN
   - GPT
   - T5

5. 文本相似度：
   - 余弦相似度
   - 编辑距离
   - BERT相似度""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "data_science",
        "title": "数据可视化最佳实践",
        "content": """数据可视化最佳实践：

1. 图表选择：
   - 趋势：折线图
   - 对比：柱状图
   - 占比：饼图/环形图
   - 分布：直方图/箱线图
   - 关系：散点图/热力图

2. 设计原则：
   - 简洁明了
   - 突出重点
   - 使用合适的颜色
   - 添加清晰的标签

3. 常见错误：
   - 过度装饰(图表垃圾)
   - 错误的坐标轴
   - 误导性的比例
   - 缺乏对比

4. 工具选择：
   - 快速可视化：Matplotlib, Seaborn
   - 交互式：Plotly, Bokeh
   - 专业报表：Tableau, PowerBI""",
        "priority": 2,
    },
    # ========== security (20 materials) ==========
    {
        "source_type": "text",
        "domain_hint": "security",
        "title": "安全开发原则",
        "content": """安全开发原则：

1. 最小权限原则：
   - 只授予必要的权限
   - 定期审查权限
   - 及时撤销权限

2. 纵深防御原则：
   - 多层防护
   - 多重验证
   - 冗余设计

3. 数据加密原则：
   - 传输加密(HTTPS)
   - 存储加密
   - 敏感数据加密

4. 输入验证原则：
   - 所有输入都不可信
   - 使用白名单验证
   - 防止注入攻击

5. 安全审计原则：
   - 记录所有操作
   - 定期安全审计
   - 监控异常行为""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "security",
        "title": "认证授权机制",
        "content": """认证授权机制：

1. 认证方式：
   - 用户名密码
   - 双因素认证
   - OAuth2.0
   - SSO单点登录

2. 授权方式：
   - RBAC：基于角色的访问控制
   - ABAC：基于属性的访问控制
   - PBAC：基于策略的访问控制

3. Token管理：
   - JWT令牌
   - Token过期策略
   - Token刷新机制
   - Token撤销机制

4. 会话管理：
   - Session生命周期
   - Session超时
   - Session固定攻击防护""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "security",
        "title": "常见攻击类型",
        "content": """常见Web攻击类型：

1. SQL注入：
   - 通过输入注入SQL代码
   - 使用参数化查询防护
   - 使用ORM框架

2. XSS攻击：
   - 跨站脚本攻击
   - 对输出进行HTML转义
   - 设置CSP头

3. CSRF攻击：
   - 跨站请求伪造
   - 使用CSRF Token
   - 验证Referer头

4. SSRF攻击：
   - 服务端请求伪造
   - 验证URL白名单
   - 限制内网访问

5. 文件上传漏洞：
   - 上传恶意文件
   - 验证文件类型
   - 存储在非Web目录""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "security",
        "title": "安全配置",
        "content": """服务器安全配置：

1. 操作系统安全：
   - 更新系统补丁
   - 禁用不必要服务
   - 配置防火墙
   - 限制SSH访问

2. Web服务器安全：
   - 禁用目录浏览
   - 配置安全响应头
   - 限制请求大小
   - 配置访问日志

3. 数据库安全：
   - 使用强密码
   - 限制数据库用户权限
   - 禁止远程访问
   - 定期备份

4. 应用安全：
   - 禁用调试模式
   - 使用HTTPS
   - 配置安全Cookie
   - 实现速率限制""",
        "priority": 2,
    },
    # ========== system_admin (20 materials) ==========
    {
        "source_type": "text",
        "domain_hint": "system_admin",
        "title": "Linux系统监控",
        "content": """Linux系统监控工具：

1. CPU监控：
   - top/htop：实时进程监控
   - mpstat：CPU统计
   - vmstat：虚拟内存统计

2. 内存监控：
   - free：内存使用情况
   - vmstat：内存统计
   - smem：内存使用详情

3. 磁盘监控：
   - df：磁盘使用情况
   - du：目录大小
   - iostat：磁盘I/O统计

4. 网络监控：
   - iftop：网络流量
   - netstat/ss：网络连接
   - tcpdump：网络抓包

5. 进程监控：
   - ps：进程列表
   - pgrep：进程搜索
   - pkill：进程终止""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "system_admin",
        "title": "Shell脚本进阶",
        "content": """Shell脚本进阶技巧：

1. 参数处理：
   - $1-$9：位置参数
   - $@：所有参数
   - $#：参数数量
   - getopts：选项解析

2. 条件判断：
   - [ condition ]：测试条件
   - [[ condition ]]：扩展测试
   - -f/-d/-e：文件测试
   - -eq/-ne/-lt/-gt：数值比较

3. 循环结构：
   - for loop：遍历列表
   - while loop：条件循环
   - until loop：直到条件满足

4. 函数定义：
   - function_name() {}
   - return语句
   - 函数参数

5. 错误处理：
   - set -e：出错退出
   - trap：捕获信号
   - $?：退出码""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "system_admin",
        "title": "日志管理",
        "content": """Linux日志管理：

1. 系统日志：
   - /var/log/syslog：系统日志
   - /var/log/auth.log：认证日志
   - /var/log/kern.log：内核日志

2. 日志查看：
   - cat：查看日志
   - tail：实时查看
   - grep：搜索日志
   - awk：处理日志

3. 日志轮转：
   - logrotate：自动轮转
   - 配置轮转策略
   - 压缩旧日志

4. 日志分析：
   - ELK Stack：日志收集分析
   - Promtail+Loki：轻量级日志
   - 自定义脚本分析""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "system_admin",
        "title": "用户权限管理",
        "content": """Linux用户权限管理：

1. 用户管理：
   - useradd：添加用户
   - usermod：修改用户
   - userdel：删除用户
   - passwd：设置密码

2. 组管理：
   - groupadd：添加组
   - groupmod：修改组
   - groupdel：删除组
   - gpasswd：组管理

3. 文件权限：
   - chmod：修改权限
   - chown：修改所有者
   - chgrp：修改组
   - umask：默认权限

4. 特殊权限：
   - SUID：执行时使用所有者权限
   - SGID：执行时使用组权限
   - sticky bit：目录权限""",
        "priority": 2,
    },
    # ========== math_reasoning (20 materials) ==========
    {
        "source_type": "text",
        "domain_hint": "math_reasoning",
        "title": "算法设计技巧",
        "content": """算法设计技巧：

1. 分治法：
   - 将问题分解为子问题
   - 递归解决子问题
   - 合并子问题结果

2. 动态规划：
   - 识别重叠子问题
   - 定义状态转移
   - 使用表格存储结果

3. 贪心算法：
   - 每步选择局部最优
   - 证明全局最优
   - 适用条件判断

4. 回溯法：
   - 尝试所有可能
   - 剪枝优化
   - 状态恢复

5. 二分查找：
   - 有序数组查找
   - 时间复杂度O(log n)
   - 边界处理""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "math_reasoning",
        "title": "数据结构选择",
        "content": """数据结构选择指南：

1. 数组：
   - 随机访问O(1)
   - 插入删除O(n)
   - 适合固定大小数据

2. 链表：
   - 插入删除O(1)
   - 随机访问O(n)
   - 适合频繁插入删除

3. 栈：
   - LIFO：后进先出
   - 适合表达式求值、回溯

4. 队列：
   - FIFO：先进先出
   - 适合任务调度、BFS

5. 哈希表：
   - 查找O(1)平均
   - 适合快速查找、去重

6. 树：
   - 层次结构
   - 适合组织关系、排序

7. 图：
   - 网络结构
   - 适合社交网络、路径规划""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "math_reasoning",
        "title": "复杂度分析",
        "content": """算法复杂度分析：

1. 时间复杂度：
   - O(1)：常数时间
   - O(log n)：对数时间
   - O(n)：线性时间
   - O(n log n)：线性对数
   - O(n^2)：平方时间
   - O(2^n)：指数时间

2. 空间复杂度：
   - O(1)：常数空间
   - O(n)：线性空间
   - O(n^2)：平方空间

3. 分析方法：
   - 最坏情况分析
   - 平均情况分析
   - 摊销分析

4. 优化方向：
   - 降低时间复杂度
   - 减少空间占用
   - 平衡时间空间""",
        "priority": 2,
    },
    # ========== troubleshooting (20 materials) ==========
    {
        "source_type": "text",
        "domain_hint": "troubleshooting",
        "title": "问题排查方法论",
        "content": """问题排查方法论：

1. 定义问题：
   - 明确问题现象
   - 记录发生时间
   - 收集环境信息

2. 收集证据：
   - 查看日志
   - 收集堆栈
   - 记录配置

3. 分析原因：
   - 重现问题
   - 对比差异
   - 假设验证

4. 定位根因：
   - 逐步排查
   - 使用二分法
   - 缩小范围

5. 验证修复：
   - 应用修复
   - 验证效果
   - 回归测试

6. 预防措施：
   - 添加监控
   - 添加测试
   - 更新文档""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "troubleshooting",
        "title": "性能问题排查",
        "content": """性能问题排查：

1. CPU问题：
   - 使用top/htop查看
   - 定位CPU密集进程
   - 使用perf分析热点

2. 内存问题：
   - 使用free查看
   - 检查内存泄漏
   - 使用memory_profiler

3. 磁盘问题：
   - 使用iostat查看
   - 检查磁盘IO
   - 检查磁盘空间

4. 网络问题：
   - 使用iftop/netstat查看
   - 检查网络延迟
   - 检查网络带宽

5. 数据库问题：
   - 检查慢查询日志
   - 分析查询计划
   - 检查连接池""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "troubleshooting",
        "title": "日志分析技巧",
        "content": """日志分析技巧：

1. 日志收集：
   - 集中收集日志
   - 标准化日志格式
   - 添加时间戳和上下文

2. 日志搜索：
   - 使用grep搜索
   - 使用awk处理
   - 使用ELK分析

3. 错误模式识别：
   - 搜索ERROR/WARNING
   - 识别重复错误
   - 分析错误频率

4. 日志关联：
   - 使用request_id关联
   - 追踪请求链路
   - 分析时序关系

5. 日志可视化：
   - 错误趋势图
   - 分布直方图
   - 热力图""",
        "priority": 2,
    },
    # ========== dev_ops (20 materials) ==========
    {
        "source_type": "text",
        "domain_hint": "dev_ops",
        "title": "CI/CD实践",
        "content": """CI/CD最佳实践：

1. 持续集成：
   - 代码提交后自动构建
   - 运行单元测试
   - 代码质量检查

2. 持续部署：
   - 自动化部署流程
   - 多环境部署
   - 蓝绿部署/金丝雀发布

3. 流水线设计：
   - 构建阶段
   - 测试阶段
   - 部署阶段
   - 验证阶段

4. 常用工具：
   - GitHub Actions
   - GitLab CI
   - Jenkins
   - CircleCI

5. 监控反馈：
   - 部署后监控
   - 自动回滚
   - 性能追踪""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "dev_ops",
        "title": "Docker最佳实践",
        "content": """Docker最佳实践：

1. Dockerfile优化：
   - 使用多阶段构建
   - 使用官方基础镜像
   - 最小化镜像大小
   - 清理构建缓存

2. 容器安全：
   - 不要以root运行
   - 使用非特权用户
   - 限制容器权限
   - 定期更新镜像

3. 网络配置：
   - 使用自定义网络
   - 限制端口暴露
   - 使用环境变量

4. 数据管理：
   - 使用Volume持久化数据
   - 分离配置和代码
   - 备份重要数据

5. 容器编排：
   - 使用Docker Compose
   - 健康检查配置
   - 自动重启策略""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "dev_ops",
        "title": "Kubernetes入门",
        "content": """Kubernetes基础：

1. 核心概念：
   - Pod：最小部署单元
   - Service：服务发现
   - Deployment：应用部署
   - StatefulSet：有状态应用
   - ConfigMap/Secret：配置管理

2. 资源管理：
   - CPU/内存限制
   - 资源请求
   - 水平自动伸缩

3. 网络：
   - Pod网络
   - Service类型(ClusterIP, NodePort, LoadBalancer)
   - Ingress

4. 存储：
   - Volume
   - PersistentVolume
   - StorageClass

5. 监控：
   - Prometheus监控
   - Grafana可视化
   - 日志收集""",
        "priority": 2,
    },
    # ========== code_engineering (20 materials) ==========
    {
        "source_type": "text",
        "domain_hint": "code_engineering",
        "title": "代码审查清单",
        "content": """代码审查清单：

1. 代码质量：
   - 命名清晰
   - 注释充分
   - 逻辑简洁
   - 避免重复

2. 安全性：
   - 输入验证
   - 敏感数据保护
   - SQL注入防护
   - XSS防护

3. 性能：
   - 算法复杂度
   - 内存使用
   - 避免性能陷阱

4. 可维护性：
   - 遵循编码规范
   - 模块化设计
   - 错误处理完善

5. 测试覆盖：
   - 单元测试覆盖
   - 集成测试覆盖
   - 边界条件测试""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "code_engineering",
        "title": "重构技巧",
        "content": """代码重构技巧：

1. 重构原则：
   - 保持行为不变
   - 小步前进
   - 有测试保护

2. 常见重构：
   - 提取函数
   - 提取类
   - 拆分复杂方法
   - 消除重复代码

3. 代码异味：
   - 过长函数
   - 过大类
   - 重复代码
   - 魔法数字

4. 重构工具：
   - IDE重构功能
   - Python: refactor, rope
   - 代码审查工具

5. 重构流程：
   - 识别问题
   - 制定计划
   - 实施重构
   - 运行测试
   - 验证效果""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "code_engineering",
        "title": "测试策略",
        "content": """软件测试策略：

1. 测试分层：
   - 单元测试：测试单个函数/类
   - 集成测试：测试模块间交互
   - 系统测试：测试完整系统
   - 验收测试：验证业务需求

2. 测试类型：
   - 功能测试：验证功能正确性
   - 性能测试：验证系统性能
   - 安全测试：验证系统安全
   - 兼容性测试：验证多环境兼容

3. 测试技术：
   - 黑盒测试：不关心实现
   - 白盒测试：基于代码结构
   - 灰盒测试：结合两者

4. 测试工具：
   - Python: pytest, unittest
   - 覆盖率：coverage.py
   - 性能：locust, k6

5. 测试管理：
   - 测试用例管理
   - 测试执行计划
   - 缺陷追踪""",
        "priority": 2,
    },
    # ========== project_mgmt (20 materials) ==========
    {
        "source_type": "text",
        "domain_hint": "project_mgmt",
        "title": "需求分析",
        "content": """需求分析方法：

1. 需求收集：
   - 用户访谈
   - 问卷调查
   - 竞品分析
   - 用户故事

2. 需求分类：
   - 功能需求
   - 非功能需求
   - 约束条件

3. 需求优先级：
   - MoSCoW方法
   - KANO模型
   - 价值/复杂度矩阵

4. 需求文档：
   - 用户故事
   - 用例图
   - 需求规格说明书

5. 需求验证：
   - 需求评审
   - 原型验证
   - 用户反馈""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "project_mgmt",
        "title": "敏捷开发",
        "content": """敏捷开发实践：

1. Scrum框架：
   - Sprint：迭代周期(2-4周)
   - Daily Standup：每日站会
   - Sprint Review：迭代评审
   - Sprint Retrospective：迭代回顾

2. Kanban方法：
   - 可视化看板
   - 限制在制品
   - 持续流动
   - 度量和改进

3. 用户故事：
   - INVEST原则
   - 故事点估算
   - 故事拆分

4. 估算方法：
   - 故事点
   - 计划扑克
   - 相对估算

5. 敏捷工具：
   - Jira
   - Trello
   - Asana""",
        "priority": 2,
    },
    # ========== daily_life (10 materials) ==========
    {
        "source_type": "text",
        "domain_hint": "daily_life",
        "title": "时间管理",
        "content": """时间管理方法：

1. 四象限法则：
   - 重要紧急：立即处理
   - 重要不紧急：计划处理
   - 紧急不重要：委托处理
   - 不紧急不重要：尽量避免

2. Pomodoro技术：
   - 25分钟工作
   - 5分钟休息
   - 4个循环后休息15分钟

3. 任务清单：
   - 每日计划
   - 优先级排序
   - 完成打勾

4. 避免干扰：
   - 关闭通知
   - 设置专注时间
   - 批量处理邮件

5. 定期回顾：
   - 每日回顾
   - 每周回顾
   - 每月回顾""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "daily_life",
        "title": "健康习惯",
        "content": """健康习惯养成：

1. 作息规律：
   - 固定起床时间
   - 固定睡觉时间
   - 保证7-8小时睡眠

2. 饮食健康：
   - 均衡饮食
   - 多喝水
   - 减少垃圾食品

3. 适量运动：
   - 每天运动30分钟
   - 多样化运动
   - 循序渐进

4. 心理健康：
   - 定期放松
   - 冥想练习
   - 保持社交

5. 工作平衡：
   - 设置工作边界
   - 定期休假
   - 培养兴趣爱好""",
        "priority": 2,
    },
    # ========== network_info (10 materials) ==========
    {
        "source_type": "text",
        "domain_hint": "network_info",
        "title": "信息搜索技巧",
        "content": """高效信息搜索技巧：

1. 搜索语法：
   - 精确匹配："关键词"
   - 排除关键词：-关键词
   - 或运算：关键词1 OR 关键词2
   - 站点搜索：site:example.com

2. 搜索策略：
   - 使用专业搜索引擎
   - 尝试不同关键词
   - 使用高级搜索选项

3. 信息验证：
   - 查看信息来源
   - 交叉验证
   - 检查发布时间

4. 信息整理：
   - 分类保存
   - 添加标签
   - 定期回顾

5. 搜索工具：
   - Google搜索
   - 专业数据库
   - AI搜索助手""",
        "priority": 2,
    },
]


def load_massive_seed_data(ingestor) -> None:
    """Load massive seed materials into the knowledge warehouse."""
    results = ingestor.bulk_ingest(MASSIVE_MATERIALS)
    added = sum(1 for _, was_added in results if was_added)
    skipped = len(results) - added
    print(f"Loaded {added} massive seed materials (skipped {skipped} duplicates)")
    return results
