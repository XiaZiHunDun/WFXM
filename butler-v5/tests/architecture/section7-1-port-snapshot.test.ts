/**
 * Arch guard (D37-arch-align §7.1 Port snapshot refresh): lock the
 * §7.1 2026-08-31 snapshot refresh against implementation drift.
 *
 *   §7.1 已实施 Port 状态（2026-08-31 snapshot）— line 307
 *
 * Refresh summary (D37, 2026-08-31):
 *
 *   - Date: 2026-08-29 → 2026-08-31
 *   - Added 3 窄接口 Port rows: Outbox / Snapshot / Projection
 *     (per `packages/ports/src/index.ts` header comment "v5 物化的
 *     6 个 Core Port" — previously only 4 Port rows present).
 *   - Event Store row: old `EventStoreService` (R2 宽 Tag) row
 *     description updated from "尚由 postgres-event-store 引用，待迁"
 *     to "已归档（commit `33af1722` 2026-08-28），prod runtime 不经
 *     Tag 注入面".
 *   - Channel row: ✅ → 🟡 (channel.ts interface 已实装; wechat
 *     adapter 线上; slack adapter skeleton 等真接生产触发; telegram
 *     未触发) — per `port-catalog.md` §3 + DESIGN §18 条件准入.
 *   - v5 Ports 总入口 row: 补 r2-shim 说明（thin barrel + fixture-only
 *     shim; prod v5 code 不得引; invariant 16 由
 *     package-membership.test.ts 锁）.
 *
 * Drift acknowledged:
 *
 *   - §7.1 Channel row 之前误列 ✅ 与 port-catalog.md §3 "待物化"
 *     冲突; 本 batch 改 🟡 修正, 与 DESIGN §18 条件准入 + Slack R14
 *     "structural alignment only" owner dialog 后再补 一致.
 *   - 6 v5 物化 Core Port 与 `packages/ports/src/index.ts` 头部注释
 *     一致, 但 §7.1 表之前只列 4 Port (Clock / Credential Provider /
 *     Event Store / Channel) — 本 batch 补 3 行 (Outbox / Snapshot /
 *     Projection), 与 `port-catalog.md` §1 同步.
 *
 * Static checks (no runtime):
 *   - C11 — production v5 code 不 import `@butler/ports/r2-shim`
 *           (r2-shim 仅 `_archive/packages/**` fixture 用, 包成员守卫
 *           由 `package-membership.test.ts` invariant 16 锁).
 *   - C12 — 6 v5 物化 Core Port 文件在 `packages/ports/src/core/` 存在:
 *           clock.ts / credential-provider.ts / event-store.ts /
 *           outbox.ts / snapshot.ts / projection.ts.
 *   - C13 — wechat 是唯一线上 ChannelPort impl (D38 closure):
 *           packages/adapters/src/wechat/channel-port.ts 存在;
 *           packages/adapters/src/slack/ 存在但不含 channel-port.ts
 *           (slack skeleton 不实现 ChannelPort 接口, 等真接生产触发).
 *           与 port-catalog.md §3 + DESIGN §7.1 🟡 同步.
 *
 * Runtime behavior is verified by:
 *   - D31 §7 main guards (thin barrel + 0 impl + 0 upward imports)
 *   - D32 §17.1 monorepo (Core 不反向依赖 adapters)
 *   - existing port unit tests (clock.test / outbox.test /
 *     snapshot.test / projection.test / channel.test /
 *     credential-provider)
 *
 * Remediation when guards fire:
 *   - production 引 r2-shim → §7.1 + invariant 16 违规; 改 import 到
 *     `@butler/ports/core/*` 物化 Port.
 *   - 物化 Port 文件缺失 → §7.1 实证失败; 恢复文件 + 同步 index.ts
 *     barrel re-export.
 */

import { describe, expect, it } from "vitest"
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"

const REPO_ROOT = join(__dirname, "../../..")
const BUTLER_V5 = join(REPO_ROOT, "butler-v5")
const PACKAGES_SRC = join(BUTLER_V5, "packages")
const CORE_DIR = join(PACKAGES_SRC, "ports/src/core")

function listTsFiles(dir: string): string[] {
  const out: string[] = []
  if (!existsSync(dir)) return out
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry)
    const stat = statSync(path)
    if (stat.isDirectory()) {
      if (entry === "node_modules" || entry === "dist" || entry === "coverage" || entry === "_archive") continue
      out.push(...listTsFiles(path))
    } else if (entry.endsWith(".ts")) {
      out.push(path)
    }
  }
  return out
}

describe("§7.1 Port snapshot refresh (D37, 2026-08-31)", () => {
  // C11 — production v5 code 不 import `@butler/ports/r2-shim`。
  // r2-shim.ts 是 fixture-only shim，仅 `_archive/packages/**` mock
  // 用；production code 引它会重新引入 R2 Effect Tag 注入面（DESIGN
  // §7 + invariant 16 共同违规）。
  it("production v5 code does not import @butler/ports/r2-shim (§7.1 + invariant 16)", () => {
    const FORBIDDEN = /from\s+["']@butler\/ports\/r2-shim["']|require\(["']@butler\/ports\/r2-shim["']\)/
    const candidateDirs = [
      join(PACKAGES_SRC, "domain/src"),
      join(PACKAGES_SRC, "runtime/src"),
      join(PACKAGES_SRC, "ports/src"),
      join(BUTLER_V5, "apps"),
      join(BUTLER_V5, "cli"),
    ].filter(existsSync)
    const violations: string[] = []
    for (const d of candidateDirs) {
      for (const f of listTsFiles(d)) {
        // 排除 r2-shim 自身（它是 shim 不是 consumer）
        if (f.endsWith("r2-shim.ts")) continue
        const src = readFileSync(f, "utf8")
        if (FORBIDDEN.test(src)) violations.push(f)
      }
    }
    expect(violations).toEqual([])
  })

  // C12 — §7.1 实证：8 v5 物化 Core Port 文件存在于
  //  `packages/ports/src/core/`（与 `ports/src/index.ts` 头部注释
  // "v5 物化的 8 个 Core Port" + `port-catalog.md` §1 同步；D44 加
  // Model Port，D46 加 Repository Port）。
  it("8 v5 物化 Core Port files exist (§7.1 + ports/src/index.ts header)", () => {
    const required = [
      "clock.ts",
      "credential-provider.ts",
      "model-port.ts",
      "repository.ts",
      "event-store.ts",
      "outbox.ts",
      "snapshot.ts",
      "projection.ts",
    ]
    const missing = required.filter((f) => !existsSync(join(CORE_DIR, f)))
    expect(missing).toEqual([])
  })

  // C13 — §7.1 + port-catalog.md §3 Channel Port 行 closure（D38）：
  // wechat 是唯一实现 ChannelPort 接口的线上 adapter；
  // slack adapter skeleton 就位但不实现 ChannelPort 接口。
  it("ChannelPort online impl is wechat-only; slack skeleton does not impl ChannelPort (§7.1 + port-catalog §3)", () => {
    const ADAPTERS_SRC = join(BUTLER_V5, "packages/adapters/src")
    // wechat 必须实现
    expect(existsSync(join(ADAPTERS_SRC, "wechat/channel-port.ts"))).toBe(true)
    // slack skeleton 存在但不实现 channel-port
    expect(existsSync(join(ADAPTERS_SRC, "slack"))).toBe(true)
    expect(existsSync(join(ADAPTERS_SRC, "slack/channel-port.ts"))).toBe(false)
  })
})