"""Extended seed data for system_admin domain."""

from __future__ import annotations

from typing import Any, Dict, List

SYSTEM_ADMIN_EXTENDED_MATERIALS: List[Dict[str, Any]] = [
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
    },]
