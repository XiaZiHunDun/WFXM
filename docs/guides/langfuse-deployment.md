# LangFuse 自托管部署指南

> Butler v4 可观测层。opt-in，非必需组件。

## 前置条件

- Docker Engine 24+ 与 Docker Compose v2
- 4GB+ 可用内存（Postgres + ClickHouse + Redis + LangFuse）
- 端口 3000 未被占用

## 一键部署

```bash
./scripts/langfuse-setup.sh
```

脚本自动执行：
1. 生成加密密钥（`deploy/langfuse/.env`）
2. 拉起 5 个容器（web / worker / postgres / clickhouse / redis）
3. 初始化 Butler 组织 + 项目 + 默认 API key
4. 等待健康检查通过

## 手动部署

```bash
cd deploy/langfuse
# 编辑 .env（或让脚本自动生成）
docker compose up -d
```

## 连接 Butler

在 Butler 运行环境中设置：

```bash
# .env 或环境变量
BUTLER_LANGFUSE_ENABLED=1
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-butler-dev
LANGFUSE_SECRET_KEY=sk-butler-dev
```

需要安装可选依赖：

```bash
pip install butler-system[observability]
# 或
pip install langfuse>=2.0
```

## 验证

```bash
# 检查 LangFuse 健康
curl http://localhost:3000/api/public/health

# Butler 侧验证
PYTHONPATH=. python -c "
from butler.ops.langfuse_tracer import langfuse_enabled
print('LangFuse enabled:', langfuse_enabled())
"
```

## 访问 UI

- 地址：`http://localhost:3000`
- 账户：`admin@butler.local`
- 密码：见 `deploy/langfuse/.env` 中 `LANGFUSE_ADMIN_PASSWORD`

## 追踪内容

启用后，Butler 自动追踪：

| Span 类型 | 数据 |
|-----------|------|
| `butler-turn` | 每轮对话 trace（session 维度） |
| LLM generation | 模型调用 token/耗时/provider |
| Tool span | 工具执行 name/duration |
| Memory prefetch | 记忆检索 hit 数/耗时 |
| Memory write | 记忆写入类型/成功率 |
| Gateway inbound | 微信入站消息 platform/长度 |
| Gateway outbound | 出站回复长度/延迟 |

## 停止 / 清理

```bash
# 停止（保留数据）
./scripts/langfuse-setup.sh --down

# 彻底清理（含数据卷）
cd deploy/langfuse && docker compose down -v
```

## 生产部署注意

- 替换 `deploy/langfuse/.env` 中所有密钥
- 修改 `LANGFUSE_ADMIN_PASSWORD` 为强密码
- 考虑在 `docker-compose.yml` 中挂载持久化卷到指定路径
- 高可用场景建议使用 Kubernetes，参见 [LangFuse 官方 Helm Chart](https://langfuse.com/self-hosting/deployment/kubernetes)
