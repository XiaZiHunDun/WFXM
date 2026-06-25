# ADR — 远程开发终局：Butler Dev + CC CLI 互补（2026-06）

> **状态**：已采纳（2026-06-25）  
> **上级**：[dev-capability-ceiling-vs-cc-cli-2026-06.md](dev-capability-ceiling-vs-cc-cli-2026-06.md)  
> **运营评估**：[butler-system-assessment-and-ops-2026-06.md](butler-system-assessment-and-ops-2026-06.md)  
> **实现**：`butler/runtime/cc_bridge.py`、`butler/gateway/commands/cc_bridge_commands.py`、`butler/gateway/commands/sandbox_commands.py`

---

## 1. 产品终局（修订）

**目标**：微信远程场景下，Butler 应能承担 **日常远程开发**（改码、测、配项目），**不必**每次依赖本机 IDE；本机 **Claude Code CLI** 作为 **重任务加速器**，而非唯一执行面。

| 执行面 | 场景 | 机制 |
|--------|------|------|
| **Butler 委派 dev** | 常规改码、pytest、patch | `delegate_task` + workspace 工具 |
| **Butler terminal** | 网关机验收命令 | 白名单 + 可选 bubblewrap（`dev-remote` / `dev-gateway`） |
| **CC CLI 桥接** | 大 refactor、长环修复 | Owner `/cc-bridge` → 本机 `claude` 子进程 |
| **本机 Cursor/CC** | 人在电脑前 | 产品文档 `/分工` 说明，非 Loop 嵌入 |

**不做的终局**：全量 MCP Host、无门控 shell、IDE 嵌入 Loop。

## 2. 环境 Profile 三档 + 远程档

| Profile | terminal | OS 沙箱 | CC 桥接 | 典型 |
|---------|----------|---------|---------|------|
| `lead` | 关 | — | 关 | 微信生产 Lead |
| `dev-local` | 开 | 关 | 可选 | 本机开发 |
| `dev-gateway` | 开 | 开 | 关 | Linux 网关 + bwrap |
| **`dev-remote`** | 开 | 开 | **开** | **远程替代 CC 主战场** |

应用：`python3 scripts/apply-butler-env-profile.py dev-remote`

## 3. 沙箱与配置 UX

- **`.env` / 网关级**：`BUTLER_TERMINAL_SANDBOX` 等须改 `.env` + restart；`/沙箱` 给指引，不写 `.env` 文件。
- **项目 `sandbox.json`**：Owner `/沙箱 策略` 可写 workspace `.butler/sandbox.json`（绕过 dev patch 写保护）。
- **网络**：`networkPolicy.allow` 非空 + `BUTLER_TERMINAL_SANDBOX_NETWORK_ALLOWLIST=1` 时 **不** `--unshare-net`（信任宿主机防火墙；**无** CC 级域代理，后续可立项 socat）。

## 4. CC CLI 桥接（由暂缓 → opt-in 实现）

- 开关：`BUTLER_CC_BRIDGE=1`（`dev-remote` profile 默认开）
- 命令：`/cc-bridge <任务摘要>`（别名 `/批准 cc-bridge`）
- 执行：网关宿主机 `claude -p …`（`BUTLER_CC_CLI` 可覆盖路径），cwd=当前项目 workspace
- 门控：仅 Owner；默认异步 + 微信完成推送
- 安全：子进程 env 剥离 `BUTLER_*` / API keys；不自动 git push

立项条件（原 ADR）已满足「最小可用」；全量 watcher/systemd 仍可选。

## 5. 验收

```bash
PYTHONPATH=. pytest tests/test_cc_bridge.py tests/test_terminal_sandbox_network.py tests/test_sandbox_commands.py -q
python3 scripts/apply-butler-env-profile.py dev-remote --dry-run
```

微信：`/沙箱` · `/cc-bridge 用一句话总结 README`（需 `claude` 在 PATH）
