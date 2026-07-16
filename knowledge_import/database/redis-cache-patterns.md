# Redis缓存设计模式

## 缓存策略模式

### Cache-Aside（旁路缓存）

**流程**：
1. 应用先查缓存
2. 缓存命中则返回
3. 缓存未命中则查数据库
4. 更新缓存后返回

**优点**：简单易懂，实现灵活
**缺点**：存在缓存一致性问题

```python
def get_user(user_id):
    # 先查缓存
    user = redis.get(f"user:{user_id}")
    if user:
        return json.loads(user)
    
    # 缓存未命中，查数据库
    user = db.query("SELECT * FROM users WHERE id = %s", user_id)
    
    # 更新缓存
    redis.set(f"user:{user_id}", json.dumps(user), ex=3600)
    
    return user
```

### Read-Through（穿透读取）

**流程**：
1. 应用只与缓存交互
2. 缓存负责读取数据库
3. 缓存更新后返回

**优点**：应用代码简化，缓存逻辑集中
**缺点**：需要定制缓存实现

### Write-Through（穿透写入）

**流程**：
1. 应用写入缓存
2. 缓存同步写入数据库
3. 返回写入结果

**优点**：数据一致性强
**缺点**：写入延迟增加

### Write-Behind（异步写入）

**流程**：
1. 应用写入缓存
2. 缓存异步写入数据库
3. 立即返回写入结果

**优点**：写入性能高
**缺点**：存在数据丢失风险

## 缓存优化技巧

### 缓存键设计

**命名规范**：
```
{业务}:{类型}:{id}
user:info:123
product:detail:456
order:status:789
```

**避免过长**：
- 键长度控制在100字符以内
- 使用哈希缩短长键

**使用结构化键**：
```python
def get_cache_key(user_id, category):
    return f"user:{user_id}:category:{category}"
```

### 过期策略

**固定过期时间**：
```python
redis.set("key", "value", ex=3600)  # 1小时过期
```

**滑动过期时间**：
```python
# 每次访问延长过期时间
redis.set("key", "value", ex=3600)
redis.expire("key", 3600)  # 访问时刷新
```

**主动过期**：
```python
# 数据更新时主动删除缓存
def update_user(user_id, data):
    db.update(data)
    redis.delete(f"user:{user_id}")
```

### 缓存预热

**启动时预热**：
```python
def warmup_cache():
    hot_users = db.query("SELECT id FROM users WHERE is_active = 1 LIMIT 1000")
    for user in hot_users:
        user_data = db.get_user(user.id)
        redis.set(f"user:{user.id}", json.dumps(user_data), ex=3600)
```

**定时任务预热**：
```bash
# 每天凌晨3点预热
0 3 * * * python warmup_cache.py
```

## 缓存问题处理

### 缓存穿透

**原因**：查询不存在的数据，导致每次都查数据库

**解决方案**：
- 缓存空值
- 使用布隆过滤器
- 接口层参数校验

```python
def get_user(user_id):
    user = redis.get(f"user:{user_id}")
    if user == "NULL":  # 缓存空值标记
        return None
    if user:
        return json.loads(user)
    
    user = db.get_user(user_id)
    if user:
        redis.set(f"user:{user_id}", json.dumps(user), ex=3600)
    else:
        redis.set(f"user:{user_id}", "NULL", ex=60)  # 缓存空值60秒
    
    return user
```

### 缓存击穿

**原因**：热点数据过期，大量请求同时穿透到数据库

**解决方案**：
- 分布式锁
- 随机过期时间
- 永不过期（主动更新）

```python
def get_hot_product(product_id):
    key = f"product:{product_id}"
    product = redis.get(key)
    
    if not product:
        # 使用分布式锁
        lock = redis.lock(f"lock:{product_id}", timeout=5)
        if lock.acquire(blocking=True, timeout=1):
            try:
                # 再次检查缓存
                product = redis.get(key)
                if not product:
                    product = db.get_product(product_id)
                    redis.set(key, json.dumps(product), ex=3600)
            finally:
                lock.release()
    
    return json.loads(product) if product else None
```

### 缓存雪崩

**原因**：大量缓存同时过期，导致数据库压力剧增

**解决方案**：
- 设置随机过期时间
- 多级缓存
- 限流降级

```python
# 添加随机因子，避免同时过期
redis.set("key", "value", ex=3600 + random.randint(0, 300))
```

## Redis数据结构

### String

**用途**：缓存简单数据、计数器
```python
redis.set("counter", 100)
redis.incr("counter")  # 原子递增
```

### Hash

**用途**：缓存对象、用户信息
```python
redis.hset("user:123", mapping={"name": "John", "age": 30})
redis.hgetall("user:123")
```

### List

**用途**：队列、消息列表
```python
redis.lpush("queue", "task1")
redis.rpop("queue")
```

### Set

**用途**：去重、交集并集
```python
redis.sadd("tags", "python", "redis")
redis.smembers("tags")
```

### Sorted Set

**用途**：排行榜、计分系统
```python
redis.zadd("leaderboard", {"Alice": 100, "Bob": 80})
redis.zrevrange("leaderboard", 0, 9, withscores=True)
```

## Redis集群

### 主从复制

**配置**：
```ini
# 从节点配置
slaveof master_host master_port
```

**用途**：读写分离，提高读性能

### Sentinel

**用途**：自动故障转移
```ini
sentinel monitor mymaster 127.0.0.1 6379 2
sentinel down-after-milliseconds mymaster 30000
sentinel failover-timeout mymaster 180000
```

### Cluster

**配置**：
```bash
redis-cli --cluster create \
    127.0.0.1:7000 127.0.0.1:7001 127.0.0.1:7002 \
    127.0.0.1:7003 127.0.0.1:7004 127.0.0.1:7005 \
    --cluster-replicas 1
```

**用途**：水平扩展，分布式存储

## 监控与运维

### 常用命令

```bash
redis-cli info  # 查看服务器信息
redis-cli info memory  # 内存使用
redis-cli info stats  # 统计信息
redis-cli monitor  # 实时监控命令
```

### 内存管理

```ini
maxmemory 10gb
maxmemory-policy allkeys-lru
```

**淘汰策略**：
- `allkeys-lru`：移除最近最少使用的key
- `volatile-lru`：移除最近最少使用的带过期时间的key
- `allkeys-random`：随机移除key
- `volatile-ttl`：移除即将过期的key

## 总结

Redis缓存设计需要考虑缓存策略、过期时间、数据结构选择等多个方面。通过合理的设计和优化，可以显著提升系统性能和稳定性。