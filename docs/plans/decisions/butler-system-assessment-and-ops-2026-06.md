# ADR — Butler 系统评估与运营策略（2026-06-25）

> **状态**：已采纳  
> **主路径**：Butler 自带开发工具（`delegate_task` + 文件工具 + dev terminal + dev_engine）  
> **CC CLI**：`/cc-bridge` opt-in，**非主路径**  
> **关联**：[`remote-dev-strategy-2026-06.md`](remote-dev-strategy-2026-06.md) · [`dev-capability-ceiling-vs-cc-cli-2026-06.md`](dev-capability-ceiling-vs-cc-cli-2026-06.md)

---

## 1. 评估结论（摘要）

| 维度 | 结论 |
|------|------|
| 架构 | v4 自建 Loop + 微信网关 **可运营**，CC 线束 P0–P4 已对齐 |
| Owner 微信面 | P0–P2 已落地；handler sim **17/17**（owner-ux + remote-dev + memory） |
| **Butler 开发主链** | Lead → `delegate_task` → dev → patch/terminal → VERIFY → `/详细` **完整可用** |
| vs CC CLI | 机械层刻意更低；Loop/记忆/多项目 **更强** |
| 主要缺口 | **真机 dev 飞轮运营证据**（G1-04 OT2 窗至 07-31）、非功能缺失 |

## 2. Profile 决策（本机网关）

| 选项 | 适用 | 本机选择 |
|------|------|----------|
| `lead` | 微信纯统筹，terminal 关，改码只委派 | — |
| `dev-local` | 本机开发，无 bwrap | — |
| `dev-gateway` | Linux 网关 + 沙箱，无 CC 桥接 | — |
| **`dev-remote`** | **远程开发主战场**：terminal + bwrap + Butler dev 工具 | **✅ 当前** |

**理由**：主公以 Butler 自带工具做远程开发；`dev-remote` 与 bubblewrap、委派 terminal 验收一致。  
**注意**：日常纯聊天若不想暴露 terminal，可另设 `lead` 网关实例；本机统一 `dev-remote` 亦可接受。

## 3. 运营节奏（Butler-native，不用 CC）

| 频率 | 动作 |
|------|------|
| **每月** | `bash scripts/butler-dev-flywheel-monthly.sh` |
| 每月 | 微信真机 1 条（见 [`dev-flywheel-monthly.md`](../../guides/dev-flywheel-monthly.md)） |
| 每周 | `butler-prod-delta-observe.sh` · `butler-lingwen-live-capture-checklist.sh` |
| 每日 | `butler-ops-followup-check.sh` |

## 4. project.yaml 标准（试点）

每个 Lead 项目应配置：

```yaml
dev:
  test_command: "…"   # 必填；驱动 VERIFY + /测试
  lint_command: "…"   # 必填
  build_command: "…"  # 可选
```

- **灵文1号**：已接 `../../tests/` 子集  
- **普通试点项目**：已接仓库内快测子集（见 `projects/DemoPilot/project.yaml`）

## 5. 沙箱与 npm

- 项目 `.butler/sandbox.json` 可配 `networkPolicy.allow`（npm/pypi）  
- `dev-remote` 已开 `BUTLER_TERMINAL_SANDBOX_NETWORK_ALLOWLIST=1`  
- 仍无 CC 级域代理；顽固场景用 `/批准沙箱外 npm install`

## 6. 暂不投入

- `/cc-bridge` 日常化  
- 全量 MCP Host、无门控 shell  
- 成本数值标定（G1-02 搁置）

## 7. 验收

```bash
bash scripts/butler-pilot-dev-testing.sh
bash scripts/butler-dev-flywheel-monthly.sh
bash scripts/butler-dev-live-flywheel-checklist.sh --probe
```
