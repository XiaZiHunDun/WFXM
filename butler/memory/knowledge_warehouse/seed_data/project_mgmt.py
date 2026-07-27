"""Seed data for project_mgmt domain."""

from __future__ import annotations

from typing import Any, Dict, List

PROJECT_MGMT_MATERIALS: List[Dict[str, Any]] = [
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
    },]
