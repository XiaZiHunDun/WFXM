# API安全指南

## 认证与授权

### JWT认证

**流程**：
1. 用户登录获取Token
2. 每次请求携带Token
3. 服务端验证Token

**实现示例**：

```python
import jwt
from datetime import datetime, timedelta

SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"

def create_token(user_id):
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(hours=24),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
```

**安全注意**：
- 使用强密钥
- 设置合理的过期时间
- 使用HTTPS传输

### OAuth2.0

**流程**：
1. 用户授权获取授权码
2. 使用授权码获取Token
3. 使用Token访问资源

**常见授权类型**：
- Authorization Code：适用于Web应用
- Client Credentials：适用于服务间调用
- Refresh Token：用于刷新Token

### API Key认证

```python
def validate_api_key(api_key):
    valid_keys = ["valid-key-1", "valid-key-2"]
    return api_key in valid_keys
```

**适用场景**：
- 内部服务调用
- 简单的API访问控制
- 第三方集成

## 输入验证

### 参数校验

```python
from pydantic import BaseModel, EmailStr, Field

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    age: int = Field(ge=18, le=120)
```

**验证规则**：
- 类型验证
- 格式验证
- 长度验证
- 范围验证

### SQL注入防护

```python
# 正确：使用参数化查询
query = "SELECT * FROM users WHERE email = %s"
cursor.execute(query, (email,))

# 错误：字符串拼接
query = f"SELECT * FROM users WHERE email = '{email}'"
cursor.execute(query)
```

**防护措施**：
- 使用参数化查询
- 使用ORM框架
- 输入转义

### XSS防护

```python
import html

def sanitize_input(input_str):
    return html.escape(input_str)
```

**防护措施**：
- 对输出进行HTML转义
- 设置CSP头
- 使用模板引擎自动转义

## 请求限制

### 速率限制

```python
from fastapi import FastAPI, Request, HTTPException
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter

app = FastAPI()

@app.on_event("startup")
async def startup():
    await FastAPILimiter.init()

@app.get("/api/data", dependencies=[Depends(RateLimiter(times=10, seconds=60))])
async def get_data():
    return {"data": "value"}
```

**策略**：
- 按IP限制
- 按用户限制
- 按API端点限制

### 请求大小限制

```python
from fastapi import FastAPI, File, UploadFile

app = FastAPI()

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    if file.size > 10 * 1024 * 1024:  # 10MB
        raise HTTPException(status_code=413, detail="File too large")
    return {"filename": file.filename}
```

**限制内容**：
- 请求体大小
- 文件上传大小
- 参数数量

## 安全头

### CORS配置

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://example.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**安全建议**：
- 限制允许的源
- 明确允许的方法和头
- 不要使用通配符

### 安全响应头

```python
from fastapi import FastAPI, Response

app = FastAPI()

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response
```

**常用安全头**：
- `X-Content-Type-Options`：防止MIME类型嗅探
- `X-Frame-Options`：防止点击劫持
- `X-XSS-Protection`：启用XSS保护
- `Strict-Transport-Security`：强制HTTPS

## 数据加密

### 传输加密

**配置HTTPS**：
```nginx
server {
    listen 443 ssl;
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
}
```

**建议**：
- 使用TLS 1.2或更高版本
- 配置HSTS头
- 使用强加密算法

### 存储加密

```python
from cryptography.fernet import Fernet

key = Fernet.generate_key()
cipher = Fernet(key)

def encrypt_data(data):
    return cipher.encrypt(data.encode())

def decrypt_data(encrypted_data):
    return cipher.decrypt(encrypted_data).decode()
```

**加密策略**：
- 敏感数据加密存储
- 使用AES-256加密
- 密钥安全管理

## 日志与监控

### 安全日志

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

def log_security_event(event_type, details):
    logger.info(f"Security event: {event_type} - {details}")
```

**日志内容**：
- 认证失败
- 访问拒绝
- 异常请求
- 敏感操作

### 异常监控

```python
from sentry_sdk import capture_exception

try:
    # 业务逻辑
    pass
except Exception as e:
    capture_exception(e)
    raise
```

**监控指标**：
- 错误率
- 响应时间
- 异常类型
- 攻击模式

## 安全审计

### 定期扫描

```bash
# 使用OWASP ZAP扫描
zap-cli quick-scan --target https://api.example.com

# 使用Nessus扫描
nessuscli scan --target 192.168.1.100
```

**扫描类型**：
- 漏洞扫描
- 配置审计
- 依赖检查

### 渗透测试

**步骤**：
1. 信息收集
2. 漏洞识别
3. 漏洞利用
4. 报告编写

**测试范围**：
- 认证绕过
- 权限提升
- 数据泄露
- API滥用

## API安全清单

### 认证
- [ ] 使用强密码策略
- [ ] 实现多因素认证
- [ ] 使用HTTPS传输Token
- [ ] 设置Token过期时间

### 授权
- [ ] 实现角色权限控制
- [ ] 验证资源所有权
- [ ] 最小权限原则
- [ ] 权限审计日志

### 输入验证
- [ ] 参数类型验证
- [ ] SQL注入防护
- [ ] XSS防护
- [ ] 文件上传验证

### 数据保护
- [ ] 敏感数据加密存储
- [ ] API响应脱敏
- [ ] 数据访问日志
- [ ] 定期数据备份

### 基础设施
- [ ] 配置防火墙规则
- [ ] 启用HTTPS
- [ ] 设置安全响应头
- [ ] 定期安全更新

## 总结

API安全是系统安全的重要组成部分。通过实施认证授权、输入验证、请求限制、数据加密等措施，可以显著提高API的安全性。