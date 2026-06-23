# 仓库目录结构

> Butler v4：**仅微信**消息网关（`butler gateway --platforms wechat`）。  
> **Cursor / Agent**：新会话先读 [`AGENTS.md`](AGENTS.md)（事实来源与易错点）。  
> **`reference/`**：主公维护的外部竞品/标本对照区（gitignore），**整理方案不修改此目录**。

```
WFXM/
├── butler/                      # ★ Butler v4 产品代码
│   ├── core/                    #   Agent Loop 栈（agent_loop、context_pipeline、tool_batch…）
│   ├── dev_engine/              #   Dev 委派、VERIFY、B9 课程与 live 评测
│   ├── experiments/             #   研究模式账本、METRIC、crash_guard
│   ├── transport/               #   LLM Provider / 客户端
│   ├── gateway/                 #   消息处理、session、斜杠命令（`commands/` 单轨）
│   │   ├── commands/            #   斜杠命令实现 + handlers（dev/project/registry…）
│   │   └── platforms/           #   wechat_ilink.py（iLink）
│   ├── runtime/                 #   定时任务、runtime jobs
│   ├── workflows/               #   短工作流 YAML / runner
│   ├── tools/                   #   工具注册与实现（含 delegate_task）
│   ├── memory/                  #   chunking、semantic_index、observation store
│   ├── skills/                  #   Skill 管理
│   ├── project/                 #   项目注册、Lead、preflight、archetypes
│   ├── cli/                     #   butler 子命令注册（doctor、registry、mcp…）
│   ├── ops/                     #   eval、B9、head_to_head、prod 观测、health_report
│   ├── human_gate.py            #   Workflow 门控
│   └── main.py                  #   `butler` CLI 入口
├── scripts/                     #   见 scripts/README.md（eval/B9/sim/head-to-head 索引）
├── docs/
│   ├── architecture/            #   v4 架构、ADR、项目激活/门控/扩展路径
│   ├── design/                  #   产品设计
│   ├── guides/                  #   运维、冒烟、接入
│   ├── config/                  #   config.yaml.example、reference.md
│   ├── plans/                   #   规划索引 README + CC/整理/外部对标
│   ├── ops/                     #   /诊断 入口矩阵、阈值
│   └── reviews/                 #   项目评估
├── tests/                       #   默认全量 pytest（排除 live_llm）
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
butler doctor                     # 部署诊断（见 docs/ops/diagnostic-entrypoints.md）
butler wechat-setup               # 微信扫码绑定
bash scripts/install-butler-gateway-service.sh   # systemd 用户服务
bash scripts/butler-gateway-ops.sh status        # 网关运维
bash scripts/butler-pre-release-smoke.sh         # 发版守门

PYTHONPATH=. pytest -q
./scripts/butler-five-reports-gate.sh   # 五报告 P5–P10 + PR-F 守门
butler registry verify
```

## 文档入口

| 文档 | 说明 |
|------|------|
| [`README.md`](README.md) | 项目总览 |
| [`docs/README.md`](docs/README.md) | 文档索引（2026-05-25） |
| [`docs/DOCUMENTATION.md`](docs/DOCUMENTATION.md) | 文档体系、维护规则、语料专项 |
| [`docs/plans/README.md`](docs/plans/README.md) | 规划文档与 P0/P2/P3 命名对照 |
| [`docs/plans/decisions/roadmap-backlog-and-boundaries-2026-05.md`](docs/plans/decisions/roadmap-backlog-and-boundaries-2026-05.md) | 否决 / Backlog 决策入口 |
| [`docs/architecture/v4-architecture.md`](docs/architecture/v4-architecture.md) | v4 架构（CC 线束 + 外部对标） |
| [`docs/plans/active/cc-butler-gap-analysis-2026-05.md`](docs/plans/active/cc-butler-gap-analysis-2026-05.md) | CC 对照与 Loop 线束 |
| [`docs/guides/four-reports-capabilities-2026-05.md`](docs/guides/four-reports-capabilities-2026-05.md) | 四报告已落地能力速查 |
| [`docs/plans/decisions/four-reports-out-of-scope-2026-05.md`](docs/plans/decisions/four-reports-out-of-scope-2026-05.md) | 四报告明确不做清单 |
| [`docs/plans/archive/reference-learning-plan-2026-05.md`](docs/plans/archive/reference-learning-plan-2026-05.md) | 外部对标（已收口） |
| [`docs/ops/diagnostic-entrypoints.md`](docs/ops/diagnostic-entrypoints.md) | `/诊断` vs `butler doctor` vs `/doctor` |
| [`docs/ops/diagnostic-thresholds.md`](docs/ops/diagnostic-thresholds.md) | `/诊断` 运行指标阈值 |
| [`docs/guides/wechat-gateway-ops.md`](docs/guides/wechat-gateway-ops.md) | 微信网关 systemd 运维 |
| [`docs/guides/wechat-daily-smoke-checklist.md`](docs/guides/wechat-daily-smoke-checklist.md) | 发版真机冒烟 |
| [`tests/README.md`](tests/README.md) | 测试分层与守门命令 |
| [`scripts/README.md`](scripts/README.md) | 脚本索引 |
| [`docs/plans/archive/consolidation-2026-05.md`](docs/plans/archive/consolidation-2026-05.md) | 整理与瘦身方案 |
| [`docs/plans/archive/butler-closed-loop-optimization-plan-2026-06-09.md`](docs/plans/archive/butler-closed-loop-optimization-plan-2026-06-09.md) | 闭环优化规划（归档） |
| [`projects/LingWen1/docs/pilot-log.md`](projects/LingWen1/docs/pilot-log.md) | 灵文试点时间线与验收 |
| [`docs/config/reference.md`](docs/config/reference.md) | 环境变量速查 |
