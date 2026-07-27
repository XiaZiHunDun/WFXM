"""Extended seed data for math_reasoning domain."""

from __future__ import annotations

from typing import Any, Dict, List

MATH_REASONING_EXTENDED_MATERIALS: List[Dict[str, Any]] = [
{
        "source_type": "text",
        "domain_hint": "math_reasoning",
        "title": "时间复杂度分析",
        "content": """时间复杂度分析方法：
O(1): 常数时间，操作次数与输入规模无关
O(log n): 对数时间，每次操作将问题规模减半（二分查找）
O(n): 线性时间，操作次数与输入规模成正比（遍历数组）
O(n log n): 线性对数时间（快速排序、归并排序）
O(n^2): 平方时间（嵌套循环）
O(2^n): 指数时间（递归生成子集）

计算规则：
- 忽略常数项：O(2n) → O(n)
- 取最高阶：O(n^2 + n) → O(n^2)
- 乘法规则：嵌套循环相乘""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "math_reasoning",
        "title": "递归公式求解",
        "content": """递归公式求解方法：
1. 展开法：逐步展开递归式
   T(n) = T(n-1) + 1
        = T(n-2) + 2
        = ...
        = T(1) + n-1 = O(n)

2. 主定理：适用于 T(n) = a*T(n/b) + f(n)
   - 如果 f(n) = O(n^c) 且 c < log_b(a): T(n) = O(n^log_b(a))
   - 如果 f(n) = O(n^c) 且 c = log_b(a): T(n) = O(n^c log n)
   - 如果 f(n) = O(n^c) 且 c > log_b(a): T(n) = O(f(n))

3. 代入法：猜测答案并验证""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "math_reasoning",
        "title": "概率论基础",
        "content": """概率论基础：
条件概率：P(A|B) = P(A∩B) / P(B)
贝叶斯定理：P(A|B) = P(B|A) * P(A) / P(B)

期望计算：
E[X] = Σ x * P(X=x)

大数定律：当试验次数足够多时，样本均值趋近于期望

中心极限定理：大量独立随机变量之和趋近于正态分布

概率分布：
- 二项分布：n次独立试验中成功k次的概率
- 泊松分布：单位时间内事件发生k次的概率
- 正态分布：连续随机变量的常见分布""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "math_reasoning",
        "title": "线性代数核心概念",
        "content": """线性代数核心概念：
向量：具有大小和方向的量
矩阵：二维数组，用于表示线性变换

矩阵运算：
- 加法：对应元素相加
- 乘法：行乘列求和，A(m×n) × B(n×p) = C(m×p)
- 转置：行列互换
- 逆矩阵：A × A⁻¹ = I

特征值与特征向量：
Ax = λx，λ是特征值，x是特征向量

奇异值分解（SVD）：
A = UΣV^T，用于降维和推荐系统

行列式：衡量矩阵变换的缩放因子""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "math_reasoning",
        "title": "图论基础",
        "content": """图论基础：
图 G = (V, E)，V是顶点集，E是边集

图类型：
- 有向图/无向图
- 加权图/无权图
- 连通图/非连通图

路径与回路：
- 路径：顶点序列，相邻顶点有边连接
- 回路：起点=终点的路径

最短路径算法：
- Dijkstra：非负权边，贪心算法
- Bellman-Ford：允许负权边，可检测负权回路
- Floyd-Warshall：所有节点对的最短路径

最小生成树：
- Prim：贪心，从顶点扩展
- Kruskal：按边权排序，避圈""",
        "priority": 2,
    },]
