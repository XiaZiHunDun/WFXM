"""Extended seed data for troubleshooting domain."""

from __future__ import annotations

from typing import Any, Dict, List

TROUBLESHOOTING_EXTENDED_MATERIALS: List[Dict[str, Any]] = [
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
    },]
