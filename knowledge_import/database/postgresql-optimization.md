# PostgreSQL性能优化

## 查询优化

### EXPLAIN分析

使用EXPLAIN ANALYZE分析查询计划：

```sql
EXPLAIN ANALYZE SELECT * FROM users WHERE email = 'test@example.com';
```

**关键点：**
- 查看是否使用索引
- 检查扫描行数
- 识别性能瓶颈

### 索引优化

**B-tree索引**：适用于等值查询和范围查询
```sql
CREATE INDEX idx_users_email ON users(email);
```

**GIN索引**：适用于JSONB、数组类型
```sql
CREATE INDEX idx_data_tags ON data USING GIN(tags);
```

**复合索引**：遵循最左前缀原则
```sql
CREATE INDEX idx_orders_user_date ON orders(user_id, created_at);
```

### 查询重写技巧

**避免SELECT ***
```sql
-- 不好
SELECT * FROM users;

-- 好
SELECT id, name, email FROM users;
```

**使用JOIN替代子查询**
```sql
-- 子查询
SELECT * FROM orders WHERE user_id IN (SELECT id FROM users WHERE country = 'CN');

-- JOIN
SELECT o.* FROM orders o JOIN users u ON o.user_id = u.id WHERE u.country = 'CN';
```

**使用CTE优化复杂查询**
```sql
WITH recent_orders AS (
    SELECT * FROM orders WHERE created_at > NOW() - INTERVAL '7 days'
)
SELECT COUNT(*) FROM recent_orders WHERE status = 'completed';
```

## 数据库配置优化

### shared_buffers

设置为系统内存的25%-40%：
```ini
shared_buffers = 4GB
```

### work_mem

设置排序和哈希操作的内存：
```ini
work_mem = 64MB
```

### maintenance_work_mem

设置维护操作的内存：
```ini
maintenance_work_mem = 2GB
```

### effective_cache_size

告诉查询优化器可用的缓存大小：
```ini
effective_cache_size = 12GB
```

## 连接池配置

### pgBouncer配置

```ini
[databases]
mydb = host=localhost port=5432 dbname=mydb

[pgbouncer]
listen_port = 6432
listen_addr = *
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 20
```

### 连接池模式

- **session模式**：每个连接独占一个服务器连接
- **transaction模式**：事务级连接复用
- **statement模式**：语句级连接复用（不支持事务）

## 分区表

### 范围分区

```sql
CREATE TABLE orders (
    id BIGINT,
    created_at TIMESTAMP,
    amount NUMERIC
) PARTITION BY RANGE (created_at);

CREATE TABLE orders_2024_q1 PARTITION OF orders
    FOR VALUES FROM ('2024-01-01') TO ('2024-04-01');
```

### 列表分区

```sql
CREATE TABLE users (
    id BIGINT,
    country TEXT
) PARTITION BY LIST (country);

CREATE TABLE users_cn PARTITION OF users
    FOR VALUES IN ('CN', 'HK', 'TW');
```

## 物化视图

### 创建物化视图

```sql
CREATE MATERIALIZED VIEW daily_sales AS
SELECT DATE(created_at) AS day, SUM(amount) AS total
FROM orders
GROUP BY DATE(created_at);
```

### 刷新物化视图

```sql
-- 完全刷新
REFRESH MATERIALIZED VIEW daily_sales;

-- 并发刷新（PostgreSQL 9.4+）
REFRESH MATERIALIZED VIEW CONCURRENTLY daily_sales;
```

### 自动刷新

使用pg_cron定时刷新：
```sql
SELECT cron.schedule('daily_sales_refresh', '0 3 * * *', 
    'REFRESH MATERIALIZED VIEW CONCURRENTLY daily_sales;');
```

## 备份策略

### 逻辑备份

```bash
pg_dump -U username -d dbname -f backup.sql
```

### 物理备份

```bash
pg_basebackup -D /backup/path -X stream -P
```

### 定时备份脚本

```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump -U admin mydb | gzip > /backup/mydb_$DATE.sql.gz
find /backup -type f -mtime +7 -delete
```

## 监控指标

### 关键指标

- **连接数**：`SELECT count(*) FROM pg_stat_activity;`
- **查询等待**：`SELECT * FROM pg_stat_activity WHERE wait_event IS NOT NULL;`
- **锁等待**：`SELECT * FROM pg_locks WHERE NOT granted;`
- **慢查询**：配置`log_min_duration_statement = '100ms'`

### 常用视图

- `pg_stat_user_tables`：表访问统计
- `pg_stat_user_indexes`：索引使用统计
- `pg_stat_statements`：查询性能统计

## 常见问题

### 死锁

**原因**：事务以不同顺序获取锁

**解决方案**：
- 固定锁的获取顺序
- 设置事务超时
- 使用乐观锁

### 连接泄漏

**原因**：应用程序未正确关闭连接

**解决方案**：
- 使用连接池
- 设置连接超时
- 定期检查连接数

### 表膨胀

**原因**：频繁更新/删除导致的空间浪费

**解决方案**：
- 定期VACUUM ANALYZE
- 使用pg_repack重建表
- 考虑分区表

## 总结

PostgreSQL性能优化需要从查询、配置、架构多个层面入手。通过合理的索引设计、查询优化和资源配置，可以显著提升数据库性能。