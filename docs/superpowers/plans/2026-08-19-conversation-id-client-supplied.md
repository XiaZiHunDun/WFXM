# Client-supplied conversationId Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow `POST /v1/wechat/inbound` to accept an optional client `conversationId` so WS clients can subscribe before the HTTP butler loop returns.

**Architecture:** Extract a pure parser (`parseClientConversationId`) used by `routes.ts`. Absent → server generates; valid → reuse; invalid → 400 before loop. Update live e2e to pre-subscribe.

**Tech Stack:** TypeScript, Hono, Vitest, existing EventBridge + WS e2e script

**Spec:** `docs/superpowers/specs/2026-08-19-conversation-id-client-supplied-design.md`

---

### Task 1: Pure parser + unit tests

**Files:**
- Create: `butler-v5/apps/api/src/conversation-id.ts`
- Create: `butler-v5/apps/api/src/conversation-id.test.ts`

- [ ] **Step 1: Write failing tests** for absent / valid / empty / bad charset / too long

- [ ] **Step 2: Implement `parseClientConversationId`**

```ts
export type ParseConversationIdResult =
  | { readonly kind: "absent" }
  | { readonly kind: "valid"; readonly value: string }
  | { readonly kind: "invalid"; readonly reason: string }

export const CONVERSATION_ID_MAX_LEN = 128
export const CONVERSATION_ID_PATTERN = /^[A-Za-z0-9_.:-]+$/

export function parseClientConversationId(raw: unknown): ParseConversationIdResult
```

- [ ] **Step 3: Run tests** — `pnpm exec vitest run apps/api/src/conversation-id.test.ts`

- [ ] **Step 4: Commit** — `feat(butler-v5): add conversationId parser for inbound seam`

### Task 2: Wire into `/v1/wechat/inbound`

**Files:**
- Modify: `butler-v5/apps/api/src/routes.ts`
- Modify: `butler-v5/apps/api/src/wiring.test.ts` (mock `runButlerLoop`)

- [ ] **Step 1: Failing route tests** — omit generates; valid echoed; invalid 400 with no stream events

- [ ] **Step 2: Wire parser in routes** before `ConversationStarted`

- [ ] **Step 3: Run** — `pnpm exec vitest run apps/api/src/wiring.test.ts apps/api/src/conversation-id.test.ts`

- [ ] **Step 4: Commit** — `feat(butler-v5): accept optional conversationId on wechat inbound`

### Task 3: E2e pre-subscribe + handoff

**Files:**
- Modify: `butler-v5/scripts/cutover/ws-subagent-push-e2e.mjs`
- Modify: `docs/architecture/v5-r10-handoff.md`

- [ ] **Step 1: E2e picks id, opens WS, then POSTs with that id**

- [ ] **Step 2: Handoff marks conversation discovery seam done**

- [ ] **Step 3: format/lint/typecheck + related tests**

- [ ] **Step 4: Commit** — `test(butler-v5): e2e WS pre-subscribe via client conversationId`
