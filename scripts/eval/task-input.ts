/** Shared eval input / trace contracts for the WFXM driver. */

export interface FixtureEntry {
  readonly content?: string
  readonly toolCalls?: readonly {
    readonly id: string
    readonly name: string
    readonly args: Record<string, unknown>
  }[]
  readonly stopReason?: "end_turn" | "tool_use" | "stop" | "max_tokens"
  /** 模拟 LLM 延迟（毫秒）；配合 BUTLER_V5_LLM_TIMEOUT_MS 验证超时路径。 */
  readonly latencyMs?: number
}

/** 内部场景转换用的最小 setup 原语；只暴露评估必需的状态预置。 */
export type SetupOperation =
  | {
      readonly op: "createConversation"
      readonly conversationId: string
      readonly subject: string
      readonly text?: string
    }
  | {
      readonly op: "createActiveRun"
      readonly conversationId: string
      readonly subject: string
      readonly goal?: string
    }
  | {
      readonly op: "createProjectKnowledge"
      readonly projectId: string
      readonly title: string
      readonly body: string
      readonly kind?: "file_snapshot" | "memory_md" | "manual_note" | "ingested_document"
      readonly tags?: readonly string[]
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
  /** 可选：每轮固定的 messageId（用于重复投递/幂等轨迹）；缺省由 harness 生成。 */
  readonly messageIds?: readonly (string | null)[]
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
        /** 多轮任务：按轮次覆盖 LLM 应答；未声明的轮次回落到 plan/exec/intake。 */
        readonly turns?: readonly {
          readonly plan?: readonly FixtureEntry[]
          readonly exec?: readonly FixtureEntry[]
          readonly intake?: readonly FixtureEntry[]
        }[]
      }
      /** RAG 任务：入库文档与检索真值。 */
      readonly rag?: {
        readonly documents?: readonly SeedDocument[]
        readonly expectation?: RagExpectation
      }
      /** 首轮使用的会话；内部场景（活跃 Run 冲突）需要预置同一会话。 */
      readonly conversationId?: string
      /** 场景级环境变量，在装配 wiring 之前生效（如 LLM 超时）。 */
      readonly env?: Readonly<Record<string, string>>
      /** 场景预置操作，按顺序在首轮之前执行。 */
      readonly setup?: readonly SetupOperation[]
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
