# Docker Deployment Acceptance Scenarios

> **Cycle**: D77 (cycle 23)
> **Date**: 2026-09-21
> **Branch**: main
> **Spec**: [docs/superpowers/specs/2026-09-21-d77-docker-deploy-design.md](../../docs/superpowers/specs/2026-09-21-d77-docker-deploy-design.md)

本文件定义 cycle 23（D77）docker deployment 的 acceptance scenarios。共 4 个场景 + 1 个 methodology check。

## Scenario DEP-HB-01: Dockerfile builds successfully (multi-arch)

**目的**：验证 Dockerfile 在 multi-arch (amd64 + arm64) 下 build 成功

**前置条件：**
- Docker + buildx installed
- Docker daemon running
- 用户有 ghcr.io/xiazihundun 写权限 (CI 自动；本地 dry-run 不需要)

**步骤：**
1. `docker buildx create --use` (确保 buildx 可用)
2. `docker buildx build --platform linux/amd64,linux/arm64 --progress=plain .` (dry-run；不 --push)

**验收：**
- 2 个平台 build 均 exit 0
- 最终镜像 `<none>`（dry-run 无 push）+ 中间 stage 缓存成功
- 镜像体积 ~250-300 MB（vs 未优化 ~900MB）

**自动化（pseudo）：**
```bash
docker buildx build --platform linux/amd64,linux/arm64 --progress=plain . 2>&1 | tail -30
# Expected: 2 platforms built, both exit 0
```

## Scenario DEP-HB-02: docker compose up starts all services healthy

**目的**：验证 docker-compose.yml 配置合法 + 服务能启起来

**前置条件：**
- Docker compose v2 installed
- ghcr.io/xiazihundun/wfxm:latest 已 publish（release workflow dry-run 也行）

**步骤：**
1. `docker compose -f butler-v5/docker-compose.yml config` (syntax check)
2. 设置 fake env vars (POSTGRES_PASSWORD=test, ANTHROPIC_API_KEY=fake)
3. `TAG=latest docker compose up -d postgres butler` (skip wechat-mock, dev profile)
4. 等 30s
5. `curl -s http://127.0.0.1:3000/health | jq`
6. `docker compose down -v`

**验收：**
- `docker compose ps` 显示 postgres + butler `healthy`
- `/health` 返回 200 + `{status: "ok", checks: {db: {status: "up", latency_ms: <number>}}`
- postgres 端口仅监听 127.0.0.1:5432 (`ss -tnlp | grep 5432`)

**自动化（pseudo）：**
```bash
export POSTGRES_PASSWORD=test
export ANTHROPIC_API_KEY=fake
export TAG=latest
docker compose -f butler-v5/docker-compose.yml up -d postgres butler
sleep 30
curl -sf http://127.0.0.1:3000/health | jq -e '.status == "ok"'
docker compose -f butler-v5/docker-compose.yml down -v
```

## Scenario DEP-HB-03: /health endpoint unit tests pass

**目的**：验证 T5 /health endpoint 实现正确

**步骤：**
1. `cd butler-v5 && pnpm test apps/api/src/routes/health.test.ts`

**验收：**
- 3 tests pass (combined /health + /health/live + db-down)

**自动化（pseudo）：**
```bash
cd butler-v5 && pnpm test apps/api/src/routes/health.test.ts 2>&1 | tail -10
# Expected: 3/3 passed
```

## Scenario DEP-HB-04: release workflow dry_run completes without push

**目的**：验证 release.yml workflow 配置合法（不实际 push 到 ghcr.io）

**前置条件：**
- GitHub repo 启用 Actions
- 用户有 Actions: workflow_dispatch 权限

**步骤：**
1. GitHub UI → Actions tab → Release workflow → Run workflow
2. 输入 tag=v5.0.0-dryrun + dry_run=true
3. 等 ~10min
4. 检查 build job 成功

**验收：**
- validate job: 成功（semver check pass）
- build job (matrix amd64 + arm64): 2/2 成功
- 无 push 到 ghcr.io（通过 dry_run=true 拦截）
- 无创建 GH release

**自动化（pseudo）：**
```bash
gh workflow run release.yml \
  --field tag=v5.0.0-dryrun \
  --field dry_run=true \
  --ref main
gh run watch <run-id> --exit-status
```

## Methodology Check: M15 — docker deploy artifacts 齐 + cross-link 一致

**目的**：验证 9 个 docker deploy artifacts 齐全 + cross-link 一致

**验收标准（全部满足）：**

1. **文件齐全（9 项）**：
   - `Dockerfile`
   - `.dockerignore`
   - `.github/workflows/release.yml`
   - `.github/dependabot.yml`
   - `butler-v5/docker-compose.yml` (含 butler service)
   - `butler-v5/apps/api/src/routes/health.ts`
   - `docs/deployment/production-hardening.md`
   - `docs/deployment/README.md`
   - `tests/acceptance/scenarios_docker_deploy.md`

2. **§20 KNOWN_ENTRY_POINTS 加 /health**：`routes/health.ts` 在 invariant 文档（NON_LLM_ENTRY_POINTS）

3. **AGENTS.md 加 production-hardening link**：`production-hardening` 命中

4. **Cross-link 一致**：production-hardening.md 含 SECURITY.md + v5-production-architecture 链接 + Secret<T> 指向真实 secret.ts（不是 dev-ops-tools-design.md）

5. **compose YAML 合法 + butler service 存在 + 全部 port 127.0.0.1**

**自动化（pseudo）：**
```bash
cd /home/ailearn/projects/WFXM

# 1. 文件齐全
for f in Dockerfile .dockerignore \
         .github/workflows/release.yml \
         .github/dependabot.yml \
         butler-v5/docker-compose.yml \
         butler-v5/apps/api/src/routes/health.ts \
         docs/deployment/production-hardening.md \
         docs/deployment/README.md \
         tests/acceptance/scenarios_docker_deploy.md; do
  [ -s "$f" ] || { echo "FAIL: missing $f"; exit 1; }
done

# 2. §20 update (NON_LLM_ENTRY_POINTS contains routes/health.ts)
grep -q "routes/health.ts" butler-v5/tests/architecture/section20-invariants*.test.ts \
  || { echo "FAIL: §20 NON_LLM_ENTRY_POINTS 未加 routes/health.ts"; exit 1; }

# 3. AGENTS.md link
grep -q "production-hardening" AGENTS.md || { echo "FAIL: AGENTS.md 未加 production-hardening link"; exit 1; }

# 4. Cross-link (Secret<T> -> real source)
grep -q "@butler/adapters/wechat/secret\.js" docs/deployment/production-hardening.md \
  || { echo "FAIL: hardening.md Secret<T> 链接错误"; exit 1; }
grep -q "SECURITY\.md\|v5-production-architecture" docs/deployment/production-hardening.md \
  || { echo "FAIL: hardening.md 缺 cross-link"; exit 1; }

# 5. compose YAML + butler service + loopback only
python3 -c "import yaml; yaml.safe_load(open('butler-v5/docker-compose.yml'))" \
  || { echo "FAIL: compose YAML"; exit 1; }
grep -q "^  butler:" butler-v5/docker-compose.yml || { echo "FAIL: butler service 缺失"; exit 1; }
grep -qE '"0\.0\.0\.0' butler-v5/docker-compose.yml \
  && { echo "FAIL: compose 含 0.0.0.0 binding"; exit 1; }

echo "✓ M15 PASS"
```

## 总结

- 4 acceptance scenarios (DEP-HB-01..04)
- 1 methodology check (M15)
- 与现有 acceptance harness 集成：`pnpm acceptance` 从 100·100 → **104·104** (+4 DEP scenarios)
- 与现有 methodology check 集成：`pnpm methodology` 从 14·14 → **15·15** (+1 M15)
