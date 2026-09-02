/**
 * T2/T3 async acceptance helpers — poll mock notify outbox and project state.
 */
import { readFileSync, existsSync } from "node:fs"

export async function waitForCondition(
  predicate: () => Promise<boolean>,
  opts: { readonly timeoutMs?: number; readonly intervalMs?: number } = {},
): Promise<boolean> {
  const timeoutMs = opts.timeoutMs ?? 120_000
  const intervalMs = opts.intervalMs ?? 50
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (await predicate()) return true
    await new Promise((resolve) => setTimeout(resolve, intervalMs))
  }
  return predicate()
}

export function readMockNotifyOutbox(path: string): readonly Record<string, unknown>[] {
  if (!existsSync(path)) return []
  return readFileSync(path, "utf8")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line) as Record<string, unknown>)
}

export async function pollMockOutboxForText(args: {
  readonly path: string
  readonly includes: string
  readonly timeoutMs?: number
}): Promise<readonly Record<string, unknown>[]> {
  let last: readonly Record<string, unknown>[] = []
  const ok = await waitForCondition(async () => {
    last = readMockNotifyOutbox(args.path)
    return last.some((entry) => JSON.stringify(entry).includes(args.includes))
  }, { timeoutMs: args.timeoutMs ?? 120_000 })
  if (!ok) {
    throw new Error(
      `mock outbox timeout: missing "${args.includes}" in ${args.path} (${last.length} lines)`,
    )
  }
  return last
}

