"""Seed data for daily_life domain."""

from __future__ import annotations

from typing import Any, Dict, List

DAILY_LIFE_MATERIALS: List[Dict[str, Any]] = [
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
    },]
