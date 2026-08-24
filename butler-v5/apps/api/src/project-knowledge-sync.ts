/**
 * Sync Project Knowledge from sources manifest (K1.1).
 * Text paths → file_snapshot; binary/office → markitdown MCP → document → ingested_document.
 */
import { readFileSync, statSync } from "node:fs"
import { basename } from "node:path"
import { ingestDocumentRecord } from "@butler/domain/knowledge/document-ingest.js"
import {
  createProjectKnowledgeRecord,
  projectKnowledgeFromDocument,
} from "@butler/domain/knowledge/project-knowledge.js"
import {
  resolveManifestSourceFiles,
  type ProjectKnowledgeSourcesManifest,
} from "@butler/domain/knowledge/project-knowledge-sources.js"
import type { ProjectKnowledgeStore } from "@butler/persistence"
import type { ToolDefinition } from "@butler/runtime/tool-runtime.js"
import { listWorkspaceFilesForGlob } from "./project-knowledge-glob.js"
import { resolveUnderWorkspace, workspaceRootFrom } from "./workspace-tools.js"
import type { Wiring } from "./wiring.js"

export type ProjectKnowledgeSyncStats = {
  readonly scanned: number
  readonly created: number
  readonly updated: number
  readonly skipped: number
  readonly errors: readonly string[]
}

const MARKITDOWN_TOOL = "mcp_markitdown_convert_to_markdown"

function extractMarkitdownText(output: unknown): string | null {
  if (typeof output === "string" && output.trim()) return output
  if (output && typeof output === "object" && !Array.isArray(output)) {
    const obj = output as Record<string, unknown>
    for (const key of ["markdown", "text", "content", "output"]) {
      const val = obj[key]
      if (typeof val === "string" && val.trim()) return val
    }
  }
  return null
}

async function invokeMarkitdownTool(
  tool: ToolDefinition,
  absolutePath: string,
): Promise<{ readonly ok: true; readonly text: string } | { readonly ok: false; readonly reason: string }> {
  const uri = absolutePath.startsWith("file://") ? absolutePath : `file://${absolutePath}`
  for (const args of [{ uri }, { path: absolutePath }, { filepath: absolutePath }]) {
    const result = await tool.run(args)
    if (!result.ok) continue
    const text = extractMarkitdownText(result.output)
    if (text) return { ok: true, text }
  }
  const last = await tool.run({ uri })
  if (!last.ok) return { ok: false, reason: last.reason }
  const text = extractMarkitdownText(last.output)
  if (!text) return { ok: false, reason: "markitdown returned empty text" }
  return { ok: true, text }
}

async function upsertSnapshot(args: {
  readonly store: ProjectKnowledgeStore
  readonly projectId: string
  readonly relativePath: string
  readonly title: string
  readonly body: string
  readonly kind: "file_snapshot" | "ingested_document"
  readonly provenance: Record<string, unknown>
  readonly mtimeMs: number
  readonly size: number
  readonly nowMs: number
}): Promise<"created" | "updated" | "skipped"> {
  const existing = await args.store.findBySourcePath({
    projectId: args.projectId,
    sourcePath: args.relativePath,
  })
  if (
    existing &&
    existing.provenance.sourceMtimeMs === args.mtimeMs &&
    existing.provenance.sourceSize === args.size &&
    existing.body === args.body
  ) {
    return "skipped"
  }

  const provenance = {
    sourcePath: args.relativePath,
    sourceMtimeMs: args.mtimeMs,
    sourceSize: args.size,
    note: "project-knowledge-sources sync",
    ...args.provenance,
  }

  const created = createProjectKnowledgeRecord({
    ...(existing ? { id: existing.id } : {}),
    projectId: args.projectId,
    title: args.title,
    kind: args.kind,
    body: args.body,
    provenance,
    nowMs: args.nowMs,
  })
  if (!created.ok) {
    throw new Error(created.reason)
  }

  if (existing) {
    await args.store.update({
      ...created.value,
      createdAt: existing.createdAt,
    })
    return "updated"
  }
  await args.store.create(created.value)
  return "created"
}

export async function syncProjectKnowledgeFromManifest(args: {
  readonly wiring: Wiring
  readonly manifest: ProjectKnowledgeSourcesManifest
  readonly env?: NodeJS.ProcessEnv
  readonly nowMs?: () => number
  readonly maxFilesPerGlob?: number
}): Promise<ProjectKnowledgeSyncStats> {
  const env = args.env ?? process.env
  const store = args.wiring.projectKnowledgeStore
  if (!store) {
    return { scanned: 0, created: 0, updated: 0, skipped: 0, errors: ["project knowledge store unavailable"] }
  }

  const workspaceRoot = workspaceRootFrom({ workspaceRoot: env["BUTLER_V5_WORKSPACE_ROOT"] })
  const documentStore = args.wiring.documentStore
  const markitdownTool = args.wiring.mcp.runtimeTools.find((t) => t.name === MARKITDOWN_TOOL) ?? null

  const files = resolveManifestSourceFiles({
    manifest: args.manifest,
    listFiles: (glob) =>
      listWorkspaceFilesForGlob(workspaceRoot, glob, args.maxFilesPerGlob ?? 200),
  })

  let created = 0
  let updated = 0
  let skipped = 0
  const errors: string[] = []
  const nowMs = (args.nowMs ?? (() => Date.now()))()

  for (const file of files) {
    const resolved = resolveUnderWorkspace(workspaceRoot, file.relativePath)
    if (!resolved.ok) {
      errors.push(`${file.relativePath}: ${resolved.reason}`)
      continue
    }
    let stat: ReturnType<typeof statSync>
    try {
      stat = statSync(resolved.path)
      if (!stat.isFile()) continue
    } catch (err) {
      errors.push(
        `${file.relativePath}: ${err instanceof Error ? err.message : String(err)}`,
      )
      continue
    }

    const mtimeMs = stat.mtimeMs
    const size = stat.size
    const title = basename(file.relativePath)

    try {
      if (file.viaMarkitdown) {
        if (!markitdownTool) {
          errors.push(`${file.relativePath}: markitdown MCP tool unavailable`)
          continue
        }
        if (!documentStore) {
          errors.push(`${file.relativePath}: document store unavailable`)
          continue
        }
        const converted = await invokeMarkitdownTool(markitdownTool, resolved.path)
        if (!converted.ok) {
          errors.push(`${file.relativePath}: ${converted.reason}`)
          continue
        }
        const docCreated = ingestDocumentRecord({
          subject: "owner",
          title,
          format: "markdown",
          text: converted.text,
          provenance: {
            sourcePath: file.relativePath,
            note: "markitdown chain from project-knowledge-sources",
          },
        })
        if (!docCreated.ok) {
          errors.push(`${file.relativePath}: ${docCreated.reason}`)
          continue
        }
        const doc = await documentStore.create(docCreated.value)
        const pk = projectKnowledgeFromDocument({
          projectId: file.projectId,
          document: doc,
          title,
        })
        if (!pk.ok) {
          errors.push(`${file.relativePath}: ${pk.reason}`)
          continue
        }
        const action = await upsertSnapshot({
          store,
          projectId: file.projectId,
          relativePath: file.relativePath,
          title,
          body: pk.value.body,
          kind: "ingested_document",
          provenance: {
            documentId: doc.id,
            note: "markitdown chain from project-knowledge-sources",
          },
          mtimeMs,
          size,
          nowMs,
        })
        if (action === "created") created += 1
        else if (action === "updated") updated += 1
        else skipped += 1
        continue
      }

      const body = readFileSync(resolved.path, "utf8")
      const action = await upsertSnapshot({
        store,
        projectId: file.projectId,
        relativePath: file.relativePath,
        title,
        body,
        kind: "file_snapshot",
        provenance: {},
        mtimeMs,
        size,
        nowMs,
      })
      if (action === "created") created += 1
      else if (action === "updated") updated += 1
      else skipped += 1
    } catch (err) {
      errors.push(`${file.relativePath}: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  return {
    scanned: files.length,
    created,
    updated,
    skipped,
    errors,
  }
}
