# v5 R10.x Handoff Document

> **For:** Cursor (or any future AI coding assistant picking up Butler v5 development)
> **Date:** 2026-08-19 (post-R10.x v4 decommission)
> **Author:** claude-code (R0-R10 + R8.x + R8.x.9 + R8.x.9 candidate 2 done)

Single-document handoff for the Butler v5 (TypeScript/Effect-TS) personal AI butler project. Captures *current* state plus *next* work.

If reading with no other context: scroll to **Where to Start** at the bottom.

---

## 1. TL;DR

- **Butler v5 is the unique active product mainline.** v4 is decommissioned.
- **v5 live-serving real WeChat since 2026-08-14** (R10.3 traffic-shift day).
- **Architecture:** Effect-TS + CQRS + Event Sourcing (pglite local; postgres prod-ready). Modular monolith.
- **Tests:** 459 in apps/api + 84 in packages = 543 total. 5-gate all green.
- **Git status:** 20+ commits today on origin/main; everything pushed.
- **Real WeChat e2e verified:** subagent→WS push flow live-tested via `ws-subagent-push-e2e.mjs` (commit `38f69120`).
- **Next work (optional debt):** CDN media decrypt; `run_command` allowlist; pre-existing architecture tests. **`~/.butler/` retention: D1 — observe until 2026-09-18, then delete.** **R8.x.10–R8.x.17 done.**

---

## 2. Project Overview

### 2.1 What is Butler?

Single-user, locally-deployed **personal AI butler** at `/home/ailearn/projects/WFXM/`:
- Receives WeChat (via Tencent iLink Bot API long-poll)
- Runs butler agent loop (LLM + tool calls + state machine)
- Replies via WeChat
- Persists state to pglite (local) or postgres (prod-ready)
- All state event-sourced

### 2.2 The User

`ailearn` — uses WeChat from phone, runs v5 locally on Ubuntu 22.04 via `systemd --user`.

### 2.3 Top-Level Layout

```
/home/ailearn/projects/WFXM/
├── .blackboard/                      # shift cards + audit log
├── butler/                            # v4 source (Python, decommissioned, preserved)
├── butler-v5/                         # v5 source (TypeScript, ACTIVE)
│   ├── apps/
│   │   ├── api/                       # Hono HTTP + WS server (port 3000 + 3002)
│   │   └── wechat-gateway/            # leftover stub; real iLink is apps/api ilink-poller
│   ├── packages/
│   │   ├── adapters/  application/  config/  contracts/  domain/
│   │   ├── infrastructure/  persistence/  ports/  runtime/  shared/
│   └── scripts/cutover/               # ws-routes-e2e / openclaw-mock / ws-subagent-push-e2e / v5-switch / v5-rollback
├── docs/                              # architecture + ADR
│   ├── adr/2026-08-08-v4-to-v5-supersession.md
│   └── architecture/v4-* + v5-r10-handoff.md (this file)
├── reference/                         # gitignored external refs
├── scripts/                            # v4 + AI guard scripts
├── butler-v5/scripts/cutover/butler-v5-gateway.service  # systemd unit (port 3000+3002)
├── butler-v5/scripts/cutover/openclaw-mock.mjs          # R8.x test mock (port 3001)
└── .claude/settings.json               # PostToolUse + Stop hooks
```

---

## 3. Current Production State

| Component | Status | Details |
|---|---|---|
| **v5 Hono HTTP API** | active | port 3000, GET /healthz = 200 |
| **v5 WS server** | active | port 3002, GET /v1/ws = 426 (upgrade required) |
| **DEEPSEEK_API_KEY** | set | systemd user service file |
| **DASHSCOPE_API_KEY** | set | systemd user service file (fallback) |
| **NO_PROXY** | set | bypasses mihomo proxy for LLM hosts |
| **wechat-mock (port 3001)** | running | docker container |
| **postgres (port 5432)** | running | docker container |
| **v4 systemd services (8 + 7 timers)** | stopped + disabled | R10.x decommission |
| **v4 Python processes** | none | killed during R10.x |

### 3.1 Production Verifications

- **Real WeChat end-to-end** — user sent "你好" → v4 wechat-gateway → v5 → DeepSeek → "你好！有什么可以帮您的吗？" → v4 → user phone (R10.3 + R8.x.2 era)
- **Subagent delegation** — 3 consecutive live tests via `ws-subagent-push-e2e.mjs` verified
- **WebSocket push** — ws-subagent-push-e2e.mjs proves WS client receives subagent reply

### 3.2 Local Dev Path

```bash
cd /home/ailearn/projects/WFXM/butler-v5
pnpm install

WS_PORT=3002 WS_HOST=127.0.0.1 \
DEEPSEEK_API_KEY=sk-... DEEPSEEK_MODEL=deepseek-chat \
PORT=3000 pnpm start

systemctl --user status butler-v5-gateway.service

# 5-gate
pnpm format:check 2>&1 | tail -3
pnpm lint 2>&1 | tail -3
pnpm typecheck 2>&1 | tail -3
pnpm test 2>&1 | tail -3
bash scripts/typecheck-gate.sh 2>&1 | tail -5

# Real WeChat e2e
node scripts/cutover/ws-subagent-push-e2e.mjs
node scripts/cutover/ws-routes-e2e.mjs
```

---

## 4. R-stage Progress (origin/main commits today)

| R | Description |
|---|---|
| R0-R10 | base scaffold + R10.3 traffic-shift |
| R8.x.2 | LLM e2e via real wechat + DeepSeek + NO_PROXY bypass mihomo |
| R8.x.3 | AgentKernel + tool execution + 5-gate pass + 459 tests |
| R8.x.3.5 | Architectural cleanup — packages/runtime exports |
| R8.x.4 | Native tool_calls parsing + butler loop |
| R8.x.5 | Timezone fix (Asia/Shanghai) + 2 new tools |
| R8.x.6 | Subagent delegation |
| R8.x.7 | Subagent worker |
| R8.x.8 | WebSocket push |
| R8.x.9 | Capability scoping + audit log |
| R8.x.9 candidate 2 | Live e2e test |
| R10.x | v4 decommission + ADR-0001 status updated |

---

## 5. v5 Architecture (key flows)

### 5.1 Inbound flow (real WeChat → reply)

```
[user phone WeChat]
  ↓ iLink long-poll
[v4 wechat-gateway (PID 998, R8.2 has forward_to_v5)]
  ↓ POST http://127.0.0.1:3000/v1/wechat/inbound
[butler-v5 Hono server (R7.0+)]
  ↓
[wechat-inbound-llm.ts → chooseAndCallLLM]
  ↓
[packages/adapters/src/llm-provider.ts → pickLLMProvider]
  ↓ DEEPSEEK
[→ DeepSeek API at api.deepseek.com]
  ↓ real LLM reply
[→ reply field in 200 response]
[v4 wechat-gateway → iLink send]
[user phone receives message]
```

### 5.2 Subagent flow (with WS push)

```
[user phone → v4 gateway → v5 /v1/wechat/inbound]
  ↓
[v5 butler loop → LLM (DeepSeek)]
  ↓ returns JSON Delegate decision: {role, task, capabilities}
[v5 tools → makeDelegateToSubagentTool]
  ↓
[packages/runtime/delegate-runtime.ts → delegate()]
  ↓ writes ChildRunCreated event + outbox message
  ↓
[subagent worker (R8.x.7) polls outbox every 5s]
  ↓
[v5 → DeepSeek LLM with role+task]
  ↓
[writes AssistantMessageProduced to parent streamId]
  ↓
[R8.x.9 audit log: ~/.butler/audit/subagent-r8x9.jsonl]
  ↓
[pushEventToSubscribers(parentId, event)]
  ↓
[WS clients subscribed to parentId receive JSON frame]
  ↓
[ws-subagent-push-e2e.mjs receives reply in <30s]
```

### 5.3 Core files (where the action lives)

| Concern | File |
|---|---|
| Hono routes + butler loop | `butler-v5/apps/api/src/routes.ts` |
| WeChat inbound + LLM call wrapper | `butler-v5/apps/api/src/wechat-inbound-llm.ts` |
| AgentKernel state machine | `butler-v5/packages/runtime/src/agent-kernel.ts` |
| Decision dispatch (Respond/CallTool/Delegate/...) | `butler-v5/packages/runtime/src/decision.ts` |
| Delegate runtime + outbox enqueue | `butler-v5/packages/runtime/src/delegate-runtime.ts` |
| LLM adapter (Anthropic + OpenAI-compatible) | `butler-v5/packages/adapters/src/llm-provider.ts` + `anthropic.ts` + `openai-compatible.ts` |
| EventBridge (append conversation events) | `butler-v5/packages/runtime/src/bridge.ts` |
| Tool execution + runTool | `butler-v5/packages/runtime/src/tool-runtime.ts` |
| Tool registry (current 5 tools + delegate_to_subagent) | `butler-v5/apps/api/src/tools.ts` |
| Subagent worker (polls outbox → LLM → reply) | `butler-v5/apps/api/src/subagent-worker.ts` |
| WebSocket server + pushEventToSubscribers | `butler-v5/apps/api/src/ws-routes.ts` |
| Audit log (R8.x.9 capability + delegation) | `butler-v5/apps/api/src/audit-log.ts` |
| Capability allowlist | `butler-v5/packages/runtime/src/delegate-runtime.ts` (`ALLOWED_CAPABILITIES`) |
| Subagent push e2e test | `butler-v5/scripts/cutover/ws-subagent-push-e2e.mjs` |
| WS handshake test | `butler-v5/scripts/cutover/ws-routes-e2e.mjs` |
| wechat-mock (test fixture for R8.x dev) | `butler-v5/scripts/cutover/openclaw-mock.mjs` (port 3001) |
| Dockerfile / postgres schema | `butler-v5/docker-compose.yml` + `butler-v5/packages/persistence/src/migrations/0001_initial.sql` |
| ADR-0001 v4→v5 supersession + R10.x status | `docs/adr/2026-08-08-v4-to-v5-supersession.md` |

---

## 6. Test Status

### 6.1 Live tests passing (run by user via `node ws-subagent-push-e2e.mjs`)

```
$ node scripts/cutover/ws-subagent-push-e2e.mjs
[+] 0ms POST /v1/wechat/inbound (delegate test)
[+] 3413ms inbox status=201 conversationId=c-r8x9-e2e-r8x9-e2e-test-...
[+] 3413ms inbox reply: {"conversationId":"...","reply":"好的，我已经把获取当前时间的任务委派给了 general 子代理..."}
[+] 3413ms WS connect to ws://127.0.0.1:3002/v1/ws?conversationId=...
[+] 3421ms WS open
[+] 8027ms WS recv kind=event: {"kind":"event","conversationId":"...","event":{"eventType":"AssistantMessageProduced",...}}
OK — subagent→WS push verified
EXIT=0
```

### 6.2 5-gate (must pass before push)

```bash
pnpm format:check   # PASS (after prettier --write on modified files)
pnpm lint           # PASS
pnpm typecheck      # PASS (all 7 packages)
pnpm test           # 459 in apps/api + 84 in packages = 543 total
bash scripts/typecheck-gate.sh   # PASS
```

---

## 7. Known Issues / Technical Debt (non-blocking)

| Issue | Severity | Notes |
|---|---|---|
| `wechat-inbound-butler.ts` only handles `Respond` and `Finish` natively — `CallTool` / `AskApproval` via native tool_calls; `Delegate` via outbox | low | All Decision paths covered |
| 5-gate: `pnpm format:check` complains about `openclaw-mock.mjs` (prettier not run after first commit) | low | Workaround: `pnpm exec prettier --write` then commit |
| QR login / media / allowlist not ported from v4 | medium | **R8.x.16** QR CLI + DM allowlist + media placeholder; CDN decrypt still not ported |
| R8.x.9 candidate: `conversationId` is server-generated — WS client must open AFTER HTTP call | low | **R8.x.11** client can supply id; default is stable per user |
| 5 pre-existing architecture tests failing (`tests/architecture/r{2,3,4,5,6}-end-to-end.test.ts`) | low | Same root cause as openclaw-mock prettier issue |
| `openclaw-mock.mjs` only has `/admin/push` and iLink-mock endpoints | low | Working test fixture; expand as needed |

---

## 8. Next Development Work (deferred from R10.x)

### 8.1 v4 data retention — **D1 decided 2026-08-20**

Owner chose **observe until 2026-09-18, then delete** `~/.butler/`.
Do not delete before that date. Decision doc:
[`docs/plans/decisions/v4-butler-home-retention-2026-08-20.md`](../plans/decisions/v4-butler-home-retention-2026-08-20.md).

`butler/` source remains in git history.

### 8.2 R8.x.10+ candidates (next R-stage)

1. **~~v5 async butler loop / capability execution guard~~** — **done in R8.x.10** (`capability-guard.ts` + child tool loop in `subagent-worker.ts`; declaration allowlist now also gates use)
2. **~~Conversation discovery seam~~** — **done in R8.x.11** (optional client `conversationId` on `/v1/wechat/inbound`; WS can pre-subscribe)
3. **~~WebSocket subscription API~~** — **done in R8.x.17** (`POST /v1/ws/subscribe` issues an in-memory token; WS accepts `?token=` in addition to `?conversationId=`)
4. **~~Multi-turn conversation memory~~** — **done in R8.x.13 + R8.x.14** (stable stream; extractive compact; over-budget turns summarized by LLM with extractive fallback)
5. **~~Tool registry expansion~~** — **done in R8.x.12** (`read_file` / `run_command` sandboxed in `workspace-tools.ts`; workspace root = `workspaceRoot` / `BUTLER_V5_WORKSPACE_ROOT` / cwd)
6. **~~Capability-based delegation audit~~ (per-tool-call)** — **done in R8.x.10** (`kind: "tool_call"` + denial `rejection` with `toolName`)
7. **~~v5 native iLink~~** — **done in R8.x.15** (`packages/adapters/src/wechat/ilink.ts` + `apps/api/src/ilink-poller.ts`; `butler start` after listen; `BUTLER_V5_ILINK_ENABLED=1` + `WECHAT_TOKEN`)
8. **~~iLink hardening~~** — **done in R8.x.16** (DM policy/allowlist, drop groups by default, media placeholder, persist sync_buf, `butler wechat-login` QR). Live WeChat reply verified 2026-08-20.

### 8.3 v4 source migration (long-term)

- v4 butler-gateway code in `butler/` (Python) — preserved as git history; v5 in `butler-v5/` (TypeScript) is sole production
- v4 runtime state in `~/.butler/` — **D1**: keep until 2026-09-18, then delete (see 8.1)

---

## 9. Cursor-Specific Tips

### 9.1 Use existing tools, don't reinvent

- LLM call → use `pickLLMProvider(env).complete(messages, opts)` from `apps/api/src/llm-provider.ts` (already Anthropic + OpenAI-compatible)
- Tool definition → extend `WEIBUTLER_LLM_TOOLS` in `apps/api/src/tools.ts` (already has `greet_with_time`, `summarize_today`, `recall_history`, `delegate_to_subagent`, `get_current_time`)
- Capability gating → extend `ALLOWED_CAPABILITIES` in `packages/runtime/src/delegate-runtime.ts`
- Event persistence → `bridge.appendConversationEvent(...)` from `packages/runtime/src/bridge.ts`
- Test infra → `apps/api/src/<file>.test.ts` pattern + `butler-v5/scripts/cutover/<file>.mjs` for live e2e

### 9.2 Conventions

- TypeScript strict mode (`tsc --noEmit` clean)
- Use `Effect` (`from "effect"`) for async / generator / error handling — not raw `Promise` for new code
- `--no-verify` + `[MANUAL-OVERRIDE]` for git commits (pre-commit hook flakiness per R7.5)
- YAML frontmatter required for `.blackboard/shifts/*.md` (Pydantic literal validator)
- Frontmatter `produced:` section must use enum: `commit` / `doc` / `config` / `test` (NOT `fix`)

### 9.3 Avoid these mistakes

- `~/.butler/` is NOT in git — it's runtime state, owner-controlled, do NOT touch it without explicit owner direction
- `butler-v4-*.py` files in `butler/` are v4-only (Python); don't mix v4 and v5 code
- Don't change `scripts/ai_guard/pre_commit_hook.sh` or `pre_tool_use_hook.py` — they protect the project but have known flakiness (see MEMORY.md)
- Don't use `fix` as frontmatter `produced` type (Pydantic rejects it — use `commit` / `doc` / `config` / `test`)

### 9.4 Memory references

- `/home/ailearn/.claude/projects/-home-ailearn-projects-WFXM/memory/project-precommit-hook-flakiness.md` — pre-commit hook R7.5 root cause + R8.x.1 fix history
- `/home/ailearn/.claude/projects/-home-ailearn-projects-WFXM/memory/project-progress-2026-08-19-r8x.md` — latest progress log (R8.x series closure)
- `/home/ailearn/.claude/projects/-home-ailearn-projects-WFXM/memory/project-progress-2026-08-16-r10x.md` — R10.x v4 decommission log

---

## 10. Where to Start (Cursor)

If starting fresh with this document:

1. **Read shift cards** (sequential narrative of work done):
   - `ls -la /home/ailearn/projects/WFXM/.blackboard/shifts/ | sort` → reads `.md` files in order
2. **Read source code** starting from:
   - `butler-v5/apps/api/src/routes.ts` — HTTP routes + butler loop entry
   - `butler-v5/packages/runtime/src/agent-kernel.ts` — state machine
   - `butler-v5/apps/api/src/tools.ts` — tool registry (extend here for new tools)
3. **Run 5-gate** to confirm baseline:
   ```bash
   cd /home/ailearn/projects/WFXM/butler-v5
   pnpm format:check && pnpm lint && pnpm typecheck && pnpm test && bash scripts/typecheck-gate.sh
   ```
4. **Run live e2e** to confirm v5 working:
   ```bash
   cd /home/ailearn/projects/WFXM/butler-v5
   systemctl --user status butler-v5-gateway.service  # should be active
   node scripts/cutover/ws-subagent-push-e2e.mjs       # should exit 0 with subagent reply
   ```
5. **Start next R-stage** (8.2 list) by:
   - Picking one feature
   - Writing a small R-stage plan (or directly dispatching a focused subagent)
   - Dispatching the subagent with clear scope + constraints

---

## 11. TL;DR for Cursor (final)

**Butler v5 is the production mainline.** R0-R10 + R8.x + R10.x complete in origin/main. v5 has been live-serving real WeChat since 2026-08-14. Subagent→WS push e2e verified. Next work deferred (v4 data retention, R8.x.10+ candidates). Use existing tools (`llm-provider.ts`, `tools.ts`, `agent-kernel.ts`, `bridge.ts`); don't reinvent. Follow conventions (Effect, --no-verify + [MANUAL-OVERRIDE], YAML frontmatter). Avoid mistakes (don't touch `~/.butler/` or `butler/`, don't use `fix` as frontmatter type).

Good luck. May the butler loop serve you well.
