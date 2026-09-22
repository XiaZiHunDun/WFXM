# Butler v5 自托管指南

> **D79 T3 · 2026-09-22** | 适用范围：个人 / 小团队 self-host Butler v5
> **关联**：[`production-hardening.md`](production-hardening.md)（生产加固细节） · [`README.md`](../../README.md)（项目根） · [`../../butler-v5/README.md`](../../butler-v5/README.md)（开发指南）

本指南覆盖从 0 到 production-ready 的完整 self-host 路径。先看 §0 一键启动，30 秒跑起来；再按需深入 §1-§10。

---

## §0 Quick start（30 秒）

零真实 LLM 试玩（无需 API key / Docker / Postgres）：

```bash
cd butler-v5
pnpm install
pnpm demo    # 脚本化 fixture LLM + 内存 PGlite CLI REPL
```

真实 LLM + Docker Compose 自托管（推荐）：

```bash
cp .env.example .env
# 编辑 .env，填入 POSTGRES_PASSWORD 和 ANTHROPIC_API_KEY
docker compose pull
docker compose up -d postgres butler
curl http://127.0.0.1:3000/health   # 期望 {"status":"ok"}
```

`docker compose up -d` 启动后，访问 `http://127.0.0.1:3000` 即可。

---

## §1 Prerequisites

| 项 | 最低 | 推荐 | 备注 |
|----|------|------|------|
| Docker | 24.0+ | 26.0+ | `docker --version` 验证 |
| Docker Compose | v2.20+ | v2.27+ | `docker compose version` 验证（v2 不是 `docker-compose`） |
| CPU | 2 核 | 4 核 | 含 postgres |
| 磁盘 | 10 GB | 50 GB | postgres 数据 + 日志 + 备份 |
| 内存 | 1 GB | 4 GB | 含 postgres + butler |
| 端口 | 3000, 5432 | — | 防火墙放行（仅 127.0.0.1 也可，外部需 reverse proxy） |
| LLM API key | Anthropic API | — | [`ANTHROPIC_API_KEY`] 必填 |

**架构前提**：butler-v5 是 self-hosted 单 owner 设计，不支持多用户 / 多租户（D-series §6 维度 4 候选）。

---

## §2 Install

### 2.1 获取代码

```bash
git clone https://github.com/xiazihundun/wfxm.git
cd wfxm
git checkout main   # 或具体 tag 如 v5.0.1
```

### 2.2 准备 secrets

```bash
cp .env.example .env
chmod 600 .env
# 编辑 .env：
#   POSTGRES_PASSWORD=$(openssl rand -hex 32)
#   ANTHROPIC_API_KEY=sk-ant-...（从 https://console.anthropic.com 获取）
```

### 2.3 拉取镜像

```bash
docker compose pull
# 首次拉取 ~500MB（node:20-bookworm-slim + postgres:16-alpine）
```

### 2.4 启动

```bash
docker compose up -d postgres butler
# 查看启动日志：
docker compose logs -f butler
```

### 2.5 验证

```bash
# 1. 容器状态
docker compose ps
# 期望：postgres (healthy) + butler (healthy)

# 2. /health endpoint
curl -fsS http://127.0.0.1:3000/health
# 期望：{"status":"ready",...}

# 3. 数据库连通性
docker compose exec postgres pg_isready -U butler -d butler_v5
```

如果 §2.5 全部 ✅，self-host 启动成功。继续 §3 配置参数。

---

## §3 Configuration

`.env` 文件是配置的唯一真值源（compose.yml 不内嵌 secrets）。下表是所有可调 env vars：

| Env var | 必填 | 默认 | 用途 |
|---------|------|------|------|
| `POSTGRES_PASSWORD` | ✅ | — | Postgres 用户密码 |
| `POSTGRES_USER` | — | `butler` | Postgres 用户名 |
| `ANTHROPIC_API_KEY` | ✅ | — | LLM API key |
| `LOG_LEVEL` | — | `info` | `debug` / `info` / `warn` / `error` |
| `PORT` | — | `3000` | butler HTTP 监听端口 |
| `TAG` | — | `latest` | butler 镜像 tag（D77 release.yml 自动签） |
| `BUTLER_LLM_PROVIDER` | — | `anthropic` | LLM provider（仅 `anthropic`） |
| `BUTLER_LLM_MODEL` | — | `claude-haiku-4-5` | 默认模型（推荐 Haiku 4.5：成本/速度平衡） |
| `INTAKE_ENABLED` | — | `1` | 微信入站开关（`0` = 仅 CLI / HTTP） |

**多 key 轮换**：暂不支持。改 key 后需重启 butler 容器：

```bash
docker compose restart butler
```

**数据库连接**：`compose.yml` 已将 `DB_HOST=postgres` 注入但ler，不用调。

---

## §4 Deploy

### 4.1 单机（默认）

`docker compose up -d postgres butler` 即单实例部署。适合个人 / 小团队（< 100 次对话/天）。

### 4.2 反向代理（公网访问）

在 butler 前加 Nginx / Caddy 终止 TLS：

```nginx
# /etc/nginx/sites-available/butler.conf
server {
  listen 443 ssl http2;
  server_name butler.example.com;

  ssl_certificate /etc/letsencrypt/live/butler.example.com/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/butler.example.com/privkey.pem;

  location / {
    proxy_pass http://127.0.0.1:3000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
```

**注意**：reverse proxy 必须设置 `X-Forwarded-For`（用于 audit / rate-limit）。但ler 不解析 trust-strip header（避免 SSRF）；具体详见 [`production-hardening.md`](production-hardening.md) §4。

### 4.3 数据卷挂载

compose.yml 默认创建 `pgdata` + `butler-data` 两个 named volumes。备份见 §6。

### 4.4 资源限制

compose.yml 已设置但ler 容器：
- CPU limit 2 核 / reserve 0.5 核
- Memory limit 2 GB / reserve 512 MB

postgres 容器未限制（建议手动加）。

详细加固（容器 hardening / 镜像签名 / SBOM）见 [`production-hardening.md`](production-hardening.md)。

---

## §5 Monitor

### 5.1 /health endpoint

```bash
curl http://127.0.0.1:3000/health
# {"status":"ready","uptimeSec":1234,"db":"ok","llm":"ok"}
```

支持 liveness（200 if alive）和 readiness（200 if db+llm 都 ok）。

### 5.2 日志

```bash
# 实时日志
docker compose logs -f butler

# 最近 1000 行 + grep error
docker compose logs --tail=1000 butler | grep -i error
```

日志格式 JSON（`LOG_LEVEL=info` 时 INFO/WARN/ERROR）。`LOG_LEVEL=debug` 输出 LLM request/response（**含 prompt**，小心敏感信息）。

### 5.3 Postgres 监控

```bash
docker compose exec postgres psql -U butler -d butler_v5 -c "
  SELECT pid, state, query_start, LEFT(query, 80)
  FROM pg_stat_activity
  WHERE state != 'idle';
"
```

### 5.4 推荐 alerts

| 指标 | 阈值 | 触发 |
|------|------|------|
| `/health` 5xx | 3 次/5 分钟 | butler 容器崩了 |
| postgres 连接数 > 80 | 持续 10 分钟 | 连接泄漏 |
| 磁盘使用 > 80% | 持续 30 分钟 | 数据卷满 |
| CPU 持续 > 90% | 持续 15 分钟 | 资源不足 |

推荐 Prometheus + Grafana 自托管（详见 [prometheus.io/docs](https://prometheus.io/docs/)）。但ler 内置 `/metrics` endpoint（Prometheus 格式）可用。

---

## §6 Backup & restore

### 6.1 备份策略

**每日 1 次 pg_dump + 保留 7 天**：

```bash
# /opt/butler-backup.sh
#!/bin/bash
set -euo pipefail
BACKUP_DIR="/var/backups/butler"
mkdir -p "$BACKUP_DIR"
docker compose exec -T postgres pg_dump -U butler butler_v5 \
  | gzip > "$BACKUP_DIR/butler_$(date +%Y%m%d_%H%M%S).sql.gz"
find "$BACKUP_DIR" -name "butler_*.sql.gz" -mtime +7 -delete
```

加 cron：

```cron
# 每日 03:00 备份（避开 [00:00] / [00:30] 高峰）
3 3 * * * /opt/butler-backup.sh >> /var/log/butler-backup.log 2>&1
```

### 6.2 恢复

```bash
# 1. 停但ler（避免连接）
docker compose stop butler

# 2. 恢复数据
gunzip -c /var/backups/butler/butler_20260922_030000.sql.gz \
  | docker compose exec -T postgres psql -U butler -d butler_v5

# 3. 重启但ler
docker compose start butler

# 4. 验证
curl http://127.0.0.1:3000/health
```

### 6.3 数据卷备份

pg_dump 是逻辑备份（推荐）。如需物理备份：

```bash
docker compose stop postgres
docker run --rm -v pgdata:/from -v $(pwd):/to alpine \
  tar czf /to/pgdata_$(date +%Y%m%d).tar.gz -C /from .
docker compose start postgres
```

---

## §7 Upgrade

```bash
# 1. 拉取新版本（commit by SHA 或 main）
git pull
git log --oneline -5   # 看 changelog

# 2. 拉新镜像
TAG=v5.0.2 docker compose pull

# 3. 重启容器（无停机 rolling：先 butler 后 postgres）
docker compose up -d butler
docker compose up -d postgres

# 4. 自动跑 db migrations（但ler 启动时执行）
docker compose logs -f butler | grep migration

# 5. 验证
curl http://127.0.0.1:3000/health
```

**回滚**：保留 `pgdata` 命名卷；如数据 schema 不兼容旧版本，需先 dump 当前数据再升级（见 §6.2）。

---

## §8 Troubleshoot

### 8.1 端口占用（"bind: address already in use"）

```bash
sudo lsof -i :3000   # 查占用进程
sudo lsof -i :5432
# 解决：杀掉进程 / 改 compose ports 映射 / 加 reverse proxy
```

### 8.2 Postgres 连不上（"ECONNREFUSED 127.0.0.1:5432"）

```bash
docker compose ps                 # 期望 postgres (healthy)
docker compose logs postgres      # 看是否有 migration 失败
docker compose exec postgres pg_isready -U butler
```

### 8.3 ANTHROPIC_API_KEY 无效（"401 invalid api key"）

```bash
# 验证 key 格式：sk-ant-api03-...
grep ANTHROPIC_API_KEY .env
# 解决：从 console.anthropic.com 重新生成，编辑 .env，docker compose restart butler
```

### 8.4 wechat-mock 未起（仅 dev profile）

```bash
# wechat-mock 在 compose profiles=["dev","test"]，默认 prod 不起
docker compose --profile dev up -d wechat-mock
```

### 8.5 OOM（butler 容器 killed）

```bash
docker compose logs butler | grep -i "killed\|oom"
dmesg | grep -i "oom\|killed process"   # 看内核 OOM killer
# 解决：增加 memory limit（compose.yml `deploy.resources.limits.memory`）
```

### 8.6 渠道连不上（微信 / Slack / Telegram）

每个 channel 有独立 secret（`BUTLER_V5_WECHAT_*` / `SLACK_*` / `TELEGRAM_*`）。检查：

```bash
docker compose logs butler | grep -i "channel\|secret\|auth"
```

详见 [`production-hardening.md`](production-hardening.md) §4。

### 8.7 approval 卡死（"waiting_approval 超时"）

```bash
docker compose exec postgres psql -U butler -d butler_v5 -c "
  SELECT id, status, created_at FROM approvals WHERE status = 'waiting';
"
```

### 8.8 db migration 失败（容器起不来）

```bash
docker compose logs butler | grep -i migration
# 看具体失败的 migration 文件 → 手动跑或回滚（详 production-hardening §0）
```

---

## §9 FAQ

**Q: 数据存在哪？**
A: Postgres 数据卷 `pgdata`（默认 named volume）。

**Q: 怎么改端口？**
A: 编辑 `compose.yml` `services.butler.ports` + `services.postgres.ports`，重 `up -d`。

**Q: 能跑多 owner 吗？**
A: 不能。当前是单 owner 设计（v5 范围）；多 owner 是 D-series §6 维度 4 长期候选。

**Q: 怎么回滚 / 备份 / 监控 / 贡献 / 报漏洞？**
A: 回滚 `git checkout <old-sha>` + `TAG=<old-tag> docker compose up -d`（migration 可能单向，详 §7）；备份见 §6；监控见 §5；贡献见 [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md)；漏洞见 [`../../SECURITY.md`](../../SECURITY.md)（均 D76 闭环）。

---

## §10 指针

| 需求 | 读这里 |
|------|--------|
| 30 秒跑起来 / 真实启动 / 配置 | → §0 / §2 / §3 |
| 公网部署 + TLS | → §4.2 |
| 加固细节 | → [`production-hardening.md`](production-hardening.md) |
| 监控 / 备份 / 升级 / 报错 | → §5 / §6 / §7 / §8 |
| 容器架构 / Dockerfile | → [`../../docker-compose.yml`](../../docker-compose.yml) / [`../../Dockerfile`](../../Dockerfile) |
| v5 架构 + 调用链 | → [`../../docs/architecture/v5-production-architecture-2026-08.md`](../../docs/architecture/v5-production-architecture-2026-08.md) |
| D-series 累计 + 维度 | → [`../ROADMAP.md`](../ROADMAP.md) §3 |
| demo / 本地无 LLM 试玩 | → [`../../butler-v5/README.md`](../../butler-v5/README.md) `pnpm demo` |

---

**End of SELF-HOSTING** | D79 T3 · 2026-09-22 · 维度 2 demo-batch 之一