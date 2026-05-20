# 仓库目录结构

> Butler v4  monorepo：`butler/` 为产品代码；根目录 Hermes 运行时用于 Gateway 子进程与 `hermes` CLI。  
> **`reference/` 为只读对照，请勿移动或修改。**

```
WFXM/
├── butler/                 # ★ Butler v4 产品（自建 Agent Loop）
│   ├── core/               #   agent_loop、tool_batch、llm_retry、context_pipeline …
│   ├── transport/          #   LLM 协议、Provider、schema 兼容
│   ├── gateway/            #   消息处理、原生 runner、platforms/wechat
│   ├── tools/              #   工具注册表、审计、路径安全
│   ├── memory/             #   分层记忆
│   ├── skills/             #   Skill 加载 / 路由 / 合并
│   ├── cli/                #   Rich CLI 展示
│   └── main.py             #   `butler` 入口
│
├── docs/                   # ★ Butler 文档（见 docs/README.md）
├── tests/                  # ★ Butler 自动化测试（925+，pytest）
├── projects/               #   用户项目工作区（示例：LingWen）
├── archive/                #   历史代码（butler-v1），非主线
├── reference/              #   Hermes 上游只读对照（不改动）
│
├── agent/                  # ⚠️ Hermes vendored（Butler 主路径不 import；Gateway 子进程用）
├── gateway/                # ⚠️ Hermes Gateway（仅 `--hermes-fallback` 使用）
├── tools/                  # Hermes 工具生态
├── hermes_cli/             # `hermes` CLI
├── providers/              # Hermes Provider 配置
├── plugins/                # Hermes / Butler 插件
├── skills/                 # Hermes Skill 目录
├── optional-skills/        # 可选 Skill 包
├── environments/           # RL / 基准环境
│
├── run_agent.py            # Hermes AIAgent 入口（hermes-agent 脚本）
├── pyproject.toml          # 打包：butler + Hermes 模块
└── .env.example            # 环境变量模板
```

## 职责边界

| 区域 | 维护方 | 说明 |
|------|--------|------|
| `butler/` | Butler 主线 | 新功能、硬化、观测默认改这里 |
| `reference/` | 只读 | 提炼时对照，不直接 import |
| `agent/`、`gateway/`、`run_agent.py` 等 | Hermes vendored（**过渡态**） | 目标移入 `vendor/` 或删除；见 `docs/architecture/hermes-decoupling.md` |
| `butler/` | Butler 主线 | **运行时零** `agent`/`run_agent` import（已达成） |
| `archive/` | 冻结 | 仅回溯 v1，不接入 CI |

## 常用命令

```bash
pip install -e .
PYTHONPATH=. pytest -q                    # Butler 测试
butler chat                               # Butler CLI
# hermes / gateway 见 Hermes 文档与 skills/
```

文档入口：[`docs/README.md`](docs/README.md) · 架构：[`docs/architecture/v4-architecture.md`](docs/architecture/v4-architecture.md)
