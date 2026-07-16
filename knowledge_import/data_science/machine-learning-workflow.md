# 机器学习工作流程

## 问题定义

### 明确目标

**步骤**：
1. **理解业务需求**：与业务方沟通
2. **定义问题类型**：分类、回归、聚类等
3. **确定评估指标**：准确率、F1分数、RMSE等

**问题类型**：
- **分类**：预测离散标签
- **回归**：预测连续数值
- **聚类**：发现数据模式
- **推荐**：推荐相关物品

### 指标选择

**分类任务**：
- **准确率**：正确预测的比例
- **精确率**：预测为正的样本中真正为正的比例
- **召回率**：真正为正的样本中被预测为正的比例
- **F1分数**：精确率和召回率的调和平均

**回归任务**：
- **RMSE**：均方根误差
- **MAE**：平均绝对误差
- **R²**：决定系数

## 数据收集

### 数据源

**类型**：
- **结构化数据**：数据库、CSV文件
- **非结构化数据**：文本、图像、音频
- **半结构化数据**：JSON、XML

**收集方法**：
- 数据库查询
- API调用
- Web爬取
- 传感器采集

### 数据存储

**工具**：
- **CSV/Excel**：小规模数据
- **SQLite**：本地存储
- **PostgreSQL**：大规模结构化数据
- **MongoDB**：非结构化数据
- **AWS S3**：云端存储

## 数据探索

### 描述性统计

```python
import pandas as pd

df = pd.read_csv("data.csv")

# 基本信息
print(df.info())

# 统计摘要
print(df.describe())

# 数据类型
print(df.dtypes)
```

### 数据可视化

```python
import matplotlib.pyplot as plt
import seaborn as sns

# 直方图
plt.hist(df['age'], bins=20)
plt.xlabel('Age')
plt.ylabel('Count')
plt.show()

# 散点图
sns.scatterplot(x='feature1', y='feature2', data=df)
plt.show()

# 相关矩阵
corr_matrix = df.corr()
sns.heatmap(corr_matrix, annot=True)
plt.show()
```

### 数据质量检查

**检查项**：
- **缺失值**：df.isnull().sum()
- **重复值**：df.duplicated().sum()
- **异常值**：使用箱线图或Z-score
- **数据类型**：检查是否正确

## 特征工程

### 特征提取

**数值特征**：
- 标准化：(x - mean) / std
- 归一化：(x - min) / (max - min)
- 对数变换：log(x)

**类别特征**：
- 独热编码：pd.get_dummies()
- 标签编码：sklearn.LabelEncoder()
- 频率编码：用频率替代类别

**文本特征**：
- TF-IDF：sklearn.TfidfVectorizer()
- Word2Vec：词向量表示
- BERT：上下文向量

### 特征选择

**方法**：
- **过滤法**：相关性分析、方差分析
- **包裹法**：递归特征消除
- **嵌入法**：树模型特征重要性

```python
from sklearn.feature_selection import SelectKBest, f_regression

selector = SelectKBest(f_regression, k=10)
X_selected = selector.fit_transform(X, y)
```

## 模型选择

### 常用模型

**分类模型**：
- **逻辑回归**：简单快速
- **决策树**：可解释性强
- **随机森林**：集成方法，效果好
- **XGBoost**：梯度提升，高性能
- **神经网络**：深度学习

**回归模型**：
- **线性回归**：简单快速
- **岭回归**：正则化线性回归
- **Lasso回归**：特征选择
- **随机森林回归**：非线性关系
- **XGBoost回归**：高性能

### 模型比较

```python
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score

models = {
    'Logistic Regression': LogisticRegression(),
    'Random Forest': RandomForestClassifier()
}

for name, model in models.items():
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    print(f"{name}: {accuracy:.4f}")
```

## 模型训练

### 训练流程

```python
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier

# 划分数据集
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)

# 训练模型
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)
```

### 交叉验证

```python
from sklearn.model_selection import cross_val_score

scores = cross_val_score(model, X, y, cv=5)
print(f"Cross-validation scores: {scores}")
print(f"Mean score: {scores.mean():.4f}")
```

## 模型调优

### 参数调优

```python
from sklearn.model_selection import GridSearchCV

param_grid = {
    'n_estimators': [50, 100, 200],
    'max_depth': [None, 10, 20],
    'min_samples_split': [2, 5, 10]
}

grid_search = GridSearchCV(
    RandomForestClassifier(),
    param_grid,
    cv=5,
    scoring='accuracy'
)

grid_search.fit(X_train, y_train)
print(f"Best parameters: {grid_search.best_params_}")
```

### 超参数优化

**工具**：
- **GridSearchCV**：网格搜索
- **RandomizedSearchCV**：随机搜索
- **Optuna**：贝叶斯优化
- **Hyperopt**：超参数优化

## 模型评估

### 评估指标

```python
from sklearn.metrics import classification_report

y_pred = model.predict(X_test)
print(classification_report(y_test, y_pred))
```

### 混淆矩阵

```python
from sklearn.metrics import confusion_matrix
import seaborn as sns

cm = confusion_matrix(y_test, y_pred)
sns.heatmap(cm, annot=True, fmt='d')
plt.xlabel('Predicted')
plt.ylabel('Actual')
plt.show()
```

### 模型解释

```python
from sklearn.inspection import permutation_importance

result = permutation_importance(model, X_test, y_test, n_repeats=10)
print(f"Feature importances: {result.importances_mean}")
```

## 模型部署

### 模型保存

```python
import joblib

# 保存模型
joblib.dump(model, 'model.pkl')

# 加载模型
model = joblib.load('model.pkl')
```

### API服务

```python
from fastapi import FastAPI
import joblib

app = FastAPI()
model = joblib.load('model.pkl')

@app.post("/predict")
async def predict(data: dict):
    features = list(data.values())
    prediction = model.predict([features])
    return {"prediction": int(prediction[0])}
```

### 监控维护

**监控指标**：
- 模型准确率
- 预测延迟
- 数据分布变化
- 漂移检测

**维护策略**：
- 定期重新训练
- 监控数据质量
- 更新模型版本

## 机器学习流水线

### Pipeline构建

```python
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier

pipeline = Pipeline([
    ('scaler', StandardScaler()),
    ('classifier', RandomForestClassifier())
])

pipeline.fit(X_train, y_train)
```

### 完整流程

```
数据收集 → 数据探索 → 特征工程 → 模型训练 → 模型评估 → 模型部署
              ↓              ↓              ↓
           数据清洗       特征选择       参数调优
```

## 常见问题

### 过拟合

**原因**：模型过于复杂，学习到训练数据的噪声

**解决方案**：
- 增加训练数据
- 使用正则化
- 减少模型复杂度
- 使用交叉验证

### 数据不平衡

**原因**：不同类别的样本数量差异很大

**解决方案**：
- 过采样：增加少数类样本
- 欠采样：减少多数类样本
- 使用加权损失函数
- 合成新样本（SMOTE）

### 特征泄露

**原因**：训练过程中使用了测试数据的信息

**解决方案**：
- 使用Pipeline确保数据隔离
- 在训练集上进行特征工程
- 避免数据泄露到模型中

## 总结

机器学习工作流程包括问题定义、数据收集、数据探索、特征工程、模型选择、模型训练、模型调优、模型评估和模型部署等步骤。通过系统化的流程和工具，可以构建高质量的机器学习模型。