/**
 * C2 app-layer approval preview: reads the previous file content for a
 * readable diff and renders the command line. Gated by
 * BUTLER_V5_APPROVAL_PREVIEW so the default behavior stays byte-identical.
 */
import { readFileSync, statSync } from "node:fs"
import { renderApprovalPreview } from "@butler/runtime/approval-preview.js"
import { redactSecretText } from "@butler/runtime/secret-redact.js"
import { envTruthy } from "./env-util.js"
import { resolveUnderWorkspace } from "./workspace-tools.js"

const MAX_PREVIEW_FILE_BYTES = 256 * 1024

export function isApprovalPreviewEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return envTruthy(env["BUTLER_V5_APPROVAL_PREVIEW"])
}

function previousWriteFileContent(
  path: string,
  workspaceRoot: string,
): { readonly ok: true; readonly content: string | null | undefined } | { readonly ok: false } {
  const resolved = resolveUnderWorkspace(workspaceRoot, path)
  if (!resolved.ok) return { ok: false }
  try {
    const stat = statSync(resolved.path)
    if (!stat.isFile() || stat.size > MAX_PREVIEW_FILE_BYTES)
      return { ok: true, content: undefined }
    return { ok: true, content: readFileSync(resolved.path, "utf8") }
  } catch (err) {
    // Missing file = new file; other read errors leave the diff unknown.
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return { ok: true, content: null }
    return { ok: true, content: undefined }
  }
}

function writeFilePreview(args: {
  readonly args: Readonly<Record<string, unknown>>
  readonly workspaceRoot?: string
}): string | null {
  const path = typeof args.args["path"] === "string" ? args.args["path"] : ""
  if (!path.trim()) return null
  const workspaceRoot =
    args.workspaceRoot ?? process.env["BUTLER_V5_WORKSPACE_ROOT"] ?? process.cwd()
  const previous = previousWriteFileContent(path, workspaceRoot)
  if (!previous.ok) return null
  return renderApprovalPreview({
    capability: "write_file",
    args: args.args,
    ...(previous.content === undefined ? {} : { oldContent: previous.content }),
    workspaceRoot,
  })
}

/** Best-effort preview; any failure returns null so approval keeps old wording. */
export function buildToolApprovalPreview(args: {
  readonly capability: string
  readonly args: Readonly<Record<string, unknown>>
  readonly workspaceRoot?: string
  readonly env?: NodeJS.ProcessEnv
}): string | null {
  const env = args.env ?? process.env
  if (!isApprovalPreviewEnabled(env)) return null
  if (args.capability !== "write_file" && args.capability !== "run_command") return null
  try {
    const preview =
      args.capability === "run_command"
        ? renderApprovalPreview({ capability: "run_command", args: args.args })
        : writeFilePreview(args)
    return preview === null ? null : redactSecretText(preview)
  } catch (err) {
    // eslint-disable-next-line no-console -- operator log; preview must never block approval
    console.error(
      "[approval-preview] render failed:",
      err instanceof Error ? err.message : String(err),
    )
    return null
  }
}
