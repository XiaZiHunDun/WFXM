"""Seed data for troubleshooting domain."""

from __future__ import annotations

from typing import Any, Dict, List

TROUBLESHOOTING_MATERIALS: List[Dict[str, Any]] = [
{
        "source_type": "text",
        "domain_hint": "troubleshooting",
        "title": "问题排查方法论",
        "content": """问题排查方法论：

1. 定义问题：
   - 明确问题现象
   - 记录发生时间
   - 收集环境信息

2. 收集证据：
   - 查看日志
   - 收集堆栈
   - 记录配置

3. 分析原因：
   - 重现问题
   - 对比差异
   - 假设验证

4. 定位根因：
   - 逐步排查
   - 使用二分法
   - 缩小范围

5. 验证修复：
   - 应用修复
   - 验证效果
   - 回归测试

6. 预防措施：
   - 添加监控
   - 添加测试
   - 更新文档""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "troubleshooting",
        "title": "性能问题排查",
        "content": """性能问题排查：

1. CPU问题：
   - 使用top/htop查看
   - 定位CPU密集进程
   - 使用perf分析热点

2. 内存问题：
   - 使用free查看
   - 检查内存泄漏
   - 使用memory_profiler

3. 磁盘问题：
   - 使用iostat查看
   - 检查磁盘IO
   - 检查磁盘空间

4. 网络问题：
   - 使用iftop/netstat查看
   - 检查网络延迟
   - 检查网络带宽

5. 数据库问题：
   - 检查慢查询日志
   - 分析查询计划
   - 检查连接池""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "troubleshooting",
        "title": "日志分析技巧",
        "content": """日志分析技巧：

1. 日志收集：
   - 集中收集日志
   - 标准化日志格式
   - 添加时间戳和上下文

2. 日志搜索：
   - 使用grep搜索
   - 使用awk处理
   - 使用ELK分析

3. 错误模式识别：
   - 搜索ERROR/WARNING
   - 识别重复错误
   - 分析错误频率

4. 日志关联：
   - 使用request_id关联
   - 追踪请求链路
   - 分析时序关系

5. 日志可视化：
   - 错误趋势图
   - 分布直方图
   - 热力图""",
        "priority": 2,
    },]
