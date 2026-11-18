import { readFileSync } from "node:fs"
import type { ILinkResult } from "./ilink-protocol.js"

export const DASHSCOPE_ASR_URL =
  "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"

export type TranscribeDashscopeInput = {
  readonly bytes: Buffer
  readonly format: "wav" | "mp3" | "silk" | string
  readonly apiKey: string
  readonly fetch: typeof fetch
  readonly endpoint?: string
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return undefined
  }
  return value as Record<string, unknown>
}

function transcriptFromBody(parsed: Record<string, unknown>): string {
  const output = asRecord(parsed["output"])
  if (output) {
    const text = output["text"]
    if (typeof text === "string" && text.trim()) return text.trim()
  }
  const direct = parsed["text"]
  return typeof direct === "string" ? direct.trim() : ""
}

/**
 * File ASR against DashScope. Silk is refused: WeChat voice needs a
 * decoder we do not ship; use `voice_item.text` or inject transcribeVoice.
 */
export async function transcribeDashscopeFile(
  input: TranscribeDashscopeInput,
): Promise<ILinkResult<string>> {
  const format = input.format.trim().toLowerCase()
  if (format === "silk" || format === "slk") {
    return { ok: false, reason: "silk decode is not bundled" }
  }
  const endpoint = input.endpoint ?? DASHSCOPE_ASR_URL
  try {
    const res = await input.fetch(endpoint, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${input.apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "paraformer-v2",
        input: {
          format,
          audio_data: input.bytes.toString("base64"),
        },
      }),
    })
    const raw = await res.text()
    if (!res.ok) return { ok: false, reason: `asr HTTP ${res.status}: ${raw.slice(0, 200)}` }
    const parsed: unknown = JSON.parse(raw)
    const rec = asRecord(parsed)
    if (!rec) return { ok: false, reason: "asr response is not a JSON object" }
    const text = transcriptFromBody(rec)
    if (!text) return { ok: false, reason: "asr response has no text" }
    return { ok: true, value: text }
  } catch (err) {
    return { ok: false, reason: err instanceof Error ? err.message : String(err) }
  }
}

export function makeTranscribeVoice(env: NodeJS.ProcessEnv, fetchImpl: typeof fetch) {
  return async (path: string): Promise<ILinkResult<string>> => {
    const apiKey = (env["DASHSCOPE_API_KEY"] ?? "").trim()
    if (!apiKey) return { ok: false, reason: "DASHSCOPE_API_KEY unset" }
    const lower = path.toLowerCase()
    const format = lower.endsWith(".mp3") ? "mp3" : lower.endsWith(".wav") ? "wav" : "silk"
    let bytes: Buffer
    try {
      bytes = readFileSync(path)
    } catch (err) {
      return { ok: false, reason: err instanceof Error ? err.message : String(err) }
    }
    return transcribeDashscopeFile({ bytes, format, apiKey, fetch: fetchImpl })
  }
}
