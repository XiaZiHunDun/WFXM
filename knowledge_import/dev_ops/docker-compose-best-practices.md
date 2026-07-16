# Docker Compose最佳实践

## 基础配置

### 版本选择

```yaml
# 使用最新版本
version: '3.8'
```

**建议**：
- 使用3.8或更高版本
- 避免使用过时的版本（如2.x）
- 参考官方文档确认兼容性

### 服务命名

```yaml
services:
  web:
    build: .
    ports:
      - "80:80"
  
  api:
    build: ./api
    ports:
      - "8080:8080"
  
  db:
    image: postgres:15
```

**规范**：
- 使用有意义的服务名称
- 避免使用特殊字符
- 保持命名风格一致

## 网络配置

### 自定义网络

```yaml
services:
  web:
    networks:
      - frontend
      - backend
  
  api:
    networks:
      - backend
  
  db:
    networks:
      - backend

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
```

**优点**：
- 隔离不同服务
- 提高安全性
- 便于管理

### 网络别名

```yaml
services:
  db:
    image: postgres:15
    networks:
      backend:
        aliases:
          - database
          - postgres
```

**用途**：
- 提供多个DNS名称
- 便于服务发现
- 支持服务迁移

## 数据持久化

### Volume挂载

```yaml
services:
  db:
    image: postgres:15
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

**优势**：
- 数据持久化
- 容器销毁后数据保留
- 便于备份和迁移

### Bind挂载

```yaml
services:
  web:
    build: .
    volumes:
      - .:/app
      - /app/node_modules
```

**用途**：
- 开发环境热重载
- 挂载配置文件
- 共享日志目录

## 环境变量

### .env文件

```yaml
services:
  web:
    build: .
    env_file:
      - .env
```

**.env文件内容**：
```
DATABASE_URL=postgres://user:pass@db:5432/mydb
REDIS_URL=redis://redis:6379
DEBUG=false
```

**安全注意**：
- 将.env文件添加到.gitignore
- 不要提交敏感信息
- 使用环境变量传递配置

### 直接定义

```yaml
services:
  web:
    build: .
    environment:
      - DATABASE_URL=postgres://user:pass@db:5432/mydb
      - DEBUG=false
```

**适用场景**：
- 非敏感配置
- 需要覆盖.env中的值
- 临时调试

## 健康检查

### 基础健康检查

```yaml
services:
  web:
    build: .
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:80/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

**参数说明**：
- `test`：检查命令
- `interval`：检查间隔
- `timeout`：超时时间
- `retries`：重试次数
- `start_period`：启动等待时间

### TCP健康检查

```yaml
services:
  db:
    image: postgres:15
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
```

### 依赖等待

```yaml
services:
  web:
    build: .
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
  
  db:
    image: postgres:15
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
  
  redis:
    image: redis:7
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
```

## 资源限制

### CPU和内存限制

```yaml
services:
  web:
    build: .
    deploy:
      resources:
        limits:
          cpus: '0.50'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 256M
```

**建议**：
- 设置合理的资源限制
- 根据服务需求调整
- 避免资源竞争

### 端口暴露

```yaml
services:
  web:
    build: .
    ports:
      - "80:80"  # 主机端口:容器端口
      - "443:443"
```

**安全注意**：
- 只暴露必要的端口
- 使用防火墙限制访问
- 考虑使用反向代理

## 多阶段构建

### Dockerfile示例

```dockerfile
# 构建阶段
FROM python:3.11-slim as builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 运行阶段
FROM python:3.11-slim

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY . .

CMD ["python", "app.py"]
```

**优点**：
- 减小镜像大小
- 提高安全性
- 加速部署

## 日志管理

### 日志驱动

```yaml
services:
  web:
    build: .
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

**常用驱动**：
- `json-file`：JSON格式日志
- `syslog`：系统日志
- `gelf`：Graylog格式
- `fluentd`：Fluentd格式

### 日志输出

```yaml
services:
  web:
    build: .
    command: ["python", "-u", "app.py"]
```

**注意**：
- 使用非缓冲输出（-u参数）
- 确保日志及时刷新
- 统一日志格式

## 开发环境配置

### 覆盖生产配置

```yaml
# docker-compose.override.yml
services:
  web:
    volumes:
      - .:/app
    environment:
      - DEBUG=true
    ports:
      - "80:80"
      - "5678:5678"  # 调试端口
```

**用途**：
- 开发环境热重载
- 启用调试模式
- 暴露额外端口

### 命令覆盖

```yaml
services:
  web:
    build: .
    command: ["python", "-m", "debugpy", "--listen", "0.0.0.0:5678", "app.py"]
```

## 安全配置

### 用户权限

```dockerfile
FROM python:3.11-slim

RUN useradd -m appuser
USER appuser

WORKDIR /app
COPY . .

CMD ["python", "app.py"]
```

**原则**：
- 不要以root用户运行
- 创建专用用户
- 限制文件权限

### 网络安全

```yaml
services:
  db:
    image: postgres:15
    networks:
      - backend
    ports: []  # 不暴露端口
```

**策略**：
- 内部服务不暴露端口
- 使用网络隔离
- 限制外部访问

## 备份策略

### Volume备份

```bash
#!/bin/bash
docker compose exec db pg_dump -U postgres mydb > backup.sql
```

### 自动化备份

```yaml
services:
  backup:
    image: postgres:15
    command: >
      bash -c "pg_dump -h db -U postgres mydb > /backup/backup_$(date +%Y%m%d_%H%M%S).sql"
    volumes:
      - backup_volume:/backup
    depends_on:
      db:
        condition: service_healthy
```

## 监控配置

### 容器监控

```yaml
services:
  web:
    build: .
    labels:
      - "com.example.service=web"
      - "com.example.environment=production"
```

**用途**：
- 服务发现
- 监控集成
- 自动配置

### 健康指标

```yaml
services:
  web:
    build: .
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:80/health"]
      interval: 30s
```

**监控指标**：
- 服务状态
- 响应时间
- 错误率

## 总结

Docker Compose是开发和部署的强大工具。通过合理的配置，可以提高开发效率、增强安全性、简化部署流程。