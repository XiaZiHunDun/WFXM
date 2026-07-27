"""Seed data for database domain."""

from __future__ import annotations

from typing import Any, Dict, List

DATABASE_MATERIALS: List[Dict[str, Any]] = [
{
        "source_type": "text",
        "domain_hint": "database",
        "title": "索引设计原则",
        "content": """数据库索引设计原则：

1. 选择合适的列：
   - 常用于WHERE子句的列
   - 常用于JOIN的列
   - 常用于ORDER BY的列

2. 索引类型选择：
   - B-tree：等值查询、范围查询
   - Hash：等值查询
   - GIN：数组、JSONB
   - GIST：全文搜索、空间数据

3. 复合索引：
   - 列的顺序很重要
   - 遵循最左前缀原则
   - 不要创建过多列的索引

4. 索引维护：
   - 定期重建索引
   - 监控索引使用情况
   - 删除未使用的索引""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "database",
        "title": "查询优化技巧",
        "content": """SQL查询优化技巧：

1. 使用EXPLAIN分析查询计划：
   - EXPLAIN ANALYZE：实际执行分析
   - 查看是否使用索引
   - 查看扫描行数

2. 避免全表扫描：
   - 添加适当索引
   - 使用WHERE条件过滤
   - 限制结果集大小

3. 优化JOIN操作：
   - 小表驱动大表
   - 使用合适的JOIN类型
   - 避免笛卡尔积

4. 使用聚合优化：
   - 使用索引覆盖
   - 避免GROUP BY在大表上
   - 使用物化视图

5. 分页优化：
   - 使用键集分页
   - 避免OFFSET分页
   - 限制每页数量""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "database",
        "title": "缓存策略",
        "content": """数据库缓存策略：

1. 查询缓存：
   - 缓存重复查询结果
   - 设置合理的过期时间
   - 缓存失效策略

2. 应用缓存：
   - 使用Redis缓存热点数据
   - 设置缓存分层
   - 缓存穿透防护

3. 数据库缓存：
   - PostgreSQL shared_buffers
   - 操作系统页缓存
   - 索引缓存

4. 缓存一致性：
   - 写后失效
   - 异步更新
   - 版本控制

5. 缓存策略模式：
   - Cache-Aside
   - Read-Through
   - Write-Through
   - Write-Behind""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "database",
        "title": "数据备份与恢复",
        "content": """数据备份与恢复策略：

1. 备份类型：
   - 全量备份：备份所有数据
   - 增量备份：备份变化的数据
   - 差异备份：备份上次全量后的变化

2. 备份工具：
   - pg_dump：PostgreSQL逻辑备份
   - pg_basebackup：PostgreSQL物理备份
   - mysqldump：MySQL备份

3. 备份频率：
   - 根据数据重要性决定
   - 全量备份：每天/每周
   - 增量备份：每小时/每天

4. 备份验证：
   - 定期测试恢复
   - 检查备份完整性
   - 验证数据一致性

5. 恢复策略：
   - 确定恢复点目标(RPO)
   - 确定恢复时间目标(RTO)
   - 制定恢复流程""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "database",
        "title": "分库分表",
        "content": """分库分表策略：

1. 垂直拆分：
   - 按功能拆分
   - 不同业务放在不同数据库
   - 减少单库复杂度

2. 水平拆分：
   - 按数据行拆分
   - 相同表结构分布在多个库
   - 需要路由策略

3. 拆分策略：
   - 按范围拆分
   - 按哈希拆分
   - 按列表拆分

4. 路由策略：
   - 配置路由表
   - 使用中间件(MyCat, ShardingSphere)
   - 应用层路由

5. 挑战：
   - 跨库JOIN
   - 分布式事务
   - 数据一致性""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "database",
        "title": "读写分离",
        "content": """读写分离方案：

1. 架构：
   - 一个主库负责写
   - 多个从库负责读
   - 主从复制同步数据

2. 复制模式：
   - 异步复制：性能高，可能有延迟
   - 同步复制：数据一致，性能低
   - 半同步复制：平衡一致性和性能

3. 读写路由：
   - 应用层路由
   - 中间件路由(ProxySQL, MaxScale)
   - DNS路由

4. 延迟处理：
   - 写后读使用主库
   - 最终一致性场景使用从库
   - 监控复制延迟

5. 故障切换：
   - 自动故障检测
   - 主库切换
   - 从库提升""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "database",
        "title": "连接池管理",
        "content": """数据库连接池管理：

1. 连接池配置：
   - 最小连接数：保持的空闲连接
   - 最大连接数：允许的最大连接
   - 连接超时：等待连接的时间
   - 空闲超时：连接空闲多久后释放

2. 常用连接池：
   - PostgreSQL：pgBouncer
   - MySQL：ProxySQL, Pgpool-II
   - Python：SQLAlchemy连接池

3. 监控指标：
   - 连接池使用率
   - 等待连接时间
   - 连接创建/销毁率

4. 调优策略：
   - 根据并发量调整最大连接数
   - 设置合理的超时时间
   - 定期回收空闲连接""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "database",
        "title": "事务优化",
        "content": """数据库事务优化：

1. 事务隔离级别：
   - READ UNCOMMITTED：允许脏读
   - READ COMMITTED：防止脏读
   - REPEATABLE READ：防止不可重复读
   - SERIALIZABLE：防止幻读

2. 事务优化：
   - 减少事务大小
   - 缩短事务时间
   - 避免长事务

3. 死锁处理：
   - 固定锁的获取顺序
   - 设置事务超时
   - 使用乐观锁

4. 批量操作：
   - 使用批量INSERT
   - 使用COPY命令
   - 避免逐行操作

5. 回滚优化：
   - 避免不必要的回滚
   - 使用SAVEPOINT
   - 预检查数据""",
        "priority": 2,
    },]
