/**
 * Embedding provider for hybrid document recall (ISSUE-09).
 *
 * DashScope 的 OpenAI-compatible `/embeddings`；无 key 或显式关闭时返回 null，
 * 调用方回退到纯词法召回。
 */

export interface EmbeddingProvider {
  readonly model: string
  readonly dimensions: number
  embed(texts: readonly string[]): Promise<readonly number[][]>
}

export interface DashScopeEmbeddingConfig {
  readonly apiKey: string
  readonly baseUrl?: string
  readonly model?: string
  readonly dimensions?: number
  readonly batchSize?: number
  readonly fetch?: typeof fetch
}

const DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
const DEFAULT_MODEL = "text-embedding-v3"
const MAX_BATCH = 10

export function makeDashScopeEmbeddingProvider(
  config: DashScopeEmbeddingConfig,
): EmbeddingProvider {
  const baseUrl = (config.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "")
  const model = config.model ?? DEFAULT_MODEL
  const dimensions = config.dimensions ?? 1024
  const batchSize = Math.min(MAX_BATCH, Math.max(1, Math.floor(config.batchSize ?? MAX_BATCH)))
  const fetchImpl = config.fetch ?? fetch

  async function embed(texts: readonly string[]): Promise<readonly number[][]> {
    const vectors: number[][] = []
    for (let offset = 0; offset < texts.length; offset += batchSize) {
      const input = texts.slice(offset, offset + batchSize)
      if (input.length === 0) continue
      const response = await fetchImpl(`${baseUrl}/embeddings`, {
        method: "POST",
        headers: {
          authorization: `Bearer ${config.apiKey}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({ model, input, dimensions, encoding_format: "float" }),
      })
      if (!response.ok) {
        throw new Error(`embedding api error: ${response.status}`)
      }
      const data = (await response.json()) as {
        readonly data?: readonly { readonly index: number; readonly embedding: readonly number[] }[]
      }
      const rows = [...(data.data ?? [])].sort((a, b) => a.index - b.index)
      if (rows.length !== input.length) {
        throw new Error(`embedding count mismatch: ${rows.length} != ${input.length}`)
      }
      for (const row of rows) {
        if (!Array.isArray(row.embedding) || row.embedding.length === 0) {
          throw new Error("embedding payload is empty")
        }
        vectors.push([...row.embedding])
      }
    }
    return vectors
  }

  return { model, dimensions, embed }
}

/**
 * Env：
 *   DASHSCOPE_API_KEY (required)
 *   BUTLER_V5_EMBEDDING_ENABLED=0 关闭
 *   BUTLER_V5_EMBEDDING_MODEL=text-embedding-v3
 *   BUTLER_V5_EMBEDDING_DIMENSIONS=1024
 *   BUTLER_V5_EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
 */
export function dashScopeEmbeddingFromEnv(
  env: Record<string, string | undefined> = process.env,
  fetchImpl?: typeof fetch,
): EmbeddingProvider | null {
  if ((env["BUTLER_V5_EMBEDDING_ENABLED"] ?? "1").trim() === "0") return null
  const apiKey = (env["DASHSCOPE_API_KEY"] ?? "").trim()
  if (!apiKey) return null
  const dimensionsRaw = Number(env["BUTLER_V5_EMBEDDING_DIMENSIONS"] ?? "1024")
  const dimensions =
    Number.isFinite(dimensionsRaw) && dimensionsRaw > 0 ? Math.floor(dimensionsRaw) : 1024
  return makeDashScopeEmbeddingProvider({
    apiKey,
    dimensions,
    model: (env["BUTLER_V5_EMBEDDING_MODEL"] ?? "").trim() || DEFAULT_MODEL,
    baseUrl: (env["BUTLER_V5_EMBEDDING_BASE_URL"] ?? "").trim() || DEFAULT_BASE_URL,
    ...(fetchImpl ? { fetch: fetchImpl } : {}),
  })
}
