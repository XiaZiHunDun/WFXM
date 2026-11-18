/**
 * Composition root for the Butler Runtime.
 *
 * Wires the pieces that must not know about each other:
 *   butler model port  <- existing LLM adapter (Effect) wrapped as Promise
 *   butler task port   <- PiTaskRunner adapter (project root map, approvals)
 *   memory ports       <- injected by the caller (agent-rag adapters)
 *   session store      <- Drizzle (butler_sessions) or an injected store
 *
 * Memory stays an injection point on purpose: WFXM does not import agent-rag.
 */
import { Effect } from "effect"
import { pickLLMForRole, type LLMAdapter, type LLMMessage, type LLMTool } from "@butler/adapters"
import { DrizzleButlerSessionStore, type ButlerDb } from "@butler/persistence"
import type { ButlerMemoryPort } from "@butler/ports/core/butler-memory.js"
import type { ButlerMessage, ButlerSessionStore } from "@butler/ports/core/butler-session.js"
import type { PiTaskSessionStore } from "@butler/ports/core/pi-task-session.js"
import type { TaskMemoryPort } from "@butler/ports/core/task-memory.js"
import { ButlerRuntime } from "@butler/runtime/butler/butler-runtime.js"
import type { ButlerModelPort, ButlerToolSpec } from "@butler/runtime/butler/model-port.js"
import {
  createPiTaskPortAdapter,
  type PiTaskPortAdapter,
} from "@butler/runtime/butler/pi-task-adapter.js"
import type { PiTaskRunner } from "@butler/runtime/execution/pi-task-runner.js"

function toLlmMessages(messages: readonly ButlerMessage[]): readonly LLMMessage[] {
  return messages.map((message) => ({
    role: message.role,
    content: message.content,
    ...(message.toolCalls === undefined
      ? {}
      : {
          toolCalls: message.toolCalls.map((call) => ({
            id: call.id,
            name: call.name,
            args: { ...call.args },
          })),
        }),
    ...(message.toolCallId === undefined ? {} : { toolCallId: message.toolCallId }),
    ...(message.toolName === undefined ? {} : { toolName: message.toolName }),
  }))
}

function toLlmTools(tools: readonly ButlerToolSpec[]): readonly LLMTool[] {
  return tools.map((tool) => ({
    name: tool.name,
    description: tool.description,
    parameters: {
      type: "object",
      ...(tool.parameters.properties === undefined
        ? {}
        : { properties: { ...tool.parameters.properties } }),
      ...(tool.parameters.required === undefined
        ? {}
        : { required: [...tool.parameters.required] }),
    },
  }))
}

/** Wraps the Effect-based LLM adapter into the butler's Promise port. */
export function createButlerModelPort(adapter: LLMAdapter): ButlerModelPort {
  return {
    async complete({ messages, tools }) {
      const response = await Effect.runPromise(
        adapter.complete(toLlmMessages(messages), {
          ...(tools === undefined ? {} : { tools: toLlmTools(tools) }),
        }),
      )
      const toolCalls = response.toolCalls.map((call) => ({
        id: call.id,
        name: call.name,
        args: { ...call.args },
      }))
      return {
        content: response.content,
        ...(toolCalls.length === 0 ? {} : { toolCalls }),
        ...(response.usage === undefined ? {} : { usage: response.usage }),
      }
    },
  }
}

export interface ButlerAssemblyOptions {
  readonly env?: NodeJS.ProcessEnv
  /** Durable session store source; ignored when `sessionStore` is provided. */
  readonly db?: ButlerDb
  readonly sessionStore?: ButlerSessionStore
  /** projectId -> workspace root. Tasks for unknown projects are rejected. */
  readonly projects: Readonly<Record<string, string>>
  /** Defaults to the "plan" role from the existing model router. */
  readonly butlerAdapter?: LLMAdapter
  readonly butlerMemory?: ButlerMemoryPort
  /** Attached when the assembly builds the runner; injected runners own theirs. */
  readonly taskMemory?: TaskMemoryPort
  /** Tests / custom deployments can inject a prepared runner. */
  readonly taskRunner?: PiTaskRunner
  readonly taskSessionStore?: PiTaskSessionStore
  readonly detachedTasks?: boolean
  readonly newTaskId?: (projectId: string) => string
  readonly taskTimeoutMs?: number
  readonly systemPrompt?: string
  readonly logger?: { warn(message: string, extra?: unknown): void }
}

export interface ButlerAssembly {
  readonly butler: ButlerRuntime
  readonly tasks: PiTaskPortAdapter
  readonly runner: PiTaskRunner
}

/**
 * Builds the assembly.
 *
 * The pi runner is imported lazily: pi ships ESM-only root exports, and this
 * module is reachable from the CJS eval harness. Loading pi eagerly would crash
 * that harness even when no butler task is ever started.
 */
export async function createButlerAssembly(
  options: ButlerAssemblyOptions,
): Promise<ButlerAssembly> {
  const env = options.env ?? process.env
  const sessionStore =
    options.sessionStore ?? (options.db ? new DrizzleButlerSessionStore(options.db) : undefined)
  if (!sessionStore) {
    throw new Error("butler assembly requires either db or sessionStore")
  }

  let runner = options.taskRunner
  if (!runner) {
    const { createPiStreamFn, resolvePiModelFromEnv } =
      await import("@butler/runtime/execution/pi-model.js")
    const { PiTaskRunner } = await import("@butler/runtime/execution/pi-task-runner.js")
    const config = resolvePiModelFromEnv(env)
    runner = new PiTaskRunner({
      model: config.model,
      apiKey: config.apiKey,
      streamFn: createPiStreamFn({ model: config.model, apiKey: config.apiKey }),
      ...(options.taskSessionStore === undefined ? {} : { store: options.taskSessionStore }),
      ...(options.taskMemory === undefined ? {} : { memory: options.taskMemory }),
      ...(options.logger === undefined ? {} : { logger: options.logger }),
    })
  }

  const tasks = createPiTaskPortAdapter(runner, {
    resolveCwd: (projectId) => {
      const root = options.projects[projectId]
      if (!root) throw new Error(`unknown project: ${projectId}`)
      return root
    },
    ...(options.newTaskId === undefined ? {} : { newTaskId: options.newTaskId }),
    ...(options.taskTimeoutMs === undefined ? {} : { timeoutMs: options.taskTimeoutMs }),
    ...(options.detachedTasks === undefined ? {} : { detached: options.detachedTasks }),
    ...(options.logger === undefined ? {} : { logger: options.logger }),
  })

  const butlerAdapter = options.butlerAdapter ?? pickLLMForRole(env, "plan")
  if (!butlerAdapter) {
    throw new Error("no LLM adapter configured for the butler runtime")
  }

  const butler = new ButlerRuntime({
    model: createButlerModelPort(butlerAdapter),
    tasks,
    store: sessionStore,
    ...(options.butlerMemory === undefined ? {} : { memory: options.butlerMemory }),
    ...(options.systemPrompt === undefined ? {} : { systemPrompt: options.systemPrompt }),
    ...(options.logger === undefined ? {} : { logger: options.logger }),
  })

  return { butler, tasks, runner }
}
