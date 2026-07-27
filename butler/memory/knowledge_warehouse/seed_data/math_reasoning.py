"""Seed data for math_reasoning domain."""

from __future__ import annotations

from typing import Any, Dict, List

MATH_REASONING_MATERIALS: List[Dict[str, Any]] = [
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
    },]
