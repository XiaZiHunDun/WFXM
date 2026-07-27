"""Seed data for system_admin domain."""

from __future__ import annotations

from typing import Any, Dict, List

SYSTEM_ADMIN_MATERIALS: List[Dict[str, Any]] = [
{
        "source_type": "text",
        "domain_hint": "system_admin",
        "title": "Linux系统监控",
        "content": """Linux系统监控工具：

1. CPU监控：
   - top/htop：实时进程监控
   - mpstat：CPU统计
   - vmstat：虚拟内存统计

2. 内存监控：
   - free：内存使用情况
   - vmstat：内存统计
   - smem：内存使用详情

3. 磁盘监控：
   - df：磁盘使用情况
   - du：目录大小
   - iostat：磁盘I/O统计

4. 网络监控：
   - iftop：网络流量
   - netstat/ss：网络连接
   - tcpdump：网络抓包

5. 进程监控：
   - ps：进程列表
   - pgrep：进程搜索
   - pkill：进程终止""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "system_admin",
        "title": "Shell脚本进阶",
        "content": """Shell脚本进阶技巧：

1. 参数处理：
   - $1-$9：位置参数
   - $@：所有参数
   - $#：参数数量
   - getopts：选项解析

2. 条件判断：
   - [ condition ]：测试条件
   - [[ condition ]]：扩展测试
   - -f/-d/-e：文件测试
   - -eq/-ne/-lt/-gt：数值比较

3. 循环结构：
   - for loop：遍历列表
   - while loop：条件循环
   - until loop：直到条件满足

4. 函数定义：
   - function_name() {}
   - return语句
   - 函数参数

5. 错误处理：
   - set -e：出错退出
   - trap：捕获信号
   - $?：退出码""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "system_admin",
        "title": "日志管理",
        "content": """Linux日志管理：

1. 系统日志：
   - /var/log/syslog：系统日志
   - /var/log/auth.log：认证日志
   - /var/log/kern.log：内核日志

2. 日志查看：
   - cat：查看日志
   - tail：实时查看
   - grep：搜索日志
   - awk：处理日志

3. 日志轮转：
   - logrotate：自动轮转
   - 配置轮转策略
   - 压缩旧日志

4. 日志分析：
   - ELK Stack：日志收集分析
   - Promtail+Loki：轻量级日志
   - 自定义脚本分析""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "system_admin",
        "title": "用户权限管理",
        "content": """Linux用户权限管理：

1. 用户管理：
   - useradd：添加用户
   - usermod：修改用户
   - userdel：删除用户
   - passwd：设置密码

2. 组管理：
   - groupadd：添加组
   - groupmod：修改组
   - groupdel：删除组
   - gpasswd：组管理

3. 文件权限：
   - chmod：修改权限
   - chown：修改所有者
   - chgrp：修改组
   - umask：默认权限

4. 特殊权限：
   - SUID：执行时使用所有者权限
   - SGID：执行时使用组权限
   - sticky bit：目录权限""",
        "priority": 2,
    },]
