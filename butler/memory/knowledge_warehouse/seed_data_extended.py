"""Extended seed data — comprehensive knowledge for all domains."""

from __future__ import annotations

from typing import Any, Dict, List

EXTENDED_MATERIALS: List[Dict[str, Any]] = [
    # ========== math_reasoning ==========
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
    },
    # ========== troubleshooting ==========
    {
        "source_type": "text",
        "domain_hint": "troubleshooting",
        "title": "Python调试技巧",
        "content": """Python调试技巧：
1. 使用print()快速定位
2. 使用pdb交互式调试：
   - pdb.set_trace() 设置断点
   - n: next（执行下一行）
   - s: step（进入函数）
   - c: continue（继续执行）
   - l: list（查看代码）
   - p: print（打印变量）

3. 使用logging模块记录日志
4. 使用assert进行断言检查
5. 使用IDE调试器（PyCharm、VSCode）
6. 使用traceback模块获取详细错误信息
7. 使用cProfile分析性能瓶颈""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "troubleshooting",
        "title": "内存泄漏排查",
        "content": """内存泄漏排查方法：
1. 使用memory_profiler监控内存使用
2. 使用objgraph查找对象引用链
3. 检查全局变量是否持有对象引用
4. 检查闭包是否捕获了大对象
5. 检查缓存是否无限增长
6. 检查线程/进程是否正常退出
7. 使用gc模块手动触发垃圾回收

常见内存泄漏场景：
- 全局列表不断追加数据
- 缓存未设置过期策略
- 事件监听器未移除
- 文件句柄未关闭
- 数据库连接未释放""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "troubleshooting",
        "title": "并发问题排查",
        "content": """并发问题排查：
死锁检测：
1. 查看线程堆栈（threading.enumerate()）
2. 检查锁的获取顺序是否一致
3. 使用timeout参数避免永久等待
4. 使用threading.Lock().locked()检查状态

竞态条件：
1. 使用threading.Lock保护共享资源
2. 使用queue模块进行线程间通信
3. 使用原子操作（如multiprocessing.Value）

死锁预防：
- 固定锁的获取顺序
- 使用可重入锁（RLock）
- 设置超时
- 使用上下文管理器（with lock:）""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "troubleshooting",
        "title": "网络问题排查",
        "content": """网络问题排查：
1. ping 检查连通性
2. telnet/netcat 检查端口是否开放
3. curl 检查HTTP服务
4. tcpdump/wireshark 抓包分析
5. netstat/ss 查看网络连接状态
6. traceroute/mtr 检查路由路径

常见网络错误：
- Connection refused：端口未监听
- Connection timed out：网络不通或防火墙阻挡
- DNS resolution failed：域名解析问题
- SSL certificate error：证书问题

HTTP状态码：
- 4xx：客户端错误（404, 401, 403）
- 5xx：服务器错误（500, 502, 503）""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "troubleshooting",
        "title": "数据库性能问题",
        "content": """数据库性能问题排查：
1. 使用EXPLAIN ANALYZE分析查询计划
2. 检查慢查询日志
3. 查看索引使用情况
4. 检查连接池状态
5. 分析锁等待情况

常见性能问题：
- 全表扫描：缺少索引
- 索引失效：WHERE条件使用函数
- 连接过多：连接池配置不当
- 死锁：并发事务冲突

优化策略：
- 添加合适索引
- 优化查询语句
- 增加缓存层
- 分库分表""",
        "priority": 2,
    },
    # ========== security ==========
    {
        "source_type": "text",
        "domain_hint": "security",
        "title": "密码安全",
        "content": """密码安全最佳实践：
1. 使用bcrypt/scrypt/Argon2进行密码哈希
2. 不要使用MD5/SHA-1等弱哈希算法
3. 使用随机盐值（至少16字节）
4. 限制密码尝试次数（最多5次）
5. 强制密码复杂度要求
6. 使用HTTPS传输密码
7. 不要在日志中记录密码

密码哈希示例（Python）：
import bcrypt
salt = bcrypt.gensalt()
hashed = bcrypt.hashpw(password.encode(), salt)
if bcrypt.checkpw(password.encode(), hashed):
    print('密码正确')""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "security",
        "title": "JWT认证",
        "content": """JWT认证安全实践：
1. 使用HS256或RS256算法
2. 密钥长度至少32字节
3. 设置合理的过期时间（短令牌）
4. 使用refresh_token获取新令牌
5. 不要在JWT中存储敏感信息
6. 通过HTTPS传输JWT
7. 实现令牌黑名单机制

JWT结构：
Header: {"alg": "HS256", "typ": "JWT"}
Payload: {"sub": "user123", "exp": 1234567890}
Signature: HMACSHA256(base64(header)+"."+base64(payload), secret)""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "security",
        "title": "SQL注入防护",
        "content": """SQL注入防护方法：
1. 使用参数化查询（Prepared Statement）
2. 使用ORM框架（SQLAlchemy, Django ORM）
3. 对用户输入进行验证和过滤
4. 使用白名单验证输入格式
5. 禁止拼接SQL字符串

安全示例：
# Bad: 字符串拼接
query = f"SELECT * FROM users WHERE username = '{username}'"

# Good: 参数化查询
query = "SELECT * FROM users WHERE username = %s"
cursor.execute(query, (username,))

# Good: ORM
User.query.filter_by(username=username).first()""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "security",
        "title": "XSS攻击防护",
        "content": """XSS攻击防护方法：
1. 对用户输入进行HTML转义
2. 使用安全的模板引擎（自动转义）
3. 设置Content-Security-Policy头
4. 对输出内容进行编码
5. 禁止内联脚本和eval()

XSS类型：
- 存储型XSS：恶意代码存储在服务器
- 反射型XSS：恶意代码通过URL参数传递
- DOM型XSS：恶意代码在客户端执行

防护示例：
# HTML转义
import html
safe_content = html.escape(user_input)

# CSP头
Content-Security-Policy: default-src 'self'; script-src 'self'""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "security",
        "title": "CSRF防护",
        "content": """CSRF防护方法：
1. 使用CSRF Token
2. 验证Referer头
3. 使用SameSite Cookie属性
4. 对敏感操作使用POST方法
5. 使用双重提交Cookie

CSRF Token实现：
- 在表单中添加隐藏字段
- 在AJAX请求中添加自定义Header
- 服务端验证Token是否有效

SameSite属性：
- Strict：仅同站点发送Cookie
- Lax：允许GET请求跨站点发送
- None：允许跨站点发送（需要Secure）""",
        "priority": 2,
    },
    # ========== data_science ==========
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
    },
    # ========== system_admin ==========
    {
        "source_type": "text",
        "domain_hint": "system_admin",
        "title": "Linux常用命令",
        "content": """Linux常用命令：
文件操作：
- ls：列出目录内容
- cd：切换目录
- pwd：显示当前目录
- mkdir：创建目录
- rm：删除文件/目录
- cp：复制文件
- mv：移动/重命名文件

系统管理：
- ps：查看进程
- top/htop：实时进程监控
- kill：终止进程
- systemctl：管理系统服务
- df：磁盘使用情况
- free：内存使用情况
- uptime：系统运行时间

网络：
- ifconfig/ip addr：网络接口信息
- ping：网络连通性测试
- curl/wget：下载文件
- ssh：远程登录""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "system_admin",
        "title": "Shell脚本编写",
        "content": """Shell脚本编写技巧：
1. 脚本头：#!/bin/bash

2. 变量：
   name="value"
   echo $name

3. 参数：
   $0：脚本名
   $1-$9：位置参数
   $@：所有参数

4. 条件判断：
   if [ condition ]; then
       commands
   fi

5. 循环：
   for i in {1..10}; do echo $i; done
   while [ condition ]; do commands; done

6. 函数：
   function_name() {
       commands
   }

7. 退出码：
   exit 0：成功
   exit 1：失败

8. 调试：
   bash -x script.sh""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "system_admin",
        "title": "Nginx配置",
        "content": """Nginx配置要点：
1. 基本配置结构：
   http {
       server {
           listen 80;
           server_name example.com;
           root /var/www/html;
           index index.html;
       }
   }

2. 反向代理：
   location /api/ {
       proxy_pass http://localhost:8000;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
   }

3. HTTPS配置：
   listen 443 ssl;
   ssl_certificate /path/to/cert.pem;
   ssl_certificate_key /path/to/key.pem;
   ssl_protocols TLSv1.2 TLSv1.3;

4. Gzip压缩：
   gzip on;
   gzip_types text/plain text/css application/json;

5. 访问日志：
   access_log /var/log/nginx/access.log;""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "system_admin",
        "title": "进程管理",
        "content": """进程管理技巧：
1. 查看进程：
   ps aux：列出所有进程
   ps aux | grep python：过滤进程
   top：实时监控
   htop：交互式监控

2. 终止进程：
   kill PID：优雅终止
   kill -9 PID：强制终止
   pkill name：按名称终止

3. 后台运行：
   command &：后台运行
   nohup command &：不受logout影响
   screen/tmux：持久化会话

4. 系统服务：
   systemctl start service
   systemctl stop service
   systemctl status service
   systemctl enable service：开机自启""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "system_admin",
        "title": "文件权限",
        "content": """Linux文件权限：
权限表示：
- r：读（4）
- w：写（2）
- x：执行（1）

权限结构：
-rwxrwxrwx
所有者 组 用户

修改权限：
chmod 755 file：rwxr-xr-x
chmod +x script.sh：添加执行权限
chmod -w file：移除写权限

修改所有者：
chown user:group file

特殊权限：
- SUID：执行时使用文件所有者权限
- SGID：执行时使用文件组权限
- sticky bit：只有所有者可删除目录内文件

常见权限：
- 755：目录和可执行文件
- 644：普通文件
- 700：私有目录""",
        "priority": 2,
    },
    # ========== 扩展原有领域知识 ==========
    # agent_dev
    {
        "source_type": "text",
        "domain_hint": "agent_dev",
        "title": "工具调用最佳实践",
        "content": """工具调用最佳实践：
1. 参数验证：调用前检查参数类型和范围
2. 结果验证：调用后检查返回值格式和有效性
3. 错误处理：捕获异常并记录失败原因
4. 超时控制：设置合理的超时时间
5. 重试机制：网络请求失败时自动重试
6. 并发控制：限制并发调用数量
7. 日志记录：记录调用参数和结果
8. 成本控制：避免不必要的工具调用

工具调用流程：
1. 用户输入分析
2. 选择合适工具
3. 构建工具参数
4. 执行工具调用
5. 解析工具输出
6. 总结并回复用户""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "agent_dev",
        "title": "对话状态管理",
        "content": """对话状态管理：
状态组成：
- 对话历史：用户和助手的消息记录
- 任务状态：当前任务的进度和状态
- 工具状态：已调用的工具和结果
- 用户状态：用户偏好和上下文信息

状态更新策略：
- 轮次级：每轮更新对话历史
- 任务级：任务完成后更新任务状态
- 会话级：会话结束后持久化状态

状态压缩：
- 删除冗余信息
- 生成摘要
- 保留关键决策

状态恢复：
- 从持久化存储加载
- 重建对话上下文
- 恢复任务进度""",
        "priority": 2,
    },
    # database
    {
        "source_type": "text",
        "domain_hint": "database",
        "title": "数据库事务",
        "content": """数据库事务ACID：
Atomicity（原子性）：事务要么全部成功，要么全部失败
Consistency（一致性）：事务前后数据状态一致
Isolation（隔离性）：事务之间相互隔离
Durability（持久性）：提交后数据永久保存

事务隔离级别：
- READ UNCOMMITTED：可读取未提交数据
- READ COMMITTED：只能读取已提交数据
- REPEATABLE READ：同一事务内读取结果一致
- SERIALIZABLE：最高隔离级别，串行执行

事务使用：
BEGIN TRANSACTION;
-- 执行操作
COMMIT;  -- 提交
ROLLBACK;  -- 回滚

死锁预防：
- 固定锁的获取顺序
- 设置事务超时
- 使用乐观锁""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "database",
        "title": "MongoDB使用",
        "content": """MongoDB使用技巧：
查询操作：
db.collection.find({key: value})
db.collection.findOne({key: value})
db.collection.find().limit(10)
db.collection.find().sort({key: 1})

索引：
db.collection.createIndex({key: 1})
db.collection.createIndex({key1: 1, key2: -1})
db.collection.getIndexes()

聚合：
db.collection.aggregate([
    {$match: {category: "books"}},
    {$group: {_id: "$author", count: {$sum: 1}}}
])

更新：
db.collection.updateOne(
    {_id: ObjectId("...")},
    {$set: {field: "value"}}
)

删除：
db.collection.deleteOne({key: value})
db.collection.deleteMany({key: value})""",
        "priority": 2,
    },
    # llm_usage
    {
        "source_type": "text",
        "domain_hint": "llm_usage",
        "title": "API调用优化",
        "content": """LLM API调用优化：
1. 缓存机制：缓存相同请求的结果
2. 批处理：合并多个小请求
3. 流式响应：减少等待时间
4. 超时设置：避免长时间等待
5. 重试机制：指数退避重试
6. 模型选择：根据任务选择合适模型
7. 参数调优：调整temperature等参数
8. 请求大小：限制输入token数量

成本优化：
- 使用较小的模型处理简单任务
- 使用embedding缓存避免重复计算
- 压缩上下文长度
- 批量处理相似请求

错误处理：
- 网络错误：重试
- 限流错误：等待后重试
- 内容安全错误：检查输入内容""",
        "priority": 2,
    },
    # dev_ops
    {
        "source_type": "text",
        "domain_hint": "dev_ops",
        "title": "监控告警",
        "content": """监控告警配置：
1. 指标采集：
   - CPU使用率
   - 内存使用率
   - 磁盘使用率
   - 网络流量
   - 请求延迟

2. 告警规则：
   - CPU > 80% 持续5分钟
   - 内存 > 85%
   - 磁盘 > 90%
   - 请求延迟 > 1s

3. 告警渠道：
   - 邮件
   - 短信
   - 钉钉/飞书
   - 电话

4. 监控工具：
   - Prometheus + Grafana
   - ELK Stack
   - Datadog
   - New Relic

5. 告警处理流程：
   - 收到告警
   - 确认问题
   - 定位根因
   - 解决问题
   - 恢复服务""",
        "priority": 2,
    },
    # code_engineering
    {
        "source_type": "text",
        "domain_hint": "code_engineering",
        "title": "设计模式",
        "content": """常用设计模式：
创建型模式：
- 工厂模式：封装对象创建过程
- 单例模式：确保只有一个实例
- 建造者模式：分步构建复杂对象
- 原型模式：通过复制创建对象

结构型模式：
- 适配器模式：转换接口
- 装饰器模式：动态添加功能
- 代理模式：控制对象访问
- 组合模式：树形结构

行为型模式：
- 观察者模式：事件通知
- 策略模式：算法替换
- 模板方法：固定流程
- 状态模式：状态驱动行为

设计原则：
- 开闭原则：对扩展开放，对修改关闭
- 单一职责：一个类只做一件事
- 依赖倒置：依赖抽象而非具体""",
        "priority": 2,
    },
    # project_mgmt
    {
        "source_type": "text",
        "domain_hint": "project_mgmt",
        "title": "风险管理",
        "content": """风险管理流程：
1. 风险识别：列出可能的风险
2. 风险评估：评估可能性和影响
3. 风险应对：制定应对策略
4. 风险监控：持续监控风险

风险应对策略：
- 规避：改变计划避免风险
- 转移：将风险转移给第三方
- 缓解：降低风险的可能性或影响
- 接受：接受风险的后果

常见风险：
- 技术风险：技术难题、技术过时
- 人员风险：人员流失、技能不足
- 进度风险：进度延迟、需求变更
- 成本风险：预算超支、资源不足

风险登记册：
- 风险描述
- 可能性（高/中/低）
- 影响（高/中/低）
- 应对措施
- 责任人""",
        "priority": 2,
    },
    # daily_life
    {
        "source_type": "text",
        "domain_hint": "daily_life",
        "title": "学习方法",
        "content": """高效学习方法：
1. 主动学习：积极思考而非被动接收
2. 间隔重复：定期复习强化记忆
3. 费曼技巧：用简单语言解释复杂概念
4. 思维导图：可视化知识结构
5. 刻意练习：专注于薄弱环节
6. 输出倒逼输入：写作、分享、教学

学习计划：
- 明确学习目标
- 制定学习计划
- 分解学习任务
- 定期回顾总结

知识管理：
- 建立个人知识库
- 使用标签分类
- 定期清理整理
- 实践应用知识""",
        "priority": 2,
    },
]


def load_extended_seed_data(ingestor) -> None:
    """Load extended seed materials into the knowledge warehouse."""
    results = ingestor.bulk_ingest(EXTENDED_MATERIALS)
    added = sum(1 for _, was_added in results if was_added)
    skipped = len(results) - added
    print(f"Loaded {added} extended seed materials (skipped {skipped} duplicates)")
    return results
