# Design: Client-supplied `conversationId` on WeChat inbound

**Date:** 2026-08-19  
**Status:** approved (owner chose approach A)  
**R-stage:** R8.x.11 candidate (conversation discovery seam)  
**Author:** cursor

## Problem

`POST /v1/wechat/inbound` always generates `conversationId` server-side and returns it only after the butler loop finishes. WebSocket clients (`/v1/ws?conversationId=...`) therefore cannot subscribe until the HTTP response is back. Subagent replies pushed via `pushEventToSubscribers` can be missed if the client connects too late relative to the worker tick.

## Decision

**Approach A — optional client-supplied `conversationId`.**

- If the inbound body omits `conversationId`, keep today's server-generated id (`c-{projectId}-{fromUserId}-{Date.now()}`).
- If present and valid, use it as the stream id for events, butler loop, and the JSON response.
- If present but invalid, return `400` and do not run the loop.

Rejected for this stage:

- **B** (`POST /v1/conversations` first) — already exists for another flow; not required for WS pre-subscribe.
- **C** (early HTTP flush/header) — more complex streaming contract; not needed if the client can name the id up front.

## Behavior

| Inbound body | Behavior |
|---|---|
| No `conversationId` | Server generates id (unchanged) |
| Valid `conversationId` | Use as-is for events + loop + response |
| Present but invalid | `400` text body; no loop |

### Validation rules

- Type: non-empty `string`
- Max length: 128
- Charset: `^[A-Za-z0-9_.:-]+$`
- No “must already exist” check (client may open WS before inbound)
- No cross-user auth (v5 remains single-user local)

## Scope

### In scope

1. `butler-v5/apps/api/src/routes.ts` — parse / validate / use optional field
2. Unit tests for omit / valid reuse / invalid 400
3. Update `butler-v5/scripts/cutover/ws-subagent-push-e2e.mjs` — pick id → open WS → POST with that id
4. Note in `docs/architecture/v5-r10-handoff.md` that the seam exists

### Out of scope

- Changing `POST /v1/conversations`
- Changing WS frame protocol or `pushEventToSubscribers`
- Multi-tenant / ownership checks on conversation ids
- Returning conversationId before the butler loop completes (HTTP still waits for reply)

## Success criteria

1. Legacy clients that omit `conversationId` still get `201` with a server-generated id.
2. Clients that supply a valid id get the same id echoed in the `201` body; events land on that stream.
3. Live e2e: WS connects with a pre-chosen id, then inbound uses that id, and still receives `AssistantMessageProduced` within 30s.
4. Invalid id → `400`; no `ConversationStarted` / loop side effects for that request.

## Test plan

- Unit: omit → generated; valid → echoed; invalid charset/empty/too long → 400
- Live e2e script: pre-subscribe path (primary proof of the seam)

## Risks

- Clients can invent arbitrary ids and create many streams — acceptable for single-user local deploy.
- Reusing an existing id appends another `ConversationStarted` — acceptable for this stage; multi-turn stream semantics are a later memory item.
