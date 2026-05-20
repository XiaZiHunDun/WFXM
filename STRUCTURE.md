# 仓库目录结构

> Butler v4：**仅微信**消息网关（`butler gateway --platforms wechat`）。  
> Hermes 对照源码在本地 `reference/hermes-agent/`（gitignore，不进仓库）。**`reference/` 为只读对照，请勿移动或修改。**

```
WFXM/
├── butler/                      # ★ Butler v4 产品代码
│   ├── core/                    #   Agent Loop 栈
│   ├── transport/               #   LLM Provider / 客户端
│   ├── gateway/                 #   消息处理、session、/health
│   │   └── platforms/           #   wechat_ilink.py（iLink）
│   ├── tools/ memory/ skills/ cli/
│   └── main.py                  #   `butler` CLI 入口
├── scripts/
│   ├── install-butler-gateway-service.sh
│   ├── butler-gateway-ops.sh    #   status | restart | logs | preflight | upgrade
│   ├── lib/butler-gateway-preflight.sh
│   └── systemd/butler-gateway.service
├── docs/
│   ├── architecture/            #   v4 架构、Hermes 解耦/提炼
│   ├── design/                  #   产品设计
│   └── guides/                  #   运维、微信冒烟、人工测试
├── tests/                       #   默认 ~931 passed（排除 live_llm / archive）
├── projects/                    #   用户项目工作区
├── logs/                        #   butler-gateway.log（gitignore *.log）
├── archive/                     #   Butler v1 快照
└── pyproject.toml               #   包名 butler-system；`[wechat]` extra
```

## 常用命令

```bash
pip install -e ".[wechat]"
cp .env.example .env              # 配置 MINIMAX_API_KEY 等

butler chat                       # CLI
butler wechat-setup               # 微信扫码绑定
bash scripts/install-butler-gateway-service.sh   # systemd 用户服务
bash scripts/butler-gateway-ops.sh status        # 网关运维

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
