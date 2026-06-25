# ADR — 本机 Claude Code CLI 桥接（可选 · 暂缓立项）

> **状态**：**部分落地**（2026-06-25）— `butler/runtime/cc_bridge.py` + `/cc-bridge`；全量 systemd watcher 仍可选  
> **上级 ADR**：[`dev-capability-ceiling-vs-cc-cli-2026-06.md`](dev-capability-ceiling-vs-cc-cli-2026-06.md) §4 P3  
> **产品边界**：[`roadmap-backlog-and-boundaries-2026-05.md`](roadmap-backlog-and-boundaries-2026-05.md) §1.3

---

## 1. 问题

- Butler **远程 dev 委派**在机械层刻意低于本机 CC CLI（白名单 terminal、无全 shell）。
- 偶发 **重编码任务**（大 refactor、多文件 import 链、长 pytest 修复环）在微信回合里成本高、成功率低。
- 主公本机已装 **Claude Code CLI**；希望「重任务本机跑、Butler 记报告」，而非把 CC 嵌进 Loop 替代 `delegate_task`。

## 2. 决策

| 项 | 结论 |
|----|------|
| **是否立项** | **否（暂缓）** — 先跑通 P1 真机飞轮 + G1-04 生产证据 |
| **是否否决** | **否** — 保留为可选 P3，书面变更边界后可立项 |
| **对标关系** | 互补：Butler 派工/门控/记忆；CC 执行重编码 |
| **不做什么** | 不用 CC/Cursor **替代** `agent_loop`；不做 IDE 嵌入；不做无门控 shell 透传 |

## 3. 草图方案（若未来立项）

```text
微信 Owner: 「这个大 refactor 太重，批准本机 CC」
    → Lead 识别 heavy_task + human_gate
    → Owner /批准 cc-bridge <project> <task摘要>
    → Gateway 写 ~/.butler/jobs/cc_bridge_pending.yaml
    → 本机 watcher（systemd --user 或 cron）:
         claude -p "<task>" --cwd <workspace>  # 或官方 CLI 等价
    →  stdout/报告 + git diff stat → butler_remember / AgentReport
    → 微信摘要：完成/失败 + 关键文件
```

| 组件 | 说明 |
|------|------|
| 门控 | `BUTLER_CC_BRIDGE=1` + Owner `/批准`；默认 **关** |
| 执行面 | **本机子进程** CC CLI，非 Butler 容器内全 shell |
| 记忆 | 报告入 L3/L4 + `delegate_dev_outcomes`；**不**自动 push |
| 安全 | workspace 锁定、无 `BUTLER_*` 密钥注入 CC 子进程 env |

## 4. ROI vs 风险

| 收益 | 成本 / 风险 |
|------|-------------|
| 重任务成功率接近本机 CC | 双运行时运维（网关 + 本机 watcher） |
| 微信仍为一入口 | 报告回填一致性、diff 过大摘要难读 |
| 与「不对标 IDE」一致 | 误用为默认路径 → Lead 不再委派 |

**触发立项的最低条件**（建议）：

1. P1 飞轮每月 sim 稳定 + ≥1 条 `prod_delegate_*` G1-04 证据  
2. 生产 `prod_delta` 显示 verify_fail 率连续 2 周无改善  
3. 主公书面确认「重任务每周 ≥1 次」

## 5. 验收标准（IF 立项）

| # | 验收 |
|---|------|
| A1 | `BUTLER_CC_BRIDGE=0` 时零代码路径 |
| A2 | `/批准 cc-bridge` 后 10 分钟内微信收到结构化摘要 |
| A3 | 失败时 audit 行 + 不静默；Owner 可 `/诊断` 见 pending job |
| A4 | 不增加 `delegate_task` 深度；不 import Hermes / Cursor |

## 6. Agent 引用

- 讨论 **是否做 CC 桥接** → **本文** + 上级 Dev 上限 ADR  
- 讨论 **当前 Dev 能力** → 以 `delegate_task` + dev_engine 为准，**勿**默认需要桥接

## 7. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-06-23 | 初版：暂缓立项；草图 + ROI + 验收 IF |
