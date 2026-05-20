# 仓库目录结构

> Butler v4 monorepo：`butler/` 为产品代码；Hermes  vendored 在 `vendor/hermes-agent/`（仅 `--hermes-fallback`）。  
> **`reference/` 为只读对照，请勿移动或修改。**

```
WFXM/
├── butler/                 # ★ Butler v4 产品（自建 Agent Loop）
│   ├── core/               #   agent_loop、tool_batch、llm_retry、context_pipeline …
│   ├── transport/          #   LLM 协议、Provider、schema 兼容
│   ├── gateway/            #   消息处理、原生 runner、platforms/wechat
│   ├── tools/              #   工具注册表、审计、路径安全
│   ├── memory/             #   分层记忆
│   ├── skills/             #   Butler Skill 加载 / 路由
│   ├── cli/                #   Rich CLI 展示
│   └── main.py             #   `butler` 入口
│
├── vendor/hermes-agent/    # ⚠️ Hermes vendored（子进程 fallback；Butler 不 import）
│   ├── agent/ gateway/ hermes_cli/ tools/ plugins/ providers/ …
│   └── run_agent.py        # `hermes-agent` 脚本入口
│
├── docs/                   # ★ Butler 文档（见 docs/README.md）
├── tests/                  # ★ Butler 自动化测试（~885，pytest；archive 另计）
├── projects/               #   用户项目工作区（示例：LingWen）
├── archive/                #   历史代码（butler-v1），非主线
├── reference/              #   Hermes 上游只读对照（不改动）
│
├── pyproject.toml          # 打包：butler + vendor/hermes-agent（package-dir）
└── .env.example            # 环境变量模板
```

## 职责边界

| 区域 | 维护方 | 说明 |
|------|--------|------|
| `butler/` | Butler 主线 | 新功能、硬化、观测；**零** `agent`/`run_agent` import |
| `vendor/hermes-agent/` | 冻结 vendored | 仅 `butler gateway --hermes-fallback`；不往此新增业务 |
| `reference/` | 只读 | 提炼对照，不直接 import |
| `archive/` | 冻结 | 仅回溯 v1 |

## 常用命令

```bash
pip install -e .                     # 仅 butler-system
pip install -e ".[dev]"              # 开发 + hermes-vendored（pytest 需要）
pip install -e ".[hermes-gateway]"   # Telegram / Slack 等 Hermes 子进程
PYTHONPATH=. pytest -q
butler chat
butler gateway                       # 默认微信 Butler 原生
butler gateway --platforms telegram  # 自动 Hermes 子进程（需 hermes-gateway）
butler gateway --hermes-fallback     # 强制 Hermes（含微信也可）
```

文档入口：[`docs/README.md`](docs/README.md) · 架构：[`docs/architecture/v4-architecture.md`](docs/architecture/v4-architecture.md)
