"""Seed data for data_science domain."""

from __future__ import annotations

from typing import Any, Dict, List

DATA_SCIENCE_MATERIALS: List[Dict[str, Any]] = [
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
    },]
