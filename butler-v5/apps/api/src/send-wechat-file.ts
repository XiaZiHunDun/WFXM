/**
 * R8.x.21 — `send_wechat_file`: send a workspace file back to the
 * current WeChat user. Parent butler only; not an ALLOWED_CAPABILITY.
 */
import { readFileSync, statSync } from "node:fs"
import { basename } from "node:path"
import {
  DEFAULT_ILINK_BASE_URL,
  DEFAULT_WECHAT_CDN_BASE_URL,
  sendOutboundMedia,
  type ILinkResult,
} from "@butler/adapters"
import type { ToolDefinition } from "@butler/runtime/tool-runtime.js"
import { resolveUnderWorkspace, workspaceRootFrom } from "./workspace-tools.js"

export type SendWechatMediaFn = (input: {
  readonly to: string
  readonly fileName: string
  readonly plaintext: Buffer
  readonly caption?: string
  readonly contextToken?: string
}) => Promise<ILinkResult<{ readonly clientId: string; readonly kind: "image" | "file" }>>

export interface SendWechatFileContext {
  readonly workspaceRoot?: string
  readonly wechatUserId?: string
  readonly wechatContextToken?: string
  readonly sendWechatMedia?: SendWechatMediaFn
  readonly env?: NodeJS.ProcessEnv
}

function mediaMaxBytes(env: NodeJS.ProcessEnv): number {
  const raw = Number(env["WECHAT_MEDIA_MAX_BYTES"] ?? 8 * 1024 * 1024)
  return Number.isFinite(raw) && raw > 0 ? raw : 8 * 1024 * 1024
}

function defaultSendWechatMedia(env: NodeJS.ProcessEnv): SendWechatMediaFn | undefined {
  const token = (env["WECHAT_TOKEN"] ?? "").trim()
  if (!token) return undefined
  const baseUrl = (env["WECHAT_BASE_URL"] ?? env["ILINK_BASE_URL"] ?? DEFAULT_ILINK_BASE_URL).trim()
  const cdnBaseUrl = (env["WECHAT_CDN_BASE_URL"] ?? DEFAULT_WECHAT_CDN_BASE_URL).trim()
  const maxBytes = mediaMaxBytes(env)
  return (input) =>
    sendOutboundMedia(
      { baseUrl, token },
      {
        to: input.to,
        fileName: input.fileName,
        plaintext: input.plaintext,
        cdnBaseUrl,
        maxBytes,
        ...(input.caption ? { caption: input.caption } : {}),
        ...(input.contextToken ? { contextToken: input.contextToken } : {}),
      },
    )
}

export function makeSendWechatFileTool(ctx: SendWechatFileContext = {}): ToolDefinition {
  return {
    name: "send_wechat_file" as ToolDefinition["name"],
    risk: "medium",
    async run(
      args: Record<string, unknown>,
    ): Promise<
      | { readonly ok: true; readonly output: unknown }
      | { readonly ok: false; readonly reason: string }
    > {
      const wechatUserId = ctx.wechatUserId?.trim() ?? ""
      if (!wechatUserId) return { ok: false, reason: "no wechat recipient on this turn" }
      const rawPath = args["path"]
      if (typeof rawPath !== "string") return { ok: false, reason: "path is required" }
      const captionRaw = args["caption"]
      const caption = typeof captionRaw === "string" ? captionRaw.trim() : ""
      const env = ctx.env ?? process.env
      const maxBytes = mediaMaxBytes(env)
      const resolved = resolveUnderWorkspace(workspaceRootFrom(ctx), rawPath)
      if (!resolved.ok) return resolved
      try {
        const st = statSync(resolved.path)
        if (!st.isFile()) return { ok: false, reason: "path is not a file" }
        if (st.size > maxBytes) return { ok: false, reason: `file exceeds ${maxBytes} bytes` }
        const plaintext = readFileSync(resolved.path)
        const send = ctx.sendWechatMedia ?? defaultSendWechatMedia(env)
        if (!send) return { ok: false, reason: "WECHAT_TOKEN is not configured" }
        const sent = await send({
          to: wechatUserId,
          fileName: basename(resolved.path),
          plaintext,
          ...(caption ? { caption } : {}),
          ...(ctx.wechatContextToken ? { contextToken: ctx.wechatContextToken } : {}),
        })
        if (!sent.ok) return sent
        const label = sent.value.kind === "image" ? "图片" : "文件"
        return { ok: true, output: `已发送${label} ${basename(resolved.path)}` }
      } catch (err) {
        return { ok: false, reason: err instanceof Error ? err.message : String(err) }
      }
    },
  }
}
