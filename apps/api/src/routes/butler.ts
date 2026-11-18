/**
 * POST /v1/wechat/butler/inbound — entry point for the new Butler Runtime.
 *
 * Runs alongside the legacy /v1/wechat/inbound (which still owns the
 * RunEngine pipeline). The assembly is built lazily from env so a missing
 * MINIMAX/project config returns 503 instead of failing process boot.
 */
import type { Hono } from "hono"
import type { ButlerMemoryPort } from "@butler/ports/core/butler-memory.js"
import type { ChannelPort } from "@butler/ports/core/channel.js"
import type { TaskMemoryPort } from "@butler/ports/core/task-memory.js"
import { parseApprovalPayload } from "@butler/runtime/butler/approval-notice.js"
import { normalizeWechatInbound } from "@butler/runtime/intake/index.js"
import { handleButlerInbound } from "../butler-inbound.js"
import { createButlerAssembly, type ButlerAssembly } from "../butler-assembly.js"
import { requireInboundSharedSecret } from "../env-util.js"
import { resolveWechatInboundProjectId } from "../wechat-active-project.js"
import type { Wiring } from "../wiring.js"

export interface ButlerRoutesOptions {
  readonly env?: NodeJS.ProcessEnv
  /** agent-rag adapters; omitted when memory is not configured. */
  readonly memory?: {
    readonly butler?: ButlerMemoryPort
    readonly task?: TaskMemoryPort
  }
  /** Test seam: bypass env/model construction. */
  readonly createAssembly?: (
    wiring: Wiring,
    env: NodeJS.ProcessEnv,
  ) => ButlerAssembly | Promise<ButlerAssembly>
}

/** BUTLER_V5_PROJECT_ROOTS='{"proj-1":"/srv/repos/proj-1"}' */
export function parseProjectRoots(env: NodeJS.ProcessEnv): Record<string, string> {
  const raw = (env["BUTLER_V5_PROJECT_ROOTS"] ?? "").trim()
  if (raw.length === 0) return {}
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    throw new Error("BUTLER_V5_PROJECT_ROOTS must be valid JSON")
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("BUTLER_V5_PROJECT_ROOTS must be an object of projectId -> root")
  }
  const roots: Record<string, string> = {}
  for (const [projectId, root] of Object.entries(parsed)) {
    if (typeof root !== "string" || root.length === 0) {
      throw new Error(`BUTLER_V5_PROJECT_ROOTS has an invalid root for ${projectId}`)
    }
    roots[projectId] = root
  }
  return roots
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

export function registerButlerRoutes(
  app: Hono,
  wiring: Wiring,
  options: ButlerRoutesOptions = {},
): void {
  const env = options.env ?? process.env
  let cached: Promise<ButlerAssembly> | null = null

  const assembly = (): Promise<ButlerAssembly> => {
    if (cached === null) {
      cached = Promise.resolve()
        .then(() =>
          options.createAssembly
            ? options.createAssembly(wiring, env)
            : createButlerAssembly({
                db: wiring.db,
                projects: parseProjectRoots(env),
                env,
                ...(options.memory?.butler === undefined
                  ? {}
                  : { butlerMemory: options.memory.butler }),
                ...(options.memory?.task === undefined ? {} : { taskMemory: options.memory.task }),
              }),
        )
        .catch((error: unknown) => {
          // Do not cache failures: a config fix + retry should work.
          cached = null
          throw error
        })
    }
    return cached
  }

  app.post("/v1/wechat/butler/inbound", async (c) => {
    const denied = requireInboundSharedSecret(env, c.req.header("x-inbound-secret"))
    if (denied) return denied
    const body = (await c.req.json().catch(() => null)) as null | {
      apiVersion?: string
      fromUserId?: string
      content?: string
      messageId?: string
      projectId?: string
      conversationId?: unknown
      activeTaskId?: string
      approvalPayload?: string
    }
    if (!body || body.apiVersion !== "v1" || typeof body.fromUserId !== "string") {
      return c.text("invalid body", 400)
    }
    const approvalPayload =
      typeof body.approvalPayload === "string" && body.approvalPayload.length > 0
        ? body.approvalPayload
        : undefined
    if (
      approvalPayload !== undefined &&
      parseApprovalPayload({ payload: approvalPayload }) === null
    ) {
      return c.text(`invalid approvalPayload: ${approvalPayload}`, 400)
    }
    if (approvalPayload === undefined && typeof body.content !== "string") {
      return c.text("invalid body", 400)
    }

    const normalized = normalizeWechatInbound({
      fromUserId: body.fromUserId,
      content: approvalPayload === undefined ? (body.content as string) : "确认",
      ...(body.messageId ? { messageId: body.messageId } : {}),
      projectId: resolveWechatInboundProjectId(body.fromUserId, body.projectId, env),
      conversationId: body.conversationId,
    })
    if (!normalized.ok) {
      if (normalized.error.kind === "invalid_conversation_id") {
        return c.text(`invalid conversationId: ${normalized.error.reason}`, 400)
      }
      return c.text(normalized.error.reason, 400)
    }
    const inbound = normalized.value

    let runtime: ButlerAssembly
    try {
      runtime = await assembly()
    } catch (error) {
      return c.json({ error: `butler runtime unavailable: ${errorMessage(error)}` }, 503)
    }

    const channel: ChannelPort = {
      channelKind: "wechat",
      async sendText() {
        // Hono returns the reply in the response body; nothing to push.
        return { ok: true, messageId: null }
      },
    }

    try {
      const outcome = await handleButlerInbound({
        butler: runtime.butler,
        channel,
        recipient: { address: inbound.subject, channelKind: "wechat" },
        input: {
          conversationId: inbound.conversationId,
          userId: inbound.subject,
          projectId: inbound.projectId,
          content: approvalPayload === undefined ? inbound.content : "",
          ...(approvalPayload === undefined ? {} : { approvalPayload }),
          ...(typeof body.activeTaskId === "string" ? { activeTaskId: body.activeTaskId } : {}),
        },
      })
      return c.json(
        {
          conversationId: inbound.conversationId,
          reply: outcome.result.reply,
          route: outcome.result.route,
          ...(outcome.result.rule === undefined ? {} : { rule: outcome.result.rule }),
          ...(outcome.result.taskId === undefined ? {} : { taskId: outcome.result.taskId }),
          traces: outcome.result.traces,
          sent: outcome.sent,
          ...(outcome.sendError === undefined ? {} : { sendError: outcome.sendError }),
        },
        200,
      )
    } catch (error) {
      return c.json({ error: errorMessage(error) }, 500)
    }
  })
}
