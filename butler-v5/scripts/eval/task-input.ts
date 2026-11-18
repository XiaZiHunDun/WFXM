/** Shared eval input / trace contracts for the WFXM driver. */

export interface FixtureEntry {
  readonly content?: string
  readonly toolCalls?: readonly {
    readonly id: string
    readonly name: string
    readonly args: Record<string, unknown>
  }[]
  readonly stopReason?: "end_turn" | "tool_use" | "stop" | "max_tokens"
}

export interface SeedFile {
  readonly path: string
  readonly content: string
}

export interface SeedDocument {
  readonly title: string
  readonly text: string
  readonly format?: "plaintext" | "markdown" | "pdf"
}

/** RAG 任务的检索真值：预期命中的文档标题与参考答案。 */
export interface RagExpectation {
  readonly expectedDocTitles?: readonly string[]
  readonly reference?: string
}

export interface EvalTaskInput {
  readonly id: string
  readonly turns: readonly string[]
  /** 单轮超时；由任务声明透传给驱动。 */
  readonly timeoutMs?: number
  /** 任务预算；maxToolCalls 会作为 Run budget 传给运行时。 */
  readonly budget?: {
    readonly maxTurns?: number
    readonly maxToolCalls?: number
  }
  /** 评估侧声明要回读的工作区文件（来自 expect.workspaceState[].path）。 */
  readonly workspacePaths?: readonly string[]
  /** repo-task：本地夹具仓库目录，执行前整体复制到工作区。 */
  readonly repoFixture?: string
  /** 真实模型模式：不注入 fixture，由 production wiring 选择模型。 */
  readonly realModel?: boolean
  /** repo-task：测试 oracle；驱动在 agent 执行前后各跑一次。 */
  readonly tests?: { readonly command: string; readonly timeoutMs?: number }
  readonly runtimeHints?: {
    readonly wfxm?: {
      readonly scenarioId?: string
      readonly fixtures?: {
        readonly plan?: readonly FixtureEntry[]
        readonly exec?: readonly FixtureEntry[]
        readonly intake?: readonly FixtureEntry[]
        readonly seedFiles?: readonly SeedFile[]
      }
      /** RAG 任务：入库文档与检索真值。 */
      readonly rag?: {
        readonly documents?: readonly SeedDocument[]
        readonly expectation?: RagExpectation
      }
    }
  }
}

export interface TraceEvent {
  readonly schema: "wfxm.trace/0"
  readonly traceId: string
  readonly runId: string
  readonly runtime: "wfxm"
  readonly seq: number
  readonly ts: string
  readonly type: string
  readonly spanId: string
  readonly parentSpanId: string | null
  readonly actor: { readonly kind: "owner" | "agent" | "system"; readonly id: string }
  readonly payload: Record<string, unknown>
}
