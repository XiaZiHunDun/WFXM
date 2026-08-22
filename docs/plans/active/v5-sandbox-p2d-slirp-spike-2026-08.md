# P2d Sandbox — slirp + iptables（2026-08-22）

> **状态**：P2d MVP ✅（opt-in `BUTLER_V5_SANDBOX_EGRESS_ISOLATION=slirp`）  
> **前置**：P2b/c ✅  
> **关联**：[`v5-sandbox-network-allowlist-2026-08.md`](v5-sandbox-network-allowlist-2026-08.md)

---

## 1. 实现摘要

| 组件 | 路径 |
|------|------|
| slirp 编排 | `packages/adapters/src/sandbox/slirp-egress.ts` |
| 集成入口 | `executeArgvInSandbox`（`bubblewrap-runner.ts`） |
| 预检 | `butler sandbox-p2d-preflight` |
| 冒烟 | `butler sandbox-probe-allowlist-slirp` / `pnpm smoke:allowlist-slirp` |

**默认**仍为 P2c（`BUTLER_V5_SANDBOX_EGRESS_ISOLATION=proxy`）。

---

## 2. P2d 数据流

```
Grant networkAllowlist
  → egress proxy（host 0.0.0.0:随机端口，allowlist 过滤）
  → unshare -U -r -n
      → slirp4netns tap0
      → iptables OUTPUT：仅 lo + 10.0.2.2:proxyPort
      → bwrap --share-net + HTTPS_PROXY=http://10.0.2.2:port
```

- raw TCP 至非 allowlist 主机：**iptables DROP**
- honor proxy 的 HTTP(S)：**经 host gateway 到 egress proxy**，再按 Grant 过滤

---

## 3. 启用（生产 opt-in）

```bash
# ~/.config/butler-v5/env
BUTLER_V5_SANDBOX=bubblewrap
BUTLER_V5_SANDBOX_NETWORK_MODE=allowlist
BUTLER_V5_SANDBOX_EGRESS_ISOLATION=slirp

systemctl --user restart butler-v5-gateway.service
pnpm smoke:allowlist-production --slirp
```

---

## 4. 主机要求

| 检查项 | 说明 |
|--------|------|
| `unshare -U -r -n` | rootless netns |
| `slirp4netns --configure` | 用户态 NAT |
| `iptables` | netns 内 OUTPUT 规则 |
| `cap_net_admin` | 建议有（bounding set） |
| slirp host gateway | guest 经 `10.0.2.2` 访问 host 上 egress proxy |

**已知限制**：部分主机 slirp guest→host gateway 不可用或 outbound NAT 受限；此时 P2d 探测 fail-closed，保持 P2c proxy 模式。

---

## 5. 验收 gate

- [x] slirp 模式代码 + 单测
- [x] raw socket 探测（`sandbox-probe-allowlist-slirp`）
- [ ] 生产 env 启用 slirp（Owner opt-in）
- [ ] live registry + slirp 同机 PASS（依赖 host gateway 连通）

---

## 6. 回滚

```bash
# 去掉或设为 proxy
BUTLER_V5_SANDBOX_EGRESS_ISOLATION=proxy
# 或删除该行（默认 proxy）
```

P2c egress proxy 可独立运行，无需 slirp。
