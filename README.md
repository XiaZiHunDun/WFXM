# 管家系统 (Butler System)

多项目 AI 协助系统 —— 通过 CLI 或微信指挥 AI 管家管理和推进多个项目。

**当前版本：Butler v4** — 自建 Agent Loop + 模块化 Hermes 提炼，不再 `import` Hermes `AIAgent`。  
架构见 [`docs/architecture/v4-architecture.md`](docs/architecture/v4-architecture.md)；文档索引 [`docs/README.md`](docs/README.md)；目录说明 [`STRUCTURE.md`](STRUCTURE.md)。

## 架构（v4 概要）

```
用户 ─→ CLI / 微信 / Gateway 平台
         │
         ▼
   Butler Orchestrator          ← 记忆、Skill、分层模型
         │
         ▼
   Agent Loop (agent_loop.py)   ← 编排 ~300 行
         ├─ context_pipeline     ← 压缩 / hygiene
         ├─ llm_retry            ← 重试 / failover
         ├─ tool_batch           ← 工具批次 / guardrails
         └─ Transport + Tools    ← LLM 协议与工具注册表
```

## 快速开始

### 1. 安装

```bash
cd /home/ailearn/projects/WFXM
pip install -e ".[wechat]"          # Butler + 微信 iLink 依赖（推荐）
```

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env，至少配置一个 LLM Provider 的 API Key
```

### 3. 启动

```bash
# 交互式 CLI
butler chat

# 单条指令
butler exec "列出所有项目"

# 项目列表 / 创建
butler projects
butler create MyApp --type software --description "我的新应用"

# 微信（个人助手主场景）
butler wechat-setup                              # 扫码绑定
bash scripts/install-butler-gateway-service.sh   # systemd 常驻网关
bash scripts/butler-gateway-ops.sh status        # 运维状态
```

### 4. 测试

```bash
PYTHONPATH=. pytest -q          # ~1121 passed（默认排除 live_llm 与 tests/archive/）

# 微信改动的快守门（见 tests/README.md）
PYTHONPATH=. pytest tests/test_gateway_acceptance.py tests/test_wechat_ilink_*.py -q
```

## 项目结构（核心）

```
butler/
├── core/              # Agent Loop 栈（agent_loop, tool_batch, llm_retry, context_pipeline, …）
├── transport/         # LLM 协议、Provider、重试与 schema 兼容
├── gateway/           # 消息网关、session 注册、/health
├── tools/             # 工具注册表、审计、路径安全
├── memory/            # 分层记忆
├── skills/            # Skill 加载 / 路由 / 合并
├── task_orchestrator.py
├── orchestrator.py
├── post_session.py
└── main.py
docs/                  # 架构与设计文档（索引 docs/README.md）
tests/                 # ~1121 自动化测试（archive 遗留另计）
scripts/               # 网关安装与 butler-gateway-ops 运维
```

## 支持的 LLM Provider

| Provider | 用途 | 环境变量 |
|----------|------|----------|
| Claude | 代码开发、复杂推理 | `ANTHROPIC_API_KEY` |
| OpenAI | 通用任务 | `OPENAI_API_KEY` |
| DeepSeek | 代码、中文 | `DEEPSEEK_API_KEY` |
| 通义千问 | 中文内容 | `DASHSCOPE_API_KEY` |
| 智谱 GLM | 中文内容 | `ZHIPUAI_API_KEY` |
| Moonshot | 中文长文本 | `MOONSHOT_API_KEY` |
| MiniMax | 中文、推理 | `MINIMAX_API_KEY` |

详见 [`butler/transport/providers.py`](butler/transport/providers.py) 与 [`.env.example`](.env.example)。

## CLI 命令（节选）

| 命令 | 说明 |
|------|------|
| `/projects` | 列出所有项目 |
| `/switch <名称>` | 切换项目 |
| `/model` | 查看 / 设置分层模型 |
| `/health`、`/诊断` | 运行时诊断与工具审计摘要 |
| `/steer <文本>` | 向运行中 Agent 插入指引（不打断工具）|
| `/new` | 新会话（自动提炼旧会话记忆）|
| `/status` | 系统状态 |
| `/help` | 帮助 |

完整列表见 [`docs/design/design.md`](docs/design/design.md) 附录。

## 使用场景

- **CLI 对话开发**：终端与管家对话，委派 Dev / Content / Review 等角色 Agent。
- **微信远程开发**：`butler gateway --platforms wechat`（Butler 原生 iLink 网关，需 `aiohttp` + `cryptography`）。生产部署见 [`docs/guides/wechat-gateway-ops.md`](docs/guides/wechat-gateway-ops.md)。

## 扩展

- **Provider**：在 `butler/transport/` 扩展协议与注册。
- **工具**：`butler/tools/` + `@register_tool`。
- **网关**：`butler/gateway/` 适配新平台。

## 文档

| 文档 | 内容 |
|------|------|
| [STRUCTURE.md](STRUCTURE.md) | 仓库目录与职责边界 |
| [docs/README.md](docs/README.md) | 文档总索引 |
| [docs/guides/README.md](docs/guides/README.md) | 微信运维与冒烟指南索引 |
| [docs/architecture/v4-architecture.md](docs/architecture/v4-architecture.md) | v4 架构、数据流、观测 |
| [docs/architecture/hermes-decoupling.md](docs/architecture/hermes-decoupling.md) | Hermes 解耦（已完成） |
| [docs/guides/wechat-gateway-ops.md](docs/guides/wechat-gateway-ops.md) | 微信网关 systemd 运维 |
| [docs/guides/wechat-daily-smoke-checklist.md](docs/guides/wechat-daily-smoke-checklist.md) | 发版真机冒烟检查表 |
| [docs/design/design.md](docs/design/design.md) | 产品设计全文 |
