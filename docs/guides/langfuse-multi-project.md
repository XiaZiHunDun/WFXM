# LangFuse 多项目共享基础设施指南

> Butler v4 的 LangFuse 实例可以同时服务多个项目，每个项目拥有独立的 API Key 和 Trace 隔离。

## 架构概览

```
LangFuse (共享基础设施, localhost:3000)
├── butler-v4       (管家自身，默认项目)
├── lingwen-1       (灵文1号项目)
├── project-a       (其他 agent 项目)
└── project-b       (其他 agent 项目)
```

## 使用方式

### 1. 创建新项目

```bash
# 自动生成配置文件
bash scripts/langfuse-setup.sh --create-project "灵文1号"
```

这会在 `~/.butler/projects/<project-id>/langfuse.json` 创建配置：

```json
{
  "project_name": "灵文1号",
  "project_id": "lingwen-1",
  "langfuse_host": "http://localhost:3000",
  "langfuse_public_key": "pk-lingwen-1",
  "langfuse_secret_key": "sk-lingwen-1-xxxx"
}
```

### 2. 在 LangFuse UI 创建对应项目

1. 打开 http://localhost:3000
2. 进入 Settings → Organization → Projects
3. 创建新项目，名称与配置文件中的 `project_name` 一致
4. 在 API Keys 页面创建密钥，使用与配置文件相同的 public/secret key

### 3. Tracer 自动切换

`langfuse_tracer.py` 支持根据当前项目 ID 自动选择对应的 LangFuse client：

```python
from butler.ops.langfuse_tracer import start_trace

# 默认使用 butler-v4 项目
ctx = start_trace(session_key="cli")

# 指定项目
ctx = start_trace(
    session_key="lingwen:task-1",
    project_name="灵文1号",
    tenant="lingwen-1",
)
```

### 4. Metadata 标签

每个 Trace 自动携带以下 metadata：

| 字段 | 来源 | 用途 |
|------|------|------|
| `project_name` | 配置/参数 | 区分项目来源 |
| `tenant` | 配置/参数 | 多租户筛选 |
| `session_source` | 自动检测 | wechat/gateway/cli/direct |

Tags 自动添加 `project:<name>` 和 `tenant:<id>`，便于 LangFuse Dashboard 筛选。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BUTLER_LANGFUSE_ENABLED` | `0` | 全局开关 |
| `LANGFUSE_HOST` | `http://localhost:3000` | LangFuse 服务地址 |
| `LANGFUSE_PUBLIC_KEY` | - | 默认项目 Public Key |
| `LANGFUSE_SECRET_KEY` | - | 默认项目 Secret Key |
| `BUTLER_PROJECT_NAME` | `butler-v4` | 默认项目名 |
| `BUTLER_TENANT` | - | 默认租户 ID |

## 评估反馈闭环

评估数据通过 `eval_bridge.py` 写入 LangFuse，再通过 `eval_feedback.py` 回读：

```
[Agent Loop] → eval_scoring → eval_bridge → [LangFuse]
                                                ↓
[Agent Loop] ← eval_feedback ← ─────────────────┘
```

每次 Turn 开始时，`agent_loop_phases._phase_init` 自动注入最近 24h 的评估反馈摘要到上下文中。

## CI 自动推送

`ci.yml` 中的 `eval-push` job 在 main 分支 push 后自动执行：
1. 运行 DevEngine 基准测试 (B1-B8)
2. 运行 Memory 基准测试 (MB1-MB7)
3. 将分数推送到 LangFuse

需要在 GitHub Secrets 中配置 `LANGFUSE_HOST`、`LANGFUSE_PUBLIC_KEY`、`LANGFUSE_SECRET_KEY`。
