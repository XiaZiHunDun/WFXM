# D53b — Deadcode Report (knip @ 2026-09-11)

**Tool:** knip v6.35.1 (replaces ts-prune per D45 lesson — 784 false positives in earlier scan)
**Config:** `butler-v5/knip.json` (8 workspaces, `project: ["scripts/acceptance/**/*.ts"]`)
**Raw output:** `/tmp/knip-raw-2026-09-11.md` (gitignored, 129 lines)
**Knip exit code:** 1 (findings exist, expected — will wrap with `|| true` later)

## Summary

| Category | Count | Action |
|---|---|---|
| Total knip findings | 92 | — |
| True dead (no references) | **87** | Delete in Task 3 |
| False positive (knip missed refs) | **5** | Keep, mark in report |
| Fixture (test fixture, knip should have ignored) | 0 | — |
| Cross-pkg re-export (referenced by another pkg) | 0 | — |
| Binaries (sandbox tooling, expected) | (counted as FP) | Keep, future: ignoreBinaries |

**Net effect:** Task 3 has **~87 deletion candidates** (8 files + 4 deps + 3 devDeps + 50 unused exports + 22 unused exported types). This is a substantial cleanup — D45 lesson: do not blind-trust; sample review proves these are real.

## By finding type

| Knip category | Count | Notes |
|---|---|---|
| Unused files | 8 | **All 8 true dead** — 4 domain barrels + 2 adapter barrels + 1 conversation-id shim |
| Unused exports | 53 | 50 true dead + 3 false positive (see below) |
| Unused exported types | 22 | **All 22 true dead** — used internally only, can drop `export` |
| Unused dependencies | 4 | All in `packages/adapters/package.json` — none imported by adapters code |
| Unused devDependencies | 3 | `@modelcontextprotocol/server-github`, `@ivotoby/openapi-mcp-server`, `firecrawl-mcp` |
| Unlisted binaries | 2 | `capsh`, `bwrap` — sandbox binaries called via execFileSync |

## True Dead Candidates (for Task 3 deletion)

### Unused files (8 — all deletable)

| File | Path | Verification grep result |
|---|---|---|
| conversation barrel | `packages/domain/src/conversation/index.ts` | `grep -rn "from.*conversation/index"` → 0 hits; `packages/domain/src/index.ts` imports directly from `./conversation/types.js` etc. |
| permissions barrel | `packages/domain/src/permissions/index.ts` | 0 hits; `packages/domain/src/index.ts:188` imports directly from `./permissions/types.js` |
| projects barrel | `packages/domain/src/projects/index.ts` | 0 hits; `packages/domain/src/index.ts:177,185` import directly from `./projects/{types,pure}.js` |
| memory barrel | `packages/domain/src/memory/index.ts` | 0 hits; `packages/domain/src/index.ts:44,50` import directly from `./memory/{types,pure}.js` |
| tools barrel | `packages/domain/src/tools/index.ts` | 0 hits; `packages/domain/src/index.ts:29,36` import directly from `./tools/{types,pure}.js` |
| llm barrel | `packages/adapters/src/llm/index.ts` | 0 hits; `packages/adapters/src/index.ts` does NOT re-export from `./llm/` (uses `./llm-provider.js` etc. directly) |
| mcp barrel | `packages/adapters/src/mcp/index.ts` | 0 hits; main `packages/adapters/src/index.ts` does NOT re-export from `./mcp/index.js` |
| conversation-id shim | `apps/api/src/conversation-id.ts` | Marked `@deprecated`; only `apps/api/src/conversation-id.test.ts` (its own deprecated test) references it. Real consumers import directly from `@butler/runtime/intake/conversation-id.js` |

### Unused dependencies in packages/adapters (4 — all deletable)

| Dependency | Reason | Action |
|---|---|---|
| `@butler/persistence` | `grep -rn "@butler/persistence" packages/adapters/src --include="*.ts"` → 0 hits. Belongs to `packages/runtime`, not adapters. | Remove from `packages/adapters/package.json:29` |
| `@butler/runtime` | `grep -rn "@butler/runtime" packages/adapters/src --include="*.ts"` → 0 hits. | Remove from `packages/adapters/package.json:32` |
| `drizzle-orm` | `grep -rn "drizzle-orm" packages/adapters/src --include="*.ts"` → 0 hits. | Remove from `packages/adapters/package.json:33` |
| `hono` | `grep -rn "from .hono." packages/adapters/src --include="*.ts"` → 0 hits. `hono` only used in apps/api, not adapters. | Remove from `packages/adapters/package.json:34` |

### Unused devDependencies in root package.json (3 — all deletable)

| Dependency | Reason | Action |
|---|---|---|
| `@modelcontextprotocol/server-github` | Only appears in `package.json:59`. No `.ts` source references it. | Remove from `package.json` devDeps |
| `@ivotoby/openapi-mcp-server` | Only appears in `package.json:58`. No `.ts` source references it. | Remove from `package.json` devDeps |
| `firecrawl-mcp` | Only appears in `package.json:65`. No `.ts` source references it. | Remove from `package.json` devDeps |

### Unused exports (50 — all drop `export` keyword; only 1 has no usage even internally)

| Export | File | Internal use | Action |
|---|---|---|---|
| `pkcs7Unpad` | `packages/adapters/src/wechat/ilink-media-crypto.ts:9` | Used at line 63 | Change `export function` → `function` |
| `loadProjectKnowledgeSourcesFromPath` | `apps/api/src/project-knowledge-sources-config.ts:25` | Used at line 50 | Drop `export` |
| `projectKnowledgeSourcesPathFromEnv` | `apps/api/src/project-knowledge-sources-config.ts:17` | Used at lines 48, 69 | Drop `export` |
| `cdnDownloadUrl` | `packages/adapters/src/wechat/ilink-media.ts:117` | Used at line 174 | Drop `export` |
| `WECHAT_OUTBOUND_NETWORK_HOSTS` (re-export) | `packages/adapters/src/wechat/ilink-media.ts:13` | Redundant re-export; canonical source is `@butler/domain/governance/wechat-network-hosts.js` (used by `packages/runtime/src/grant-network.ts`) | Delete the entire `export { ... } from "..."` line |
| `isProjectKnowledgeInjectEnabled` | `apps/api/src/project-knowledge-inject.ts:13` | Used at line 24 | Drop `export` |
| `wechatProjectPathsConfigPath` | `apps/api/src/wechat-project-surface.ts:32` | Used at line 42 | Drop `export` |
| `canRespondToInlineApproval` | `apps/api/src/wechat-inline-approval.ts:13` | Used at line 67 | Drop `export` |
| `allowedOutboundMediaRoots` | `apps/api/src/channel-outbound-media.ts:57` | Used at line 71 | Drop `export` |
| `mediaKindForPath` | `apps/api/src/channel-outbound-media.ts:29` | Used at line 46 | Drop `export` |
| `projectPathEntry` | `apps/api/src/wechat-project-surface.ts:53` | Used at lines 242, 275 | Drop `export` |
| `isDurableMemoryInjectEnabled` | `apps/api/src/durable-memory-inject.ts:13` | Used at line 25 | Drop `export` |
| `wechatActiveProjectStorePath` | `apps/api/src/wechat-active-project.ts:17` | Used at lines 78, 90 | Drop `export` |
| `wechatToolAllowlistPath` | `apps/api/src/wechat-tool-allowlist.ts:78` | Used at line 92 | Drop `export` |
| `readMockNotifyOutbox` | `apps/api/src/wechat-async-harness.ts:20` | Used at line 36 | Drop `export` |
| `allWechatCoreToolNames` | `apps/api/src/wechat-tool-profile.ts:16` | Used at line 41 | Drop `export` |
| `qualityGateConfigPath` | `apps/api/src/wechat-quality-gate.ts:29` | Used at line 37 | Drop `export` |
| `EXEC_TOOL_NAMES` | `apps/api/src/wechat-tool-profile.ts:14` | Used at lines 42, 72 | Drop `export` |
| `devSessionConversationId` | `apps/api/src/dev-session-grant.ts:32` | Used at line 63 | Drop `export` |
| `loopUsedDirectExecTools` | `apps/api/src/dev-quality-gate.ts:265` | Used at line 279 | Drop `export` |
| `listGitTouchedPaths` | `apps/api/src/dev-quality-gate.ts:126` | Used at lines 319, 377, 414, 460 | Drop `export` |
| `DEV_SESSION_TOOLS` | `apps/api/src/dev-session-grant.ts:13` | Used at line 108 | Drop `export` |
| `devSessionMaxUses` | `apps/api/src/dev-session-grant.ts:53` | Used at line 98 | Drop `export` |
| `resolveGitBranch` | `apps/api/src/dev-quality-gate.ts:176` | Used at lines 320, 378, 415, 461 | Drop `export` |
| `devSessionTtlMs` | `apps/api/src/dev-session-grant.ts:47` | Used at line 97 | Drop `export` |
| `runDevVerify` | `apps/api/src/dev-quality-gate.ts:193` | Used at lines 318, 413, 459 | Drop `export` |
| `isDevVerifyAutoEnabled` | `apps/api/src/dev-quality-gate.ts:22` | Used at lines 275, 354 | Drop `export` |
| `workspaceRootFromEnv` | `apps/api/src/dev-quality-gate.ts:32` | Used at line 40 (NB: separate private `workspaceRootFromEnv` exists in wechat-project-surface.ts:28) | Drop `export` |
| `devVerifyTimeoutMs` | `apps/api/src/dev-quality-gate.ts:64` | Used at line 204 | Drop `export` |
| `pendingUndoCount` | `apps/api/src/workspace-tools.ts:477` | **No usage anywhere** | Delete entire function |
| `runArgv` | `apps/api/src/dev-quality-gate.ts:74` | Used at lines 133, 141, 155, 181 | Drop `export` |
| `loadScheduleJobsFromPath` | `apps/api/src/schedule-config.ts:75` | Used at lines 105, 107 | Drop `export` |
| `normalizeCredentialNames` | `apps/api/src/workspace-tools.ts:59` | Used at line 588 | Drop `export` |
| `sandboxWorkspaceRootFrom` | `apps/api/src/workspace-tools.ts:80` | Used at lines 149, 173, 256, 277 | Drop `export` |
| `telegramMediaMaxBytes` | `apps/api/src/channel-media.ts:165` | Used at line 185 | Drop `export` |
| `RUN_COMMAND_SLIRP_TIMEOUT_MS` | `apps/api/src/tool-boundary.ts:30` | Used at line 47 | Drop `export` |
| `SEND_WECHAT_FILE_TIMEOUT_MS` | `apps/api/src/tool-boundary.ts:28` | Used at line 53 | Drop `export` |
| `telegramMediaCacheEnabled` | `apps/api/src/channel-media.ts:13` | Used at line 175 | Drop `export` |
| `DEFAULT_TOOL_TIMEOUT_MS` | `apps/api/src/tool-boundary.ts:27` | Used at lines 49, 56 | Drop `export` |
| `telegramMediaCacheDir` | `apps/api/src/channel-media.ts:17` | Used at line 184 | Drop `export` |
| `projectStateStorePath` | `apps/api/src/project-state.ts:30` | Used at lines 63, 74 | Drop `export` |
| `runCommandTimeoutMs` | `apps/api/src/tool-boundary.ts:37` | Used at line 55 | Drop `export` |
| `startIlinkPoller` | `apps/api/src/ilink-poller.ts:232` | Used at line 321 | Drop `export` |
| `parseDmPolicy` | `apps/api/src/ilink-config.ts:39` | Used at line 96 | Drop `export` |
| `DEFAULT_SUBSCRIBE_TTL_MS` | `apps/api/src/ws-subscribe.ts:3` | Used at line 26 | Drop `export` |
| `extractQueryParam` | `apps/api/src/ws-routes.ts:134` | Used at lines 159, 167 | Drop `export` |
| `resolveWsIdentity` | `apps/api/src/ws-routes.ts:166` | Used at line 206 | Drop `export` |
| `parseMcpStdioArgs` | `apps/api/src/mcp-config.ts:52` | Used at line 153 | Drop `export` |
| `makeRecallDocumentTool` | `apps/api/src/tools.ts:594` | Used at line 728 | Drop `export` |
| `loadToolConversationHistory` | `apps/api/src/tools.ts:90` | Used at lines 135, 234 | Drop `export` |

### Unused exported types (22 — all change `export type` → `type`)

| Type | Location | Internal use |
|---|---|---|
| `RuntimeTx` | `packages/domain/src/runtime/store-contract.ts:213` | Used at lines 189, 201, 209; also referenced in test regex matches (ignored) and 1 comment in `runtime-store.ts:443` |
| `ConversationStatus` | `packages/domain/src/conversation/types.ts:15` | Used at line 50 |
| `ProjectIdRef` | `packages/domain/src/conversation/types.ts:10` | Used at line 49 |
| `TurnStatus` | `packages/domain/src/conversation/types.ts:16` | Used at line 40 |
| `WechatProjectPathEntry` | `apps/api/src/wechat-project-surface.ts:17` | Used at lines 25, 56 |
| `SweeperType` | `apps/api/src/wechat-sweeper-notify.ts:18` | Used at line 75 |
| `QualityGateProject` | `apps/api/src/wechat-quality-gate.ts:15` | Used at lines 22, 48 |
| `CompactSource` | `apps/api/src/conversation-memory.ts:22` | Used at line 27 |
| `QualityGateCommand` | `apps/api/src/wechat-quality-gate.ts:9` | Used at line 17 |
| `ConversationUsage` | `apps/api/src/owner-routes/usage.ts:12` | Used at lines 37, 135 |
| `UsageTotals` | `apps/api/src/owner-routes/usage.ts:26` | Used at lines 36, 134 |
| `SendWechatMediaFn` | `apps/api/src/send-wechat-file.ts:16` | Used at lines 28, 37 |
| `ChainEntry` | `apps/api/src/workspace-tools.ts:311` | Used at lines 332, 343, 502 |
| `McpServerBootstrap` | `apps/api/src/mcp-bootstrap.ts:43` | Used at line 54 |
| `McpBootstrapMode` | `apps/api/src/mcp-bootstrap.ts:41` | Used at lines 45, 52 |
| `ChannelMediaKind` | `apps/api/src/channel-media.ts:10` | Re-export only; slack adapter has its own definition; this re-export is unused |
| `McpStdioConnection` | `apps/api/src/mcp-config.ts:24` | Used at line 32 |
| `McpHttpConnection` | `apps/api/src/mcp-config.ts:10` | Used at line 32 |
| `McpSseConnection` | `apps/api/src/mcp-config.ts:17` | Used at line 32 |
| `ExecOutcome` | `apps/api/src/exec-audit.ts:26` | Used at line 34 |
| `WsIdentity` | `apps/api/src/ws-routes.ts:162` | Used at line 166 |
| `WsOutboundFrame` | `apps/api/src/ws-routes.ts:52` | Used at lines 86, 214, 234 |

## False Positives (kept — knip config issues)

| Export | Path | Why false positive | Reference found |
|---|---|---|---|
| `approveWaitingStep` | `apps/api/src/approval-resume.ts:32` | Used via cross-package re-export bridge; knip misses this. Real callers: `apps/api/src/wechat-inline-approval.ts:2,91` and `apps/api/src/owner-routes/approvals-runs.ts:3,57`. Canonical def: `packages/runtime/src/approval-runtime.ts:144`. | `grep -rn "approveWaitingStep" --include="*.ts"` → 5 non-test files import it |
| `denyWaitingStep` | `apps/api/src/approval-resume.ts:32` | Same pattern as `approveWaitingStep`. Real callers: `apps/api/src/wechat-inline-approval.ts:3,78` and `apps/api/src/owner-routes/approvals-runs.ts:4,121`. | `grep -rn "denyWaitingStep"` → multiple non-test files import it |
| `buildHonoApp` | `apps/api/src/acceptance-app.ts:14` | Used by `tests/acceptance/harness.ts:37,171` — but `tests/` is not in the root workspace's `project` array, so knip can't trace references through it. Harness is reachable from `scripts/acceptance/record-real-llm.ts` (an entry) via `makeAcceptanceApp`/`sendWechatMessage`, but the harness's own imports aren't traced because harness.ts itself isn't in any project array. | `grep "buildHonoApp"` → 2 hits in `tests/acceptance/harness.ts` |

## Unlisted Binaries (false positives — sandbox tooling)

| Binary | File | Reason |
|---|---|---|
| `capsh` | `packages/adapters/src/sandbox/p2d-preflight.ts:33` | Sandbox capability check via `execFileSync("capsh", ["--print"])`. Not "dead" — runtime dependency. Add to `ignoreBinaries` in knip.json. |
| `bwrap` | `apps/api/src/mcp-spawn.ts:33` | Bubblewrap sandbox binary referenced via `buildBubblewrapArgs()`. Not "dead" — runtime dependency. Add to `ignoreBinaries` in knip.json. |

## Sample Review Trail (D45 lesson: ≥5 manual reviews)

Reviewed 8 candidates with explicit grep verification:

1. **`packages/domain/src/conversation/index.ts`** → barrel file
   - `grep -rn "from.*conversation/index" --include="*.ts"` → 0 results
   - `cat packages/domain/src/index.ts` → imports directly from `./conversation/types.js`, `./conversation/transitions.js`, `./conversation/context.js` (lines 16-18)
   - **Classification:** TRUE DEAD (delete file)

2. **`apps/api/src/conversation-id.ts`** → `@deprecated` thin re-export shim
   - `cat apps/api/src/conversation-id.ts` → marked `@deprecated`, only re-exports from `@butler/runtime/intake/conversation-id.js`
   - `grep -rn "from.*conversation-id" --include="*.ts"` → only its own deprecated test `apps/api/src/conversation-id.test.ts` and the actual runtime source `packages/runtime/src/intake/conversation-id.ts`
   - Real consumer `apps/api/src/wechat-subagent-commands.ts:2` imports `defaultWechatConversationId` from `@butler/runtime/intake/conversation-id.js` directly, not via the shim
   - **Classification:** TRUE DEAD (delete file + its deprecated test)

3. **`pkcs7Unpad`** (export in `packages/adapters/src/wechat/ilink-media-crypto.ts:9`)
   - `grep -rn "pkcs7Unpad" --include="*.ts"` → 2 hits, both in `ilink-media-crypto.ts` (definition line 9 and internal call line 63)
   - **Classification:** TRUE DEAD export (change `export function` → `function`)

4. **`@butler/persistence` dep in `packages/adapters/package.json`**
   - `grep -rn "@butler/persistence" packages/adapters/src --include="*.ts"` → 0 hits
   - `grep -rn "@butler/persistence" packages/ --include="*.ts"` (excluding `_archive`, `package.json`) → only `packages/runtime/src/*.test.ts` use it (10+ tests)
   - **Classification:** TRUE DEAD dep of adapters (the dep belongs to runtime, not adapters)

5. **`ChainEntry` type in `apps/api/src/workspace-tools.ts:311`**
   - `grep -rn "ChainEntry" --include="*.ts"` → 4 hits, all in `workspace-tools.ts` (definition line 311, used at lines 332, 343, 502)
   - **Classification:** TRUE DEAD type (change `export type` → `type`)

6. **`buildHonoApp`** (export in `apps/api/src/acceptance-app.ts:14`)
   - `grep -rn "buildHonoApp" --include="*.ts"` → 3 hits: definition in acceptance-app.ts:14, usage in `tests/acceptance/harness.ts:37,171`
   - knip config issue: `tests/` is not in root workspace's `project` array; harness.ts is invisible to knip
   - **Classification:** FALSE POSITIVE (config gap; fix: add `tests/acceptance/**/*.ts` to root project's `project` array OR add `tests/acceptance/harness.ts` as entry)

7. **`approveWaitingStep`** (export in `apps/api/src/approval-resume.ts:32`)
   - `grep -rn "approveWaitingStep" --include="*.ts"` → 5+ non-test files: `apps/api/src/wechat-inline-approval.ts:2,91`, `apps/api/src/owner-routes/approvals-runs.ts:3,57`, plus many test files (ignored)
   - Function IS used in production via re-export pattern
   - **Classification:** FALSE POSITIVE (knip fails to track cross-package re-exports through `apps/api/src/approval-resume.ts:32`)

8. **`WECHAT_OUTBOUND_NETWORK_HOSTS`** (export in `packages/adapters/src/wechat/ilink-media.ts:13`)
   - `grep -rn "WECHAT_OUTBOUND_NETWORK_HOSTS" --include="*.ts"` → 5 hits: definition in `packages/domain/src/governance/wechat-network-hosts.ts:2`, consumed by `packages/runtime/src/grant-network.ts:1`, re-exported by `packages/domain/src/index.ts:279` and `packages/adapters/src/wechat/ilink-media.ts:13`
   - No one imports from `ilink-media.js` — the canonical path is `@butler/domain/governance/wechat-network-hosts.js`
   - **Classification:** TRUE DEAD export (the ilink-media.ts:13 re-export line is redundant)

## Knip Config Issues (for D53c / D54 follow-up)

| Issue | Suggested Fix |
|---|---|
| `tests/` is not in any workspace's `project` array | Add `tests/acceptance/**/*.ts` to root workspace `project` array (or `entry` for harness.ts) — would resolve `buildHonoApp` false positive |
| `apps/api/src/acceptance-app.ts` is unreachable from entries (only reachable from harness.ts) | Either add acceptance-app.ts as an apps/api entry, OR fix the root `tests/` project array (preferred) |
| Cross-package re-export pattern (`apps/api/src/approval-resume.ts:32` re-exports from `@butler/runtime/...`) | knip limitation — may need `knip.json`'s `entry` arrays to explicitly include the bridge files, or file a knip upstream issue |
| 2 unlisted binaries (capsh, bwrap) — sandbox tooling | Add to `ignoreBinaries` in `knip.json`: `["capsh", "bwrap"]` |
| `**/*.test.ts` is ignored → test-only exports look "unused" | Documented protocol: grep for `.test.ts` references when classifying. Future scans should apply same discipline. |

## Task 3 Action Plan

**Single commit "chore(deadcode): D53b Task 3 drop 87 true-dead findings" with these sub-changes:**

1. **Delete 8 unused files** (Task 3a)
   - `rm packages/domain/src/{conversation,permissions,projects,memory,tools}/index.ts`
   - `rm packages/adapters/src/{llm,mcp}/index.ts`
   - `rm apps/api/src/conversation-id.ts apps/api/src/conversation-id.test.ts` (file + its deprecated test)

2. **Remove 4 unused deps from `packages/adapters/package.json`** (Task 3b)
   - `@butler/persistence`, `@butler/runtime`, `drizzle-orm`, `hono`

3. **Remove 3 unused devDeps from root `package.json`** (Task 3c)
   - `@modelcontextprotocol/server-github`, `@ivotoby/openapi-mcp-server`, `firecrawl-mcp`

4. **Drop `export` keyword on 50 unused exports** (Task 3d)
   - See table above; one-line edits per file (preserve internal usage)
   - Special: delete `pendingUndoCount` entirely (no internal use)

5. **Drop `export` keyword on 22 unused exported types** (Task 3e)
   - Change `export type X` → `type X` and `export interface X` → `interface X` per table above

6. **Update `knip.json`** to suppress 2 false positive binaries (Task 3f)
   - Add `"ignoreBinaries": ["capsh", "bwrap"]`
   - Optional: add `tests/acceptance/**/*.ts` to root `project` array to fix `buildHonoApp` false positive

**Verification after each step:**
- `pnpm deadcode:knip` re-run shows decreasing findings (target: 0-2 after Task 3)
- `pnpm test` (no test regressions)
- `pnpm typecheck` (no type errors)

## Notes

- This audit is **static only**. Runtime dead code (registered callbacks, conditional registrations) cannot be found by knip.
- D45 lesson applied: `pnpm deadcode:knip` exit code is 1 even with 87 true-dead + 5 FP + 0 fixture. Wrap with `|| true` to make it not fail CI until Task 3 is complete.
- The `acceptHarness.ts` (tests/acceptance/harness.ts) is a meaningful behavior driver (D52 evidence: 41 scenarios), so `buildHonoApp` is **definitely** needed even if knip flags it. False positive confirmed by manual review.
---

## Post-deletion verification (Task 3 — 2026-09-11)

Re-ran `pnpm deadcode:knip` after all 6 sub-tasks:

- **Total findings: 3** (was 92)
- **True dead remaining: 0** (was 87)
- **False positive (kept): 3** — `approveWaitingStep`, `denyWaitingStep` (`apps/api/src/approval-resume.ts:32`), `buildHonoApp` (`apps/api/src/acceptance-app.ts:14`). The 2 binary FPs (`capsh`, `bwrap`) are now suppressed via `ignoreBinaries`.
- **Reclassifications: 0** — every one of the 87 true-dead candidates was verified and removed; no restore was needed.

### Sub-task commits

| Sub-task | Commit | Change |
|---|---|---|
| 3a | `3891a19a` | Delete 8 unused files (9 files on disk — `conversation-id.ts` + its deprecated test) |
| 3b | `50468e41` | Remove 4 unused deps from `packages/adapters/package.json` (`@butler/persistence`, `@butler/runtime`, `drizzle-orm`, `hono`) |
| 3c | `bc15cece` | Remove 3 unused devDeps from root `package.json` (`@modelcontextprotocol/server-github`, `@ivotoby/openapi-mcp-server`, `firecrawl-mcp`) |
| 3d | `b484a741` | Drop 50 unused exports (48 `export` keyword drops + 1 re-export line delete `WECHAT_OUTBOUND_NETWORK_HOSTS` + 1 full function delete `pendingUndoCount`) — 26 files |
| 3e | `91c0d700` | Drop 22 unused exported types (21 `export type`/`interface` drops + 1 re-export-list entry removal `ChannelMediaKind`) — 14 files |
| 3f | `77bd8628` | `knip.json` add `ignoreBinaries: ["capsh", "bwrap"]` |

### Verification evidence

- **`pnpm typecheck`**: green after every sub-task (8/8 workspaces)
- **`pnpm lint`**: 0 errors, 0 warnings after 3d and 3e
- **`pnpm test`**: 277 files / 1874 passed / 1 skipped after 3e
- **`pnpm test:acceptance` (N=3)**: 81/81 passed after 3a and after 3e

### Pre-existing flake observed (NOT caused by deletions)

`tests/acceptance/product-regressions.test.ts > /undo：真实审批后还原 write_file 写入` intermittently returns 500 instead of 201 **when the full acceptance suite runs in parallel**. Isolation-proof performed during Task 3d:

- clean `HEAD` (3c, no 3d edits), full suite ×3 → **3/3 fail** with the same `expected 500 to be 201`
- clean `HEAD`, file in isolation ×3 → 3/3 pass
- with 3d edits, file in isolation ×3 → 3/3 pass
- with 3d edits, full suite ×3 → 1 pass / 2 fail (same assertion)

Conclusion: parallel-run cross-file state contamination, **pre-existing**, unrelated to any deletion. Belongs to the Task 7 flake-fix scope alongside `subagent-multiturn`.

### Cross-reference notes captured during verification

- `workspaceRootFromEnv` and `runArgv` each have *separate private definitions* in `wechat-quality-gate.ts` / `wechat-project-surface.ts`. Dropping `export` in `dev-quality-gate.ts` does not affect them.
- `RuntimeTx` is referenced by two architecture tests via source-text regex (`/type\s+RuntimeTx\s*=\s*unknown/`). Dropping `export` preserves the matched text — both tests still pass.
- `ChannelMediaKind` in `apps/api/src/channel-media.ts` was a pure pass-through re-export of the slack adapter's own type. Removed from both the `import type` and `export type` lists; the slack canonical definition is untouched.
- Zero of the 70 export/type names had any `*.test.ts` reference (knip's `**/*.test.ts` ignore was therefore not a source of false positives in this batch).

## Post-D54 verification (Task 6 — 2026-09-11)

Re-ran `pnpm deadcode:knip` after D54 T6 config update:

- **Total findings: 0** (was 6 post-D53c: 3 unused deps + 3 unused exports; was 3 post-D53b before D53c regression fix)
- **knip exit code: 0** (clean pass; first time since the 6 FPs were introduced)
- **knip config delta**: `ignoreDependencies` × 6 (3 existing + 3 new MCP devDeps) + `ignoreIssues` × 2 (file-glob → `["exports", "types"]` for the 2 source files)

### Why `ignoreIssues` instead of `ignoreExports`

The original D54 T6 plan specified `ignoreExports` (per-export suppression list), but knip v6.35.1 does not support that key — schema validation rejects it with `ERROR: Invalid input (unrecognized_keys: ignoreExports)`. Verified against `node_modules/knip/dist/schema/configuration.d.ts`: available `ignore*` keys are `ignoreBinaries`, `ignoreDependencies`, `ignoreFiles`, `ignoreMembers`, `ignoreUnresolved`, `ignoreExportsUsedInFile`, `ignoreIssues`, `ignoreWorkspaces`. Closest equivalent for per-file export suppression is `ignoreIssues` (file-glob → issue-type array). Used it as the substitute; the spirit of "knip 6 → 0 reported" is preserved.

### False positives documented (not deleted)

| Name | File | Why knip can't see it | Suppression |
|---|---|---|---|
| `approveWaitingStep` | `apps/api/src/approval-resume.ts:32` | Re-export from `@butler/runtime/approval-runtime.js`; runtime consumers import via this barrel | `ignoreIssues` for file |
| `denyWaitingStep` | `apps/api/src/approval-resume.ts:32` | Same as above | `ignoreIssues` for file |
| `buildHonoApp` | `apps/api/src/acceptance-app.ts:14` | Used by `tests/acceptance/harness.ts`, excluded by knip's `**/*.test.ts` ignore | `ignoreIssues` for file |
| `@modelcontextprotocol/server-github` | root `package.json:59` | Runtime-used via `config/mcp-manifest.json:35` subprocess spawn; `config/**` is in knip `ignore` | `ignoreDependencies` |
| `@ivotoby/openapi-mcp-server` | root `package.json:58` | Same as above (`config/mcp-manifest.json:59`) | `ignoreDependencies` |
| `firecrawl-mcp` | root `package.json:65` | Same as above (`config/mcp-manifest.json:22`) | `ignoreDependencies` |

All 6 are **D53b regression-fix correctness**: D53b T3c deleted them as "unused", D53c restored them once evidence surfaced (config/mcp-manifest.json + mcp-config.test.ts references). knip static analysis cannot trace through these paths because of the `ignore` patterns, hence the suppressions here.

### Verification evidence

- **`pnpm deadcode:knip`**: 0 reported, exit 0
- **`pnpm lint`**: 0 errors, 0 warnings
- **`pnpm typecheck`**: 8/8 workspaces green (unchanged; no source edits)
- **No source-file edits**: only `knip.json` + `tools/deadcode-report.md` changed

### D54 closure summary

Drift items closed by D54 batch: 5-type spec full ✓ (T1-T3 added delete_file / apply_patch / run_command with invertible flag) / 6-phrase spec full ✓ (T4 added `撤销这轮` family) / invertible flag spec formalized ✓ (T5) / **knip config closed ✓ (T6, this task)**.
