"""Extended seed data for data_science domain."""

from __future__ import annotations

from typing import Any, Dict, List

DATA_SCIENCE_EXTENDED_MATERIALS: List[Dict[str, Any]] = [
{
        "source_type": "text",
        "domain_hint": "data_science",
        "title": "Pandas数据处理",
        "content": """Pandas数据处理技巧：
1. 读取数据：pd.read_csv(), pd.read_json(), pd.read_sql()
2. 数据查看：df.head(), df.info(), df.describe()
3. 数据清洗：
   - df.dropna() 去除缺失值
   - df.fillna() 填充缺失值
   - df.drop_duplicates() 去重
   - df.astype() 类型转换

4. 数据筛选：
   - df.loc[row_condition, col_names] 标签索引
   - df.iloc[row_index, col_index] 位置索引

5. 数据聚合：
   - df.groupby().agg()
   - df.pivot_table()

6. 数据合并：
   - pd.merge() 数据库式连接
   - pd.concat() 堆叠""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "data_science",
        "title": "特征工程",
        "content": """特征工程技巧：
1. 数值特征：
   - 标准化：(x - mean) / std
   - 归一化：(x - min) / (max - min)
   - 对数变换：log(x)，处理长尾分布

2. 类别特征：
   - 独热编码：pd.get_dummies()
   - 标签编码：LabelEncoder()
   - 目标编码：用目标变量的均值替换类别

3. 时间特征：
   - 提取年、月、日、小时
   - 计算时间差
   - 周期性特征（sin/cos编码）

4. 特征选择：
   - 相关性分析
   - 方差选择
   - 互信息""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "data_science",
        "title": "机器学习模型选择",
        "content": """机器学习模型选择指南：
分类问题：
- 数据量小：逻辑回归、朴素贝叶斯
- 数据量大：随机森林、XGBoost、神经网络
- 高维数据：SVM、PCA降维后再分类
- 文本数据：TF-IDF + 分类器

回归问题：
- 线性关系：线性回归、Ridge、Lasso
- 非线性关系：随机森林、XGBoost、神经网络

聚类问题：
- 球形簇：K-Means
- 非球形簇：DBSCAN、层次聚类

评估指标：
- 分类：准确率、精确率、召回率、F1、AUC
- 回归：MAE、MSE、RMSE、R²""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "data_science",
        "title": "数据可视化",
        "content": """数据可视化技巧：
1. Matplotlib基础：
   - plt.plot() 折线图
   - plt.bar() 柱状图
   - plt.hist() 直方图
   - plt.scatter() 散点图

2. Seaborn高级：
   - sns.lineplot()
   - sns.barplot()
   - sns.heatmap() 热力图
   - sns.pairplot() 成对关系图

3. 可视化原则：
   - 选择合适的图表类型
   - 添加标题和标签
   - 使用清晰的配色
   - 避免图表垃圾

4. 交互式可视化：
   - Plotly：交互式图表
   - Bokeh：交互式仪表盘""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "data_science",
        "title": "模型评估与调优",
        "content": """模型评估与调优：
1. 交叉验证：
   - K-Fold：数据分成K份，轮流作为验证集
   - Stratified K-Fold：保持类别比例

2. 超参数调优：
   - GridSearchCV：网格搜索
   - RandomizedSearchCV：随机搜索
   - Bayesian Optimization：贝叶斯优化

3. 模型选择：
   - 比较不同模型的交叉验证分数
   - 使用学习曲线判断过拟合/欠拟合

4. 集成方法：
   - Bagging：并行训练多个模型取平均
   - Boosting：串行训练，每个模型纠正前一个的错误
   - Stacking：用多个模型的输出训练元模型""",
        "priority": 2,
    },]
