# 调试技术指南

## 调试方法论

### 定义问题

**步骤**：
1. **记录现象**：详细描述问题表现
2. **确定范围**：问题影响哪些功能
3. **收集信息**：时间、环境、操作步骤

**信息清单**：
- 错误消息和堆栈跟踪
- 系统日志
- 配置文件
- 环境变量

### 重现问题

**目标**：
- 在受控环境中重现问题
- 确认问题的可重复性
- 缩小问题范围

**方法**：
- 使用相同的输入数据
- 模拟相同的操作流程
- 复现相同的环境条件

### 分析原因

**技术**：
- **日志分析**：查看相关日志
- **代码审查**：检查相关代码
- **调试工具**：使用调试器

**技巧**：
- 使用二分法定位问题
- 从错误消息入手
- 检查最近的代码变更

### 验证修复

**步骤**：
1. 应用修复
2. 验证问题是否解决
3. 运行回归测试
4. 确认没有引入新问题

## 日志调试

### 日志级别

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

logger.debug("详细调试信息")
logger.info("一般信息")
logger.warning("警告信息")
logger.error("错误信息")
logger.critical("严重错误")
```

### 日志格式

```python
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
```

### 结构化日志

```python
import json

logger.info(json.dumps({
    "event": "user_login",
    "user_id": 123,
    "status": "success",
    "latency_ms": 45
}))
```

## 代码调试

### Python调试器

```python
import pdb

def debug_function():
    x = 10
    y = 20
    pdb.set_trace()  # 断点
    result = x + y
    return result
```

**常用命令**：
- `n`：下一步
- `s`：进入函数
- `c`：继续执行
- `p variable`：打印变量
- `l`：查看代码
- `q`：退出调试

### 远程调试

```python
import debugpy

debugpy.listen(("0.0.0.0", 5678))
debugpy.wait_for_client()
```

### 日志替代调试

```python
def process_data(data):
    logger.debug(f"Input data: {data}")
    
    result = []
    for item in data:
        logger.debug(f"Processing item: {item}")
        processed = transform(item)
        logger.debug(f"Processed result: {processed}")
        result.append(processed)
    
    logger.debug(f"Final result: {result}")
    return result
```

## 性能调试

### 性能分析工具

```bash
# 使用cProfile
python -m cProfile -o profile_results.prof myscript.py

# 分析结果
python -m pstats profile_results.prof
```

**常用命令**：
- `sort cumulative`：按累计时间排序
- `stats 10`：显示前10个函数
- `list function_name`：查看函数详情

### 内存分析

```bash
# 使用memory_profiler
python -m memory_profiler myscript.py
```

```python
from memory_profiler import profile

@profile
def memory_intensive_function():
    # 内存密集型操作
    pass
```

### 时间分析

```python
import time

start_time = time.time()

# 执行代码
result = expensive_operation()

end_time = time.time()
print(f"Execution time: {end_time - start_time:.2f} seconds")
```

## 数据库调试

### 查询分析

```sql
EXPLAIN ANALYZE SELECT * FROM users WHERE country = 'CN';
```

**分析要点**：
- 是否使用索引
- 扫描行数
- 执行时间
- 瓶颈位置

### 慢查询日志

```ini
# MySQL配置
slow_query_log = 1
slow_query_log_file = /var/log/mysql/slow.log
long_query_time = 2
```

### 连接池监控

```sql
-- PostgreSQL连接数
SELECT count(*) FROM pg_stat_activity;

-- 等待事件
SELECT wait_event, count(*) FROM pg_stat_activity GROUP BY wait_event;
```

## 网络调试

### 网络抓包

```bash
# 使用tcpdump
tcpdump -i eth0 port 80 -w capture.pcap

# 使用Wireshark分析
wireshark capture.pcap
```

### 请求追踪

```python
import requests

response = requests.get("https://api.example.com/data")
print(f"Status code: {response.status_code}")
print(f"Headers: {response.headers}")
print(f"Content: {response.text}")
```

### 延迟测试

```bash
ping api.example.com
curl -w "Time: %{time_total}s\n" https://api.example.com
```

## 并发调试

### 死锁检测

```python
import threading
import time

lock1 = threading.Lock()
lock2 = threading.Lock()

def thread1():
    lock1.acquire()
    time.sleep(0.1)
    lock2.acquire()  # 死锁！

def thread2():
    lock2.acquire()
    time.sleep(0.1)
    lock1.acquire()  # 死锁！
```

**解决方案**：
- 固定锁的获取顺序
- 使用超时机制
- 使用无锁数据结构

### 竞态条件

```python
import threading

counter = 0

def increment():
    global counter
    for _ in range(100000):
        counter += 1

threads = [threading.Thread(target=increment) for _ in range(10)]
for t in threads:
    t.start()
for t in threads:
    t.join()

print(f"Counter: {counter}")  # 可能不是1000000
```

**解决方案**：
- 使用锁保护共享变量
- 使用原子操作
- 使用线程安全的数据结构

## 调试技巧

### 二分法定位

```python
def find_bug():
    # 第一步：检查前半部分
    if check_part1():
        # 问题在前半部分
        if check_part1a():
            # 问题在part1a
            pass
        else:
            # 问题在part1b
            pass
    else:
        # 问题在后半部分
        pass
```

### 单元测试辅助

```python
def test_edge_case():
    # 测试边界条件
    result = function_under_test(edge_input)
    assert result == expected_output
    
def test_error_case():
    # 测试错误情况
    with pytest.raises(ValueError):
        function_under_test(invalid_input)
```

### 代码审查

**审查要点**：
- 变量命名是否清晰
- 逻辑是否正确
- 错误处理是否完善
- 边界条件是否考虑

## 调试工具

### IDE调试器

**PyCharm**：
- 可视化断点
- 变量监视
- 条件断点
- 远程调试

**VS Code**：
- 内置调试器
- 断点管理
- 调用栈查看
- 交互式调试

### 命令行工具

```bash
# Python调试器
python -m pdb myscript.py

# 堆栈跟踪
python -c "import traceback; traceback.print_exc()"

# 内存使用
free -h

# CPU使用
top -p $(pgrep -d',' -f python)
```

## 常见错误

### 语法错误

**现象**：
```
SyntaxError: invalid syntax
```

**解决**：
- 检查括号、引号是否匹配
- 检查缩进是否正确
- 检查Python版本兼容性

### 运行时错误

**现象**：
```
RuntimeError: maximum recursion depth exceeded
```

**解决**：
- 检查递归终止条件
- 增加递归深度限制
- 改用迭代实现

### 逻辑错误

**现象**：输出结果不符合预期

**解决**：
- 添加日志记录中间结果
- 使用调试器逐步执行
- 编写单元测试验证逻辑

## 预防措施

### 代码质量

- 编写清晰的代码
- 添加充分的注释
- 遵循编码规范

### 测试覆盖

- 编写单元测试
- 测试边界条件
- 使用测试驱动开发

### 日志记录

- 添加关键日志
- 使用结构化日志
- 定期检查日志

## 总结

调试是软件开发的重要技能，需要掌握多种技术和工具。通过系统化的方法和持续的实践，可以高效地定位和解决问题。