"""Seed data for security domain."""

from __future__ import annotations

from typing import Any, Dict, List

SECURITY_MATERIALS: List[Dict[str, Any]] = [
{
        "source_type": "text",
        "domain_hint": "security",
        "title": "安全开发原则",
        "content": """安全开发原则：

1. 最小权限原则：
   - 只授予必要的权限
   - 定期审查权限
   - 及时撤销权限

2. 纵深防御原则：
   - 多层防护
   - 多重验证
   - 冗余设计

3. 数据加密原则：
   - 传输加密(HTTPS)
   - 存储加密
   - 敏感数据加密

4. 输入验证原则：
   - 所有输入都不可信
   - 使用白名单验证
   - 防止注入攻击

5. 安全审计原则：
   - 记录所有操作
   - 定期安全审计
   - 监控异常行为""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "security",
        "title": "认证授权机制",
        "content": """认证授权机制：

1. 认证方式：
   - 用户名密码
   - 双因素认证
   - OAuth2.0
   - SSO单点登录

2. 授权方式：
   - RBAC：基于角色的访问控制
   - ABAC：基于属性的访问控制
   - PBAC：基于策略的访问控制

3. Token管理：
   - JWT令牌
   - Token过期策略
   - Token刷新机制
   - Token撤销机制

4. 会话管理：
   - Session生命周期
   - Session超时
   - Session固定攻击防护""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "security",
        "title": "常见攻击类型",
        "content": """常见Web攻击类型：

1. SQL注入：
   - 通过输入注入SQL代码
   - 使用参数化查询防护
   - 使用ORM框架

2. XSS攻击：
   - 跨站脚本攻击
   - 对输出进行HTML转义
   - 设置CSP头

3. CSRF攻击：
   - 跨站请求伪造
   - 使用CSRF Token
   - 验证Referer头

4. SSRF攻击：
   - 服务端请求伪造
   - 验证URL白名单
   - 限制内网访问

5. 文件上传漏洞：
   - 上传恶意文件
   - 验证文件类型
   - 存储在非Web目录""",
        "priority": 2,
    },
    {
        "source_type": "text",
        "domain_hint": "security",
        "title": "安全配置",
        "content": """服务器安全配置：

1. 操作系统安全：
   - 更新系统补丁
   - 禁用不必要服务
   - 配置防火墙
   - 限制SSH访问

2. Web服务器安全：
   - 禁用目录浏览
   - 配置安全响应头
   - 限制请求大小
   - 配置访问日志

3. 数据库安全：
   - 使用强密码
   - 限制数据库用户权限
   - 禁止远程访问
   - 定期备份

4. 应用安全：
   - 禁用调试模式
   - 使用HTTPS
   - 配置安全Cookie
   - 实现速率限制""",
        "priority": 2,
    },]
