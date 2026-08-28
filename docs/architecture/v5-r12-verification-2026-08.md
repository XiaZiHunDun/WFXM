# v5 R12 port migration — host-side verification (2026-08-28)

Operator 在 **host terminal**（非 AI 沙箱）跑下列命令，验证 R12 commit `620e7514` 落地 + PRD §9 全闭环。

## 0. Pull & 验证 HEAD

```bash
cd /home/ailearn/projects/WFXM/butler-v5
git pull
git log --oneline -2
# 期望：HEAD = 620e7514 docs(v5): R12 doc sync — port-catalog + DESIGN §7.1 reflects thin-barrel state
```

## 1. 5-gate 复核（与 AI 沙箱一致基线）

```bash
CI= pnpm typecheck                       # 期望 0 错 (10/10 包)
CI= pnpm lint                           # 期望 0 警告 (--max-warnings 0)
CI= pnpm test                           # 期望 182 files / 1008 pass / 1 skip / 0 fail
CI= pnpm test:archived                  # 期望 18 files / 81 pass / 2 fail（pre-existing archive rot in `run-loop.test.ts`，与 R12 无关）
```

任何一项偏离上面基线 → 报告 `[FAIL] <gate>` + 输出末尾 30 行。

## 2. 真路径 smoke（PRD §9 验收条款）

```bash
pnpm smoke:prod-tune                    # 期望 PASS（基线已绿）
pnpm smoke:allowlist-owner              # 期望 PASS（owner 路径真实跑）
```

## 3. 报告格式

成功：回 `R12 verified`。  
失败：贴 `[FAIL] <gate-or-smoke>` 与 tail 输出（<80 行）。

## 已知 baseline 偏差

- `pnpm smoke:allowlist-slirp`：host 端通常可通（slirp4netns + unshare `-U -r`）；若 host 内核仍拒 `unshare` 写 `/proc/<uid_map>`，记录 `[env-blocked]` 不算 fail。
- `pnpm smoke:scheme-b-allowlist`：live LLM 方差，fixture 模式下 3/3 PASS（per state.md 2026-08-27）。
- `db-open.test.ts` 真实 PG：沙箱 CI 库不可达，需 `CI= pnpm test` 跳过（无 PG 服务）。

## 通过后的下一题

R12 verified → PRD §9 闭环（生产 runtime 1008/1/0 全绿；archived 2 pre-existing fail 视 operator 接受度，可后续单独 session 修）。下一题候选：
1. Channel Port trigger-day ADR (Path C, Slack/Telegram 真接生产时开)
2. Model Port 立项 (多 Provider 记账/协议统一需求真出现时)
3. R12 之外的 archived 债清理（修 `_archive/packages/application/_archive/run-loop/` 的 mock 预期，或 Effect v3.x 版本固定）
4. 新能力 / 修 bug
