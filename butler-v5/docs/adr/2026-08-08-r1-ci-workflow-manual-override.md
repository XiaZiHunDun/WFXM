# Manual Override: Butler v5 CI 工作流同步

- Status: Pending Owner manual override
- Date: 2026-08-08
- Scope: `butler-v5/.github/workflows/ci.yml` 的 gate 与 Postgres CI 配置
- Related: Task 11 of `docs/superpowers/plans/2026-08-08-wfxm-v5-replacement-implementation-plan.md`

## 背景与受保护原因

Task 11 原计划要求同步 CI 工作流，但 Implementer 不得直接改动该文件。`butler-v5/.butler/scope-boundaries.json` 的 `off_limits` 明确列出 `.github/workflows/*`；`AGENTS.md` 同时要求遵循四栏 Scope 边界，受保护文件只能由 Owner manual override。

GitHub Actions workflow 会决定远端安装、类型检查、门禁和测试的执行顺序。自动修改可能绕过现有守卫，或在工作流尚未由 Owner 复核时改变提交门槛。因此本任务只提交操作说明，不修改 `ci.yml`，也不将任何既有 WIP 纳入提交。

当前文件状态核对如下：

- `test` job 仍使用 `pnpm test -- --coverage`，需要 Owner 替换为 `pnpm gate`；
- `lint-and-typecheck` job 当前已有 `bash scripts/typecheck-gate.sh`，Owner 应确认该步骤只保留一处；
- Postgres service 当前为 `postgres:16-alpine`，Owner 应在手动复核时确认版本保持一致。

## 建议修改内容

### 1. `test` job 的测试命令

把 `ci.yml` 中 `test` job 的原有命令：

```yaml
- run: pnpm test -- --coverage
```

改为以下内容（原计划要求的变更原文）：

```yaml
- run: pnpm gate
```

### 2. `lint-and-typecheck` job 的类型检查门禁

在 `lint-and-typecheck` job 增加以下步骤（原计划要求的变更原文）：

```yaml
- run: bash scripts/typecheck-gate.sh
```

如果该步骤已经存在，不要重复添加；应保留一次，并确认其位于依赖安装之后、job 结束之前。该 job 的 Postgres service 不需要重复声明，仍应使用：

```yaml
image: postgres:16-alpine
```

## Owner 操作步骤

1. 复核 `/home/ailearn/projects/WFXM/butler-v5/.butler/scope-boundaries.json`，确认本次操作属于 `.github/workflows/*` 的 manual override。
2. 打开 `/home/ailearn/projects/WFXM/butler-v5/.github/workflows/ci.yml`，先保存当前版本并检查 diff 基线。
3. 在 `test` job 中将 `pnpm test -- --coverage` 替换为 `pnpm gate`。
4. 在 `lint-and-typecheck` job 中确认 `bash scripts/typecheck-gate.sh` 恰好执行一次；当前已有该行时不再新增副本。
5. 确认 Postgres service 使用 `postgres:16-alpine`，并保留现有健康检查与测试环境变量。
6. 在本地执行下列干跑；Implementer 不代替 Owner 执行这些命令：

```bash
docker compose -f /home/ailearn/projects/WFXM/butler-v5/docker-compose.yml up -d postgres
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 test
docker compose -f /home/ailearn/projects/WFXM/butler-v5/docker-compose.yml down
```

7. 复核 workflow diff 和下节验证命令；如需提交，使用包含 `[MANUAL-OVERRIDE]` 的 Owner commit message。

## 验证命令与期望输出

Owner 完成修改后运行：

```bash
git -C /home/ailearn/projects/WFXM diff --check -- butler-v5/.github/workflows/ci.yml
git -C /home/ailearn/projects/WFXM diff -- butler-v5/.github/workflows/ci.yml
```

期望结果：diff 无空白错误，并且只包含上述两处 gate 变更；Postgres 版本仍为 `16-alpine`。

本地干跑的 `pnpm test` 应以退出码 0 完成，Vitest 测试通过；随后 `docker compose ... down` 应成功清理 Postgres service。Owner 还应在提交前运行：

```bash
pnpm --dir /home/ailearn/projects/WFXM/butler-v5 gate
```

期望输出为 format check、typecheck、lint、coverage test 和 `typecheck-gate.sh` 全部退出码 0。GitHub Actions 的 `lint-and-typecheck` 与 `test` 两个 job 随后应均为绿色。

## 当前已知风险

- 若 Prettier 或 lint 在本地未先修复，失败会传递给 CI；切换至 `pnpm gate` 后，`test` job 会直接因这些检查失败而阻断。
- 本次实现不修改 workflow，Owner 未完成 manual override 前，远端仍会执行旧的 `pnpm test -- --coverage`。
- 本地 5432 端口被其他 Postgres 占用、或 Docker daemon 不可用时，干跑无法提供有效证据；应记录失败原因并在环境可用后重试。
- `pnpm gate` 与 lint job 中的 `typecheck-gate.sh` 可能各执行一次同一门禁，增加少量 CI 时长，但不改变校验结果。

## 交付边界

本文档不执行 Docker、pnpm install、pnpm test 或 git add/commit，不修改 `ci.yml`，不修改任何既有 WIP。最终纳入 CI 的变更由 Owner 复核、手动写入并决定提交。
