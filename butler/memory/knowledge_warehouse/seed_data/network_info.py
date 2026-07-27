"""Seed data for network_info domain."""

from __future__ import annotations

from typing import Any, Dict, List

NETWORK_INFO_MATERIALS: List[Dict[str, Any]] = [
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
