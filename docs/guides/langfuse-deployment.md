# LangFuse 连接指南（Butler 侧）

> **栈运维 SSOT**：`~/gongju/langfuse/README.md`（compose、起停、升级）。  
> Butler 仓库不再包含 LangFuse Docker 部署文件。

## 启动 LangFuse

```bash
cd ~/gongju/langfuse
./ops.sh up
./ops.sh health
```

## 连接 Butler

在 `WFXM/.env`：

```bash
BUTLER_LANGFUSE_ENABLED=1
LANGFUSE_HOST=http://localhost:3000
LANGFUSE_PUBLIC_KEY=pk-butler-dev
LANGFUSE_SECRET_KEY=sk-butler-dev
```

可选依赖：

```bash
pip install butler-system[observability]
```

一键写入 Butler `.env`（不改 Docker）：

```bash
bash scripts/butler-observability-provision.sh
```

## 验证

```bash
curl http://localhost:3000/api/public/health

cd ~/projects/WFXM
BUTLER_LANGFUSE_ENABLED=1 PYTHONPATH=. python3 -c "
from butler.ops.langfuse_tracer import langfuse_enabled, _get_client
print('enabled:', langfuse_enabled(), 'client:', _get_client() is not None)
"
```

## 多项目

```bash
bash scripts/butler-langfuse-project.sh "灵文1号"
```

详见 [`langfuse-multi-project.md`](langfuse-multi-project.md)。

## 追踪内容

| Span | 数据 |
|------|------|
| `butler-turn` | 每轮对话 trace |
| LLM generation | token / 耗时 |
| `tool:*` | 工具执行 |
| `memory:prefetch` | 预取命中 |
| Gateway inbound/outbound | 微信入出站 |

评测推送：`eval_bridge`、`eval_turn` → LangFuse Scores。见 [`evaluation-guide.md`](evaluation-guide.md)。
