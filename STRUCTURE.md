# 仓库目录结构

> Butler v4：**仅微信**消息网关（`butler gateway --platforms wechat`）。  
> **Cursor / Agent**：新会话先读 [`AGENTS.md`](AGENTS.md)（事实来源与易错点）。  
> **`reference/`**：主公维护的外部竞品/标本对照区（gitignore），**整理方案不修改此目录**。

```
WFXM/
├── butler/                      # ★ Butler v4 产品代码
│   ├── core/                    #   Agent Loop 栈（含 design_md_sections、tool_implicit_context）
│   ├── experiments/             #   研究模式账本、METRIC、crash_guard
│   ├── transport/               #   LLM Provider / 客户端
│   ├── gateway/                 #   消息处理、session、/health
│   │   └── platforms/           #   wechat_ilink.py（iLink）
│   ├── runtime/ workflows/    #   定时任务、短工作流
│   ├── tools/ memory/ skills/ cli/ ops/   # memory: chunking、query_decompose、semantic_index
│   ├── project*.py              #   项目注册 / Lead / preflight
│   └── main.py                  #   `butler` CLI 入口
├── scripts/                     #   见 scripts/README.md
├── docs/
│   ├── architecture/            #   v4 架构、ADR、Hermes 解耦（已完成）
│   ├── design/                  #   产品设计
│   ├── guides/                  #   运维、冒烟、接入
│   ├── config/                  #   config.yaml.example、reference.md
│   ├── plans/                   #   规划索引 README + CC/整理/外部对标
│   ├── ops/                     #   /诊断 阈值等运维说明
│   └── reviews/                 #   项目评估
├── tests/                       #   默认 ~1816 passed（排除 live_llm）
├── projects/                    #   LingWen1、DemoPilot 等工作区
├── logs/                        #   butler-gateway.log（gitignore *.log）
├── archive/                     #   README + Git 标签 archive/butler-v1-20260522
├── reference/                   #   【不动】外部对照，主公维护
└── pyproject.toml               #   包名 butler-system；`[wechat]` extra
```

## 常用命令

```bash
pip install -e ".[wechat]"
cp .env.example .env              # 配置 MINIMAX_API_KEY 等

butler chat                       # CLI
butler project preflight --project 灵文1号
butler doctor                     # 静态安全配置审计
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
| [`docs/README.md`](docs/README.md) | 文档索引（2026-05-25） |
| [`docs/plans/README.md`](docs/plans/README.md) | 规划文档与 P0/P2/P3 命名对照 |
| [`docs/architecture/v4-architecture.md`](docs/architecture/v4-architecture.md) | v4 架构（CC 线束 + 外部对标） |
| [`docs/plans/cc-butler-gap-analysis-2026-05.md`](docs/plans/cc-butler-gap-analysis-2026-05.md) | CC 对照与 Loop 线束 |
| [`docs/guides/four-reports-capabilities-2026-05.md`](docs/guides/four-reports-capabilities-2026-05.md) | 四报告已落地能力速查 |
| [`docs/plans/four-reports-out-of-scope-2026-05.md`](docs/plans/four-reports-out-of-scope-2026-05.md) | 四报告明确不做清单 |
| [`docs/plans/reference-learning-plan-2026-05.md`](docs/plans/reference-learning-plan-2026-05.md) | 外部对标（已收口） |
| [`docs/ops/diagnostic-thresholds.md`](docs/ops/diagnostic-thresholds.md) | `/诊断` 运行指标阈值 |
| [`docs/guides/wechat-gateway-ops.md`](docs/guides/wechat-gateway-ops.md) | 微信网关 systemd 运维 |
| [`docs/guides/wechat-daily-smoke-checklist.md`](docs/guides/wechat-daily-smoke-checklist.md) | 发版真机冒烟 |
| [`tests/README.md`](tests/README.md) | 测试分层与守门命令 |
| [`scripts/README.md`](scripts/README.md) | 脚本索引 |
| [`docs/plans/consolidation-2026-05.md`](docs/plans/consolidation-2026-05.md) | 整理与瘦身方案 |
| [`docs/config/reference.md`](docs/config/reference.md) | 环境变量速查 |
