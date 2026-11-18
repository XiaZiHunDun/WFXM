/**
 * agent-rag memory bootstrap for the Butler Runtime.
 *
 * This is the only WFXM file that imports agent-rag: the adapters are wired
 * here and injected as plain ports, so runtimes stay storage-agnostic.
 * Memory is opt-in: without BUTLER_V5_MEMORY_PATH + BUTLER_V5_OWNER_ID it is
 * disabled and the butler keeps working without recall.
 */
import { mkdir } from "node:fs/promises"
import { dirname } from "node:path"
import { createWfxmMemoryPorts, type WfxmMemoryPorts } from "@agent-rag/adapters"
import { AgentRagClient } from "@agent-rag/client"
import { JsonTextStore } from "@agent-rag/store-text"

export interface ButlerMemoryBootstrap {
  readonly ports: WfxmMemoryPorts
  readonly path: string
  readonly ownerId: string
}

export async function createButlerMemoryFromEnv(
  env: NodeJS.ProcessEnv = process.env,
): Promise<ButlerMemoryBootstrap | null> {
  const path = (env["BUTLER_V5_MEMORY_PATH"] ?? "").trim()
  const ownerId = (env["BUTLER_V5_OWNER_ID"] ?? "").trim()
  if (path.length === 0 || ownerId.length === 0) return null

  await mkdir(dirname(path), { recursive: true })
  const store = await JsonTextStore.open(path)
  const client = new AgentRagClient({ store })
  return {
    ports: createWfxmMemoryPorts({ client, ownerId }),
    path,
    ownerId,
  }
}
