# v5 Sandbox 出网 Host Allowlist — 方案设计（2026-08）

> **状态**：P2b/c/d ✅ 已落地（Grant + egress proxy + opt-in slirp）；见 [`v5-sandbox-p2d-slirp-spike-2026-08.md`](v5-sandbox-p2d-slirp-spike-2026-08.md)  
> **前置**：A8 已落地 — `BUTLER_V5_SANDBOX=bubblewrap`、Grant `sandboxProfile`、binary network deny/allow  
> **关联**：[`v5-post-boundary-roadmap-2026-08.md`](v5-post-boundary-roadmap-2026-08.md) P2、[`v5-product-boundaries-2026-08.md`](../decisions/v5-product-boundaries-2026-08.md) §执行隔离

---

## 1. 现状（已交付）

| 能力 | 实现 |
| --- | --- |
| 工作区 bind | bwrap `--bind $WORKSPACE $WORKSPACE` |
| 默认出网 | `--unshare-net`（`workspace-write-network-deny`） |
| Owner 提升 | 审批 `elevateNetwork` → `workspace-write-network-allow`（无 `--unshare-net`） |
| 执行入口 | `run_command` → `executeArgvInSandbox` + ALS `currentSandboxProfileName()` |
| 点验 | `butler sandbox-probe` / `pnpm smoke:sandbox-network` |
| 系统 python | ro-bind `/etc/alternatives`（使 `/usr/bin/python3` 在沙箱内可解析） |

**刻意不做**：per-host 细粒度过滤（本文件 scope）。

---

## 2. 问题

Binary **deny / allow** 无法满足常见生产需求：

- `pnpm install` 需要 **registry 域名**（如 `registry.npmjs.org`），不应全开网；
- LLM / 微信网关已在宿主进程，**不应**靠 `network-allow` 让工具侧随意出网；
- Policy 误放行时，allow-all 风险过大。

产品边界（`v5-product-boundaries`）要求：提升 sandbox profile 必须写入 **短期、不可委派 ScopedGrant**；allowlist 应同样绑定 Grant，而非全局 env 永久放行。

---

## 3. 目标（立项后）

1. 默认仍 **network-deny**（与 today 一致）。
2. 新增第三档 profile（名称待定）：**`workspace-write-network-allowlist`**，Grant 携带 **host:port 列表**（或 CIDR 子集）。
3. Owner 审批时可：`elevateNetwork: false` + `networkAllowlist: ["registry.npmjs.org:443"]`（示例）。
4. fail-closed：解析失败、iptables 应用失败、未知 profile → 拒绝执行。
5. 审计：`AuditEvent` 记录 profile + allowlist hash（不记录全量 secret URL）。

---

## 4. 技术选项对比

| 方案 | 机制 | 优点 | 缺点 | 建议 |
| --- | --- | --- | --- | --- |
| **A. bwrap + slirp4netns + iptables/nft** | 独立 netns，slirp 出网，iptables 按 dst 过滤 | 与现有 bwrap 栈一致；可测 | 需 cap/net_admin；slirp 运维复杂 | **首选（Linux 生产）** |
| **B. 用户态 egress proxy** | 沙箱内仅 `HTTP(S)_PROXY=127.0.0.1`；proxy 做 host ACL | 不碰 netns；易日志 | 需信任 proxy；非 HTTP 难控 | MCP/HTTP 工具备选 |
| **C. firejail** | 替代 bwrap | 内置 network | 第二套沙箱栈；与 A8 分叉 | **否决**（双栈） |
| **D. Docker/E2B  per-run** | 容器网络 policy | 隔离强 | 过重；产品边界为 opt-in | 远期 optional provider |

**推荐路径**：Phase 1 设计 Grant schema + proxy MVP（B，仅 HTTPS）；Phase 2 slirp+iptables（A）替换 proxy 热路径。

---

## 5. 数据模型（草案）

### 5.1 Grant 扩展

```sql
-- 0009_sandbox_network_allowlist.sql (draft, not applied)
ALTER TABLE scoped_grants ADD COLUMN IF NOT EXISTS network_allowlist jsonb;
-- ["registry.npmjs.org:443", "pypi.org:443"]
```

`ScopedGrantRecord`：

- `sandboxProfile`: `workspace-write-network-allowlist`
- `networkAllowlist`: `readonly string[]`（规范化：`host:port`，小写 host，默认 443）

校验（domain 层）：

- 最多 N 条（建议 8）；
- 禁止 `0.0.0.0/0`、私有段出网（除非 Owner 显式 `BUTLER_V5_SANDBOX_ALLOW_PRIVATE_EGRESS=1` opt-in）；
- IDN punycode 规范化。

### 5.2 环境变量（立项后，非 today）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `BUTLER_V5_SANDBOX_NETWORK_MODE` | `binary` | `binary` \| `allowlist`（启用第三档） |
| `BUTLER_V5_SANDBOX_EGRESS_PROXY` | — | Phase 1：本地 proxy 监听地址 |
| `BUTLER_V5_SANDBOX_ALLOW_PRIVATE_EGRESS` | `0` | 是否允许 RFC1918 目标 |

**不**新增全局 permanent allowlist env（避免绕过 Grant）。

---

## 6. 执行流（Phase 2 目标）

```mermaid
sequenceDiagram
  participant Loop
  participant Grant
  participant Bwrap
  participant Netns
  participant Iptables

  Loop->>Grant: run_command + sandboxProfile=allowlist
  Grant->>Bwrap: executeArgvInSandbox(profile, allowlist)
  Bwrap->>Netns: unshare net + slirp
  Bwrap->>Iptables: DROP except dst allowlist
  Bwrap->>Loop: stdout / fail-closed
```

CLI 点验（立项后）：

```bash
butler sandbox-probe --mode allowlist --hosts registry.npmjs.org:443
pnpm smoke:sandbox-allowlist
```

---

## 7. 验收标准（立项 gate）

- [ ] 默认 deny：现有 `pnpm smoke:sandbox-network` 仍 PASS  
- [ ] allowlist Grant：`pnpm install` 类 argv 仅允许列表内 host 成功  
- [ ] 列表外 host：fail-closed + 审计事件  
- [ ] 无 Grant allowlist 时不能通过 env 单独开网  
- [ ] 文档：`reference.md` + Owner approve API 示例  

---

## 8. 与本仓库其他决策对齐

- **v4** `.butler/sandbox.json` `networkPolicy.allow`：v5 **不**机械搬运；语义收敛到 Grant.allowlist（见 `remote-dev-strategy-2026-06.md` 仅作历史参考）。
- **MCP HTTP**：allowlist 与 `run_command` 共用 `executeArgvInSandbox` 入口（A8 已统一）。
- **微信入站**：不受沙箱影响；沙箱仅副作用工具链。

---

## 9. 建议排期

| 阶段 | 内容 | 估时 |
| --- | --- | --- |
| **P2a（文档）** | 本文件 + roadmap 链接 | ✅ 2026-08-22 |
| **P2b** | Grant schema + Owner API `networkAllowlist` + 域校验 | ✅ 2026-08-22 |
| **P2c** | egress proxy MVP + 单测 | ✅ 2026-08-22 |
| **P2d** | slirp4netns + iptables + raw socket 探测 | ✅ opt-in（`SANDBOX_EGRESS_ISOLATION=slirp`）；见 [`v5-sandbox-p2d-slirp-spike-2026-08.md`](v5-sandbox-p2d-slirp-spike-2026-08.md) |

**生产点验**：`pnpm smoke:allowlist-production`（可选 `--pnpm` live registry）。

---

## 10. 参考命令（today）

```bash
# binary 点验
pnpm smoke:sandbox-network

# allowlist egress proxy（P2c）
pnpm smoke:sandbox-allowlist

# 生产串联点验 + P2d 预检
pnpm smoke:allowlist-production
pnpm smoke:allowlist-pnpm   # 需外网

butler sandbox-p2d-preflight

# run_command 集成（本机需 bwrap）
pnpm exec vitest run apps/api/src/workspace-tools.bubblewrap.test.ts
```
