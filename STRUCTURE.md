# 仓库目录结构

> Butler v4：**仅微信**消息网关（`butler gateway --platforms wechat`）。  
> **`reference/`**：主公维护的外部竞品/标本对照区（gitignore），**整理方案不修改此目录**。

```
WFXM/
├── butler/                      # ★ Butler v4 产品代码
│   ├── core/                    #   Agent Loop 栈
│   ├── transport/               #   LLM Provider / 客户端
│   ├── gateway/                 #   消息处理、session、/health
│   │   └── platforms/           #   wechat_ilink.py（iLink）
│   ├── runtime/ workflows/    #   定时任务、短工作流
│   ├── tools/ memory/ skills/ cli/ ops/
│   ├── project*.py              #   项目注册 / Lead / preflight
│   └── main.py                  #   `butler` CLI 入口
├── scripts/                     #   见 scripts/README.md
├── docs/
│   ├── architecture/            #   v4 架构、ADR、Hermes 解耦（已完成）
│   ├── design/                  #   产品设计
│   ├── guides/                  #   运维、冒烟、接入
│   ├── config/                  #   config.yaml.example、reference.md
│   └── plans/                   #   整理方案等
├── tests/                       #   默认 ~1138 passed（排除 live_llm / archive）
├── projects/                    #   LingWen1、DemoPilot 等工作区
├── logs/                        #   butler-gateway.log（gitignore *.log）
├── archive/                     #   Butler v1 快照（计划迁 tag）
├── reference/                   #   【不动】外部对照，主公维护
└── pyproject.toml               #   包名 butler-system；`[wechat]` extra
```

## 常用命令

```bash
pip install -e ".[wechat]"
cp .env.example .env              # 配置 MINIMAX_API_KEY 等

butler chat                       # CLI
butler project preflight --project 灵文1号
butler wechat-setup               # 微信扫码绑定
bash scripts/install-butler-gateway-service.sh   # systemd 用户服务
bash scripts/butler-gateway-ops.sh status        # 网关运维
bash scripts/butler-pre-release-smoke.sh         # 发版守门

PYTHONPATH=. pytest -q
```

## 文档入口

| 文档 | 说明 |
|------|------|
| [`README.md`](README.md) | 项目总览 |
| [`docs/README.md`](docs/README.md) | 文档索引 |
| [`docs/architecture/v4-architecture.md`](docs/architecture/v4-architecture.md) | v4 架构 |
| [`docs/guides/wechat-gateway-ops.md`](docs/guides/wechat-gateway-ops.md) | 微信网关 systemd 运维 |
| [`docs/guides/wechat-daily-smoke-checklist.md`](docs/guides/wechat-daily-smoke-checklist.md) | 发版真机冒烟 |
| [`tests/README.md`](tests/README.md) | 测试分层与守门命令 |
| [`scripts/README.md`](scripts/README.md) | 脚本索引 |
| [`docs/plans/consolidation-2026-05.md`](docs/plans/consolidation-2026-05.md) | 整理与瘦身方案 |
| [`docs/config/reference.md`](docs/config/reference.md) | 环境变量速查 |
