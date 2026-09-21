# D77 Cycle 23 — Docker Deployment + CI/CD + Hardening Design Spec

**日期**：2026-09-21
**作者**：owner + Claude (brainstorming flow)
**状态**：✅ Approved (Section 1-7 全 approved)
**Cycle**：D77 (cycle 23)
**Ship 累計目标**：22 cycles × 5 ship = 110 → D77 add 7 ship = **117 ship 累計**（首次 7-ship cycle）

## 背景与动机

D76 cycle 22 完成 OSS 门面 5 件套 + CHANGELOG 回填（[spec](2026-09-21-oss-handbook-design.md)）。Owner 接受 3 维度梳理计划（可以部署 / 功能正常 / 文档体系），本 spec 覆盖 **维度 1 — 可以部署**。

**现状缺口**：
- 无 root Dockerfile（Dockerfile + .dockerignore 缺失）
- `butler-v5/docker-compose.yml` 604 字节，只有 postgres + wechat-mock，**无 butler app service**
- 无 release workflow（`.github/workflows/` 只有 ci.yml，是 v4 Python legacy CI）
- 无 Dependabot 配置
- 无 health check endpoint
- 无 production hardening 文档

**cycle 23 目标**：让 WFXM "可以部署"——一个 owner `git clone` 后能跑 `docker compose up`，GH Actions 自动发布镜像，依赖自动更新，部署安全规范有 doc。

## 设计决策汇总

| 维度 | 决定 | 理由 |
|------|------|------|
| Scope | 7 deliverables in 1 cycle | D76 6 commits 模式已 prove；7 T 类似规模 |
| Base image | `node:20-bookworm-slim` + multi-stage | debuggable + 体积优化 + 社区默认 |
| Release trigger | tag push (`v*`) + workflow_dispatch | 严格 semver 控制 + 手动重跑 |
| Container registry | ghcr.io | GitHub 原生 + public 免费 + 自动鉴权 |
| Multi-arch | linux/amd64 + linux/arm64 | Apple Silicon + AWS Graviton + RPi 覆盖 |
| Dependabot scope | npm + github-actions + docker | 不含 pip (v4 EOL per ADR-0001) |
| Hardening depth | secrets + 容器 + 网络 | 3 大类核心；不展开 backup/restore (D78 docs) |
| Compose strategy | 最小补充（butler service 加入） | 现有 postgres + wechat-mock 保留；dev workflow 不变 |
| Health check | 包入 D77 + §20 KNOWN_ENTRY_POINTS 更新 | 部署闭环必须；side-fix 模式延续 D75 T1 |
| Cycle scope vs sub-cycle | 单 cycle（不走 D77a/b/c split） | D-series 纪律；artifact→CI→runtime 内聚 |

---

## §1 Architecture Overview

**Owner 视角**：
```
git tag v5.0.1 → push
    ↓
GitHub Actions (release.yml) — multi-arch build (amd64 + arm64)
    ↓
Push to ghcr.io/xiazihundun/wfxm:v5.0.1 + SBOM + cosign sign
    ↓
Dependabot 每周一 9am UTC 扫描 npm/actions/dockerfile
    ↓
Owner pull 镜像 → docker compose up → 服务跑起来
```

**Layer 分离**：
1. **Build layer** (T1) — root Dockerfile + .dockerignore
2. **Distribution layer** (T2 + T3) — release workflow + Dependabot
3. **Runtime layer** (T4 + T5) — docker-compose + /health endpoint
4. **Operational layer** (T6) — production hardening 文档
5. **Validation layer** (T7) — acceptance scenarios + methodology

**Out of scope** (D77 不做)：
- Demo deployment / E2E tests（→ D79 functional）
- Backup/restore strategy（→ D78 docs）
- RISC-V arch / Helm chart / k8s manifests
- release-please bot
- Self-hosting runbook（→ D79 functional）

---

## §2 Dockerfile 设计

**File**: `/home/ailearn/projects/WFXM/Dockerfile` (new, ~70 行)

### 3-stage multi-stage build

```dockerfile
# syntax=docker/dockerfile:1.7
# ---------- Stage 1: deps (pnpm fetch + install) ----------
FROM node:20-bookworm-slim AS deps
WORKDIR /repo

RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates python3 build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN corepack enable && corepack prepare pnpm@9.15.0 --activate

COPY pnpm-workspace.yaml package.json ./
COPY apps packages cli ./apps ./packages ./cli
RUN pnpm fetch --frozen-lockfile
RUN pnpm install --frozen-lockfile --offline --ignore-scripts

# ---------- Stage 2: build (compile TypeScript) ----------
FROM deps AS build
WORKDIR /repo
COPY . .
RUN pnpm -r build

# ---------- Stage 3: runtime (minimal final image) ----------
FROM node:20-bookworm-slim AS runtime
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client tini ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1001 butler \
    && useradd --system --uid 1001 --gid butler --no-create-home butler

ENV NODE_ENV=production \
    PNPM_HOME=/usr/local/share/pnpm \
    PATH=/usr/local/share/pnpm:$PATH

COPY --from=build --chown=butler:butler /repo/apps /app/apps
COPY --from=build --chown=butler:butler /repo/packages /app/packages
COPY --from=build --chown=butler:butler /repo/cli /app/cli
COPY --from=build --chown=butler:butler /repo/node_modules /app/node_modules
COPY --from=build --chown=butler:butler /repo/package.json /app/package.json
COPY --from=build --chown=butler:butler /repo/pnpm-workspace.yaml /app/pnpm-workspace.yaml

USER butler

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD pg_isready -h "${DB_HOST:-postgres}" -p "${DB_PORT:-5432}" -U "${DB_USER:-butler}" \
   && node -e "fetch('http://127.0.0.1:' + (process.env.PORT||3000) + '/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))" \
  || exit 1

EXPOSE 3000
ENTRYPOINT ["/usr/bin/tini", "--"]

# Default cmd — implementer must verify correct entry point path
# against butler-v5 `pnpm -r build` output (likely apps/api/dist/main.js
# or cli/dist/index.js depending on package being primary)
CMD ["node", "apps/api/dist/main.js"]
```

**Layer 优化**：deps 单独 stage 缓存 pnpm install（lockfile 改动少）；build stage 编译 source（频繁改动）；runtime 只 copy 产物（最小）。

**镜像体积目标**：
| Stage | 估算大小 |
|-------|---------|
| `deps` | ~1.2 GB（不导出） |
| `build` | ~1.5 GB（不导出） |
| `runtime`（最终） | **~250-300 MB** |

vs `node:20-bookworm` 默认 ~900MB → **节省 ~70%** 体积。

**Security 关键点**：non-root user (uid 1001) + no shell + tini signal handling + HEALTHCHECK embedded + no secrets in image。

### Multi-arch 策略

Dockerfile 本身 arch-neutral。multi-arch 由 release.yml 触发：
```yaml
- uses: docker/setup-qemu-action@v3
- uses: docker/setup-buildx-action@v3
- run: docker buildx build --platform linux/amd64,linux/arm64 --push .
```

buildx QEMU 在 amd64 runner 上 emulate arm64。arm64 build 慢（~5x），首次 ~10min，后续 cached ~2-3min。

### .dockerignore

**File**: `/home/ailearn/projects/WFXM/.dockerignore` (new, ~30 行)

白名单策略：默认排除 `*.md` 但显式 include 4 个 OSS 文件（CHANGELOG/CoC/SECURITY/CONTRIBUTING）— 被 `/app/` 内嵌用。

---

## §3 Release workflow

**File**: `/home/ailearn/projects/WFXM/.github/workflows/release.yml` (new, ~100 行)

### Triggers

```yaml
on:
  push:
    tags: ['v*']
  workflow_dispatch:
    inputs:
      tag: {required: true, type: string}
      dry_run: {type: boolean, default: false}
```

### Job 1: validate

- 提取 tag（push event 或 workflow_dispatch input）
- 校验 semver (`^v[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$`)
- 输出 `tag` + `version` 给下游 jobs

### Job 2: build

- **Permissions**: `contents:write / packages:write / id-token:write` (cosign OIDC)
- **Matrix**: `linux/amd64` + `linux/arm64`
- **Steps**:
  - checkout + QEMU + buildx setup
  - login ghcr.io (GITHUB_TOKEN auto)
  - metadata-action 生成 tags (semver + major.minor + latest + sha)
  - buildx build + push (cache-from/to type=gha)
  - **provenance: true** (SLSA) + **sbom: true** (镜像内嵌)
  - **anchore/sbom-action@v0** 生成 CycloneDX SBOM artifact
  - **cosign sign** keyless (OIDC via GitHub Actions identity)
- **Cache**: `cache-from: type=gha` + `cache-to: type=gha,mode=max` — 首次 10-15min，后续 2-3min

### Job 3: release

- 依赖 validate + build
- 收集 SBOM artifacts
- 生成 release notes（git log 自上次 tag + SBOM 链接）
- `softprops/action-gh-release@v2` 创建 GH release（带 SBOM attachments）
- Pre-release 自动：tag 含 `-` 时

### 关键设计点

| 维度 | 选择 |
|------|------|
| Permissions scoping | 3 job 各自声明最小权限 |
| Provenance | true（SLSA attestation） |
| SBOM | CycloneDX JSON format |
| Cosign | keyless + OIDC（无需密钥管理） |
| Tag strategy | `5.0.1` + `5.0` + `latest` + `sha-abc1234` |

### 镜像 tag 矩阵

| Trigger | 镜像 |
|---------|------|
| `git tag v5.0.1 && push` | `:5.0.1` + `:5.0` |
| main branch latest | `:latest` |
| 任意 commit SHA | `:sha-abc1234` |
| Pre-release (含 `-`) | draft + prerelease flag |

---

## §4 Dependabot + docker-compose 更新

### File 1: `.github/dependabot.yml` (T3, ~50 行)

3 个 ecosystem：

```yaml
version: 2
updates:
  - package-ecosystem: "npm"
    directory: "/butler-v5"
    schedule: {interval: "weekly", day: "monday", time: "09:00", timezone: "UTC"}
    open-pull-requests-limit: 5
    labels: ["dependencies", "butler-v5"]
    groups:
      butler-v5-minor: {patterns: ["*"], update-types: ["minor", "patch"]}
      butler-v5-major: {patterns: ["*"], update-types: ["major"]}
    ignore:
      - dependency-name: "@anthropic-ai/sdk"  # API 兼容性手动 review
      - dependency-name: "pnpm"
      - dependency-name: "typescript"

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule: {interval: "weekly", day: "monday", time: "09:00", timezone: "UTC"}
    open-pull-requests-limit: 3
    labels: ["dependencies", "ci"]

  - package-ecosystem: "docker"
    directory: "/"
    schedule: {interval: "weekly", day: "monday", time: "09:00", timezone: "UTC"}
    open-pull-requests-limit: 3
    labels: ["dependencies", "docker"]
```

**关键策略**：weekly Monday 09:00 UTC（避开 release 日）；minor+patch 合并 / major 独立；critical deps ignore（@anthropic-ai/sdk / pnpm / typescript 即使 patch 也手动 review）。

### File 2: `butler-v5/docker-compose.yml` update (T4)

**当前状态**（604 字节）：只有 postgres + wechat-mock，**无 butler app service**。

**更新后**：加 butler service（从 ghcr.io pull + healthcheck + read_only + resource limits + non-root-friendly）。

**关键 diff**：
| 维度 | 之前 | 之后 |
|------|------|------|
| butler service | ❌ 缺失 | ✅ 从 ghcr.io pull |
| env secrets | hardcoded `butler_dev` | `${VAR:?required}` 强制 |
| port binding | `0.0.0.0:` | `127.0.0.1:`（loopback only） |
| health check | 仅 postgres | ✅ butler + postgres |
| profiles | 无 | ✅ `wechat-mock` 仅 dev/test |
| resource limits | 无 | ✅ cpus + memory |
| read_only fs | 无 | ✅ butler read_only + tmpfs |
| security_opt | 无 | ✅ no-new-privileges |

**Compose 使用**：
```bash
export POSTGRES_PASSWORD=$(openssl rand -hex 32)
export ANTHROPIC_API_KEY=sk-ant-...
export TAG=v5.0.1
docker compose up -d postgres butler  # wechat-mock 不启（不在 profiles）

# Dev (with wechat-mock)
docker compose --profile dev up
```

**dev workflow 兼容**：`butler-v5/scripts/cutover/smoke-*.mjs` 等脚本可继续 host 上 `pnpm` 跑。Compose 仅 deployment unit。

---

## §5 /health endpoint（T5 small new route）

**File**: `/home/ailearn/projects/WFXM/butler-v5/apps/api/src/routes/health.ts` (new, ~60 行)

**Routes**：
- `GET /health` — combined liveness + readiness（200 ok / 503 degraded）
- `GET /health/live` — pure liveness（无 deps）

**Response schema**：
```json
// Healthy (200)
{
  "status": "ok",
  "version": "5.0.1",
  "uptime_seconds": 3600,
  "timestamp": "2026-09-21T11:23:45.000Z",
  "checks": {
    "db": { "status": "up", "latency_ms": 2 }
  }
}

// Degraded (503)
{
  "status": "degraded",
  "version": "5.0.1",
  ...,
  "checks": { "db": { "status": "down", "latency_ms": null } }
}
```

**关键设计**：
- 单端点 + `/live` 拆分（Docker HEALTHCHECK start_period 用 /live）
- 无 auth（LB / Docker healthcheck 无 credentials；OS-level network 防御）
- DB check 复用现有 db client（`db.query("SELECT 1")`）
- 503 而非 500（标准健康检查语义）
- 不在 response 暴露 secrets
- 不 cache response（readiness 必须真实）

**Files**：
- `butler-v5/apps/api/src/routes/health.ts` (new)
- `butler-v5/apps/api/src/routes/index.ts` (modify, +3 行 register)
- `butler-v5/apps/api/src/routes/health.test.ts` (new, ~50 行 unit test)

**Side-fix**：§20 KNOWN_ENTRY_POINTS 更新（per D75 T1 pattern，T5 加 /health 后 KNOWN_ENTRY_POINTS 列表需更新）

**与 Dockerfile HEALTHCHECK 协同**：
- Docker HEALTHCHECK: pg_isready + /health
- Compose butler service: HEALTHCHECK via curl
- K8s: livenessProbe → /health/live, readinessProbe → /health

---

## §6 Production hardening 指南（T6 doc）

**File**: `/home/ailearn/projects/WFXM/docs/deployment/production-hardening.md` (new, ~300 行)
**File**: `/home/ailearn/projects/WFXM/docs/deployment/README.md` (new, ~15 行索引页)

### 7 节结构

1. **Secrets 管理** — 必备 secrets（POSTGRES_PASSWORD / ANTHROPIC_API_KEY / DB_PASSWORD）+ 3 注入方式（.env / env var / secret manager）+ Secret<T> 包装层 + ❌ 反模式（hardcode / commit / URL query）
2. **容器安全** — non-root user 验证 + read_only fs + cap_drop ALL + cap_add CHOWN/SETUID/SETGID + resource limits + Trivy CVE 扫描 + cosign verify + 镜像来源（仅 ghcr.io pinned tag）
3. **网络暴露** — owner-route 默认 127.0.0.1 + 3 远程访问方案（SSH tunnel / WireGuard / Cloudflare Tunnel）+ Postgres 内网 + ❌ 反模式（公网暴露 / ngrok / network_mode host / 0.0.0.0 binding）
4. **部署后验证清单** — 11 项 checkbox（healthcheck / non-root / read_only / trivy clean / cosign verify / port binding / pinned tag / .env chmod 600 / remote access 走 tunnel）
5. **持续维护** — 6 任务表（Dependabot weekly / Trivy weekly / 镜像月度升级 / Postgres backup daily / audit log 归档 weekly / 订阅 GH releases）
6. **已知限制** — cross-link 到 v5 production architecture doc
7. **反馈与升级** — Discussions / Issues / SECURITY 漏洞披露 3 路径

### Cross-link 矩阵

- `SECURITY.md` (D76) — 漏洞披露
- `docs/architecture/v5-production-architecture-2026-08.md` — 已知限制
- `AGENTS.md` "OSS 手册" section (D76 T5.1) — cross-link 索引
- `butler-v5/Dockerfile` (本 cycle T1) — 镜像源
- `.github/workflows/release.yml` (本 cycle T2) — 发布流程

### 关键内容决策

| 维度 | 选择 |
|------|------|
| 网络方案 3 选项 | SSH tunnel / WireGuard / Cloudflare Tunnel（覆盖单机 → 跨设备 → 公网） |
| 反模式清单 | 显式列出 5+ ❌（与 D-series "❌" 习惯一致） |
| ❌ 不含 | backup/restore strategy（D78 docs）+ metrics 暴露（D79 functional） |
| Length | ~300 行（7 节 + checklist + 维护 + 限制 + 反馈） |

---

## §7 7-T delivery schedule + cycle gates

### 7 commits

| T | Commit | Files | Workload |
|---|--------|-------|----------|
| T1 | `feat(deploy) D77 T1 close DEPLOY-DOCKERFILE: ...` | Dockerfile + .dockerignore | 1-1.5h |
| T2 | `feat(ci) D77 T2 close DEPLOY-RELEASE: ...` | release.yml | 1.5-2h |
| T3 | `chore(ci) D77 T3 close DEPLOY-DEPENDABOT: ...` | dependabot.yml | 30min |
| T4 | `feat(deploy) D77 T4 close DEPLOY-COMPOSE: ...` | docker-compose.yml (modify) | 45min |
| T5 | `feat(api) D77 T5 close DEPLOY-HEALTH: ...` | health.ts + index.ts (modify) + test + §20 | 45min |
| T6 | `docs(deploy) D77 T6 close DEPLOY-HARDENING: ...` | production-hardening.md + README.md | 1.5h |
| T7 | `chore(docs) D77 T7 close DEPLOY-VALIDATE: ...` | scenarios_docker_deploy.md + m15 test | 30min |
| **合计** | **8 files (7 new + 1 modify)** | **~6-7h** |

**Ship 累計**：22 cycles × 5 ship = 110 → D77 add 7 ship = **117 ship 累計**（首次 7-ship cycle）

### Cycle 收尾 verification

```bash
cd /home/ailearn/projects/WFXM/butler-v5

# 1. 7 commits landed
git log --oneline -7

# 2. Docker compose syntax check
docker compose -f /home/ailearn/projects/WFXM/butler-v5/docker-compose.yml config

# 3. All gates baseline match + delta
pnpm lint && pnpm typecheck && pnpm test:full
pnpm acceptance  # 96·96 → 100·100 (+4 DEP scenarios)
pnpm methodology  # 13·13 → 14·14 (+1 M15)
pnpm knip  # 0
```

---

## 取舍决定汇总（10 个）

| # | 决策点 | 选择 |
|---|--------|------|
| Q1 | Cycle scope | 7 deliverables in 1 cycle（不走 sub-cycle split） |
| Q2 | Base image | `node:20-bookworm-slim` + 3-stage multi-stage |
| Q3 | Release trigger | tag push (`v*`) + workflow_dispatch |
| Q4 | Container registry | ghcr.io |
| Q5 | Multi-arch | linux/amd64 + linux/arm64 |
| Q6 | Dependabot scope | npm + github-actions + docker（不含 pip） |
| Q7 | Hardening depth | secrets + 容器 + 网络（中等） |
| Q8 | Compose strategy | 最小补充 + butler service 加入 |
| Q9 | Health check | 包入 D77 + §20 KNOWN_ENTRY_POINTS 更新 |
| Q10 | Cycle split vs single | 单 cycle（D77 不分 a/b/c） |

---

## Out of Scope（不在本 spec 处理）

- Demo deployment / E2E tests（→ D79 functional cycle）
- Backup/restore strategy（→ D78 docs cycle）
- Self-hosting runbook（→ D79 functional）
- Multi-arch additional（riscv64 等）
- Helm chart / k8s manifests
- release-please bot 集成
- Metrics 暴露（Prometheus exporter 等）

预计作为 cycle 24-25+ 的 functional + docs 维度内容。

---

## Related

- **Predecessor spec**: [[docs/superpowers/specs/2026-09-21-oss-handbook-design.md]] (D76 OSS 治理)
- **Plan** (gitignored): `docs/superpowers/plans/2026-09-21-d77-docker-deploy-plan.md`（after writing-plans skill）
- **Memory**:
  - [[project-pause-state-post-D76-FULL-CYCLE-2026-09-21]] — D76 110-ship pause
  - [[project-fix-D76-T1-2026-09-21]] — D76 T1 (CHANGELOG backfill)
  - [[project-fix-D76-T2-T5-2026-09-21]] — D76 T2-T5 + T5.1
- **D-series ship 累計**: 22 cycles × 5 ship = 110 (D55→D76) → cycle 23 add 7 → **117 ship**
- **§20 invariant** (KNOWNN_ENTRY_POINTS): D75 T1 建立 + D77 T5 更新（加 /health）
