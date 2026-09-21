# Butler v5 生产加固指南

> **适用范围**：本指南面向 self-host Butler v5 的部署者。
> **关联**：[SECURITY.md](../../SECURITY.md)（漏洞披露） · [v5 production architecture](../../docs/architecture/v5-production-architecture-2026-08.md)（已知限制） · [AGENTS.md](../../AGENTS.md)（项目约定）

部署 WFXM Butler v5 不只是 `docker compose up`。本文档列出自托管场景下必须配置的 **3 大类**加固措施。

---

## 1. Secrets 管理

### 1.1 必备 secrets

| Secret | 来源 | 用途 |
|--------|------|------|
| `POSTGRES_PASSWORD` | `openssl rand -hex 32` | Postgres 密码 |
| `ANTHROPIC_API_KEY` | Anthropic Console | LLM API key |
| `DB_PASSWORD` | 同 `POSTGRES_PASSWORD`（或独立） | App 连 DB 凭证 |

### 1.2 注入方式（3 选 1）

#### A. .env 文件（推荐 self-host）

```bash
cat > .env <<EOF
POSTGRES_PASSWORD=$(openssl rand -hex 32)
ANTHROPIC_API_KEY=sk-ant-...
DB_PASSWORD=\${POSTGRES_PASSWORD}
EOF
chmod 600 .env
```

#### B. 环境变量（CI/CD / k8s）

```bash
export POSTGRES_PASSWORD=...
export ANTHROPIC_API_KEY=sk-ant-...
docker compose up -d postgres butler
```

#### C. Secret manager（生产推荐）

- AWS Secrets Manager
- HashiCorp Vault
- 1Password CLI
- 任何支持 env 注入的 secret store

应用通过 `${VAR}` 引用，secret store 在容器启动前注入 env。

### 1.3 运行时处理（Secret<T> 包装）

应用层使用 `Secret<T>` 包装层（参考 [secret.ts](../../butler-v5/packages/adapters/src/wechat/secret.ts)）：

```typescript
// ❌ 错误：直接读 env（可能在 log 泄露）
const apiKey = process.env.ANTHROPIC_API_KEY!;

// ✅ 正确：通过 Secret<T>
import { Secret } from "@butler/adapters/wechat/secret.js";
const apiKey = Secret.create(process.env.ANTHROPIC_API_KEY!);
// cleartext 仅在 .unwrap() 时暴露；toString() 返回 "[REDACTED]"，toJSON() 返回 {"__secret__":true}
```

### 1.4 ❌ 反模式

- ❌ 镜像内 hardcode 任何 secret（即使 build-time 也不可）
- ❌ `.env` 文件 commit 到 git（`.gitignore` 排除）
- ❌ 在 issue / commit message / log 中贴完整 secret
- ❌ Secret 通过 URL query 传递（应在 body 或 header）
- ❌ Secret 在 Slack / 邮件明文传输

---

## 2. 容器安全

### 2.1 root → non-root（必须）

WFXM 镜像默认以 UID 1001 (`butler`) 运行：

```bash
docker compose exec butler id
# 期望：uid=1001(butler) gid=1001(butler)
```

如未生效，需检查 `Dockerfile` 的 `USER butler` 指令。

### 2.2 Read-only file system（必须）

`docker-compose.yml` 已配置：

```yaml
services:
  butler:
    read_only: true
    tmpfs:
      - /tmp           # node 临时文件
      - /app/.cache    # node 模块 cache
    volumes:
      - butler-data:/app/data:rw  # 仅 audit log / undo state 可写
```

### 2.3 Capability dropping（推荐）

```yaml
services:
  butler:
    cap_drop:
      - ALL
    cap_add:
      - CHOWN          # postgres client 需要
      - SETUID         # node user 切换
      - SETGID
    security_opt:
      - no-new-privileges:true
```

### 2.4 Resource limits（推荐）

```yaml
services:
  butler:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
```

### 2.5 Image hygiene

#### CVE 扫描（推荐 weekly）

```bash
trivy image ghcr.io/xiazihundun/wfxm:v5.0.1
```

集成到 CI 可考虑 `aquasecurity/trivy-action`。

#### 签名验证（cosign keyless）

```bash
cosign verify \
  --certificate-identity-regexp 'https://github.com/XiaZiHunDun/WFXM' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
  ghcr.io/xiazihundun/wfxm:v5.0.1
```

镜像由 release workflow 自动签名，验证通过表明未篡改。

### 2.6 镜像来源

- ✅ 仅 `ghcr.io/xiazihundun/wfxm:TAG`（本项目 release workflow 产出）
- ❌ 不使用 `:latest`（除非 dev 环境；prod 必须 pinned tag）
- ❌ 不使用 third-party fork / mirror
- ❌ 不使用 docker hub / 私人 registry

---

## 3. 网络暴露

### 3.1 owner-route 默认 127.0.0.1（必须）

WFXM owner-route 设计为 **单 owner 本机访问**，**绝不暴露公网**：

```yaml
services:
  butler:
    ports:
      - "127.0.0.1:3000:3000"   # 仅 loopback
      # ❌ "0.0.0.0:3000:3000" — 绝不允许
```

### 3.2 远程访问方案（3 选 1，按威胁模型）

#### 方案 A：SSH tunnel（最简单）

```bash
# 本地：监听 3000 + 转发
ssh -L 3000:127.0.0.1:3000 user@butler-host

# 远程访问：http://127.0.0.1:3000
```

**适用**：单机 / 家用服务器 / 偶尔远程

#### 方案 B：WireGuard VPN（推荐）

```bash
# 服务器
wg-quick up wg0

# 客户端
wg-quick up ~/wg0-butler.conf
# 加入后所有流量走 VPN；owner-route 默认就 accessible
```

**适用**：跨设备访问、admin 多设备、需要稳定连接

#### 方案 C：Cloudflare Tunnel（零端口暴露）

```bash
# 服务器
cloudflared tunnel create butler
cloudflared tunnel route dns butler butler.example.com
cloudflared tunnel run butler

# 远程访问：https://butler.example.com（Cloudflare 中转）
```

**适用**：想让 owner-route 在公网但不想开端口
**注意**：必须配 Cloudflare Access 鉴权（避免 URL 暴露即访问）

### 3.3 Postgres 端口（必须内网）

```yaml
services:
  postgres:
    ports:
      - "127.0.0.1:5432:5432"   # 仅 loopback
```

外部访问 Postgres 用 SSH tunnel 或 admin VPN。

### 3.4 WebSocket / SSE 暴露（视场景）

owner-route 默认 `:3000`。如果启用 WebSocket（如 subagent push）走同端口（Hono 同 listener）。

不要为 WebSocket 单独开端口 → 攻击面倍增。

### 3.5 ❌ 反模式

- ❌ 把 owner-route 暴露公网（任何形式）
- ❌ 用 ngrok / frp 等临时隧道到公网
- ❌ Docker `network_mode: host`（绕过隔离）
- ❌ `ports: - "3000:3000"`（无 host binding，绑 0.0.0.0）
- ❌ Docker socket 暴露（`/var/run/docker.sock` 挂载到容器）

---

## 4. 部署后验证清单

执行以下命令逐项验证：

```markdown
- [ ] `docker compose ps` 显示所有 service `healthy`
- [ ] `curl http://127.0.0.1:3000/health` 返回 200 + `{status: "ok"}`
- [ ] `curl http://127.0.0.1:3000/` 需鉴权（401/403）
- [ ] `docker inspect butler-app | jq '.[0].Config.User'` = `"butler"` (non-root)
- [ ] `docker inspect butler-app | jq '.[0].HostConfig.ReadonlyRootfs'` = `true`
- [ ] `trivy image ghcr.io/xiazihundun/wfxm:vX.Y.Z` 无 Critical CVE
- [ ] `cosign verify ...` 通过（镜像签名）
- [ ] Postgres 仅监听 127.0.0.1:5432（`ss -tnlp | grep 5432`）
- [ ] butler 镜像无 `latest` tag（pinned）
- [ ] .env 文件权限 `600`（owner only）
- [ ] 远程访问走 SSH/WireGuard/Cloudflare Tunnel（不直连公网）
- [ ] audit_events 表存在且持续写入（`psql -c "SELECT COUNT(*) FROM audit_events"`）
```

---

## 5. 持续维护

| 任务 | 频率 | 工具 |
|------|------|------|
| 依赖更新 | weekly（Dependabot 自动 PR） | [`.github/dependabot.yml`](../../.github/dependabot.yml) |
| 镜像 CVE 扫描 | weekly（手动或 CI） | Trivy |
| 镜像版本升级 | 月度评估 | owner 决定 |
| Postgres backup | daily | pg_dump + cron |
| audit log 归档 | weekly | 自定义脚本 |
| WFXM 新 release | watch GH releases | owner 订阅 |

Postgres backup 示例 cron：
```cron
# /etc/cron.d/butler-backup
0 3 * * * docker exec butler-postgres pg_dump -U butler butler_v5 | gzip > /backup/butler_$(date +\%Y\%m\%d).sql.gz
```

---

## 6. 已知限制

参考 [v5 production architecture § 已知限制](../../docs/architecture/v5-production-architecture-2026-08.md)：

- 单 owner 设计 → 多用户场景不适用
- PostgreSQL + WeChat iLink 强依赖 → 离线部署受限
- LLM API key 必须可用 → 离线推理不支持
- 容器未配 rate limit → 受攻击时依赖上游 Cloudflare/WireGuard
- 单镜像单 entry point → 水平扩展需额外架构

---

## 7. 反馈与升级

发现部署问题：

1. [GitHub Issues](https://github.com/XiaZiHunDun/WFXM/issues) — bug/feature（新 issue 选择 `bug_report.md` 模板）
2. [GitHub Discussions](https://github.com/XiaZiHunDun/WFXM/discussions) — 一般讨论（启用后）
3. [SECURITY.md](../../SECURITY.md) — 漏洞披露（GitHub Security Advisories 主路径）

---

> **历史**
> - 2026-09-21：初版（D77 T6，伴随 v5.0.0 release 一同 ship）
