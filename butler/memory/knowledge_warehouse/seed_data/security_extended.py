"""Extended seed data for security domain."""

from __future__ import annotations

from typing import Any, Dict, List

SECURITY_EXTENDED_MATERIALS: List[Dict[str, Any]] = [
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
    },]
