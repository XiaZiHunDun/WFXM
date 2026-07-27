"""Seed data for llm_usage domain."""

from __future__ import annotations

from typing import Any, Dict, List

LLM_USAGE_MATERIALS: List[Dict[str, Any]] = [
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
    },]
