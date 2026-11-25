/**
 * Phase 6 P1: report how old the real-LLM regression baseline is.
 *
 * `tests/acceptance/scenarios/recordings/*.json` is the ground truth for
 * "did the model change behaviour?". Nothing refreshed it after models or
 * prompts moved on, so the baseline silently rots. This module only *reports*
 * age (no re-recording, no network), and `/诊断` surfaces it.
 */
import { readdir, stat } from "node:fs/promises"
import { join, resolve } from "node:path"

const DAY_MS = 24 * 60 * 60 * 1000

export interface EvalBaselineStatus {
  readonly dir: string
  readonly latest_at: string | null
  readonly age_days: number | null
  readonly stale: boolean
  readonly max_age_days: number
  readonly count: number
}

function workspaceRootFromEnv(env: Readonly<Record<string, string | undefined>>): string {
  return (env["BUTLER_V5_WORKSPACE_ROOT"] ?? process.cwd()).trim() || process.cwd()
}

/** Default: `<workspace>/tests/acceptance/scenarios/recordings`. */
export function resolveRecordingsDir(
  env: Readonly<Record<string, string | undefined>> = process.env,
): string {
  const explicit = (env["BUTLER_V5_EVAL_RECORDINGS_DIR"] ?? "").trim()
  if (explicit !== "") return resolve(workspaceRootFromEnv(env), explicit)
  return join(workspaceRootFromEnv(env), "tests/acceptance/scenarios/recordings")
}

export function maxAgeDays(
  env: Readonly<Record<string, string | undefined>> = process.env,
): number {
  const raw = Number.parseInt(env["BUTLER_V5_EVAL_BASELINE_MAX_AGE_DAYS"] ?? "", 10)
  return Number.isFinite(raw) && raw > 0 ? raw : 30
}

export async function readEvalBaseline(
  env: Readonly<Record<string, string | undefined>> = process.env,
  nowMs: number = Date.now(),
): Promise<EvalBaselineStatus> {
  const dir = resolveRecordingsDir(env)
  const maxDays = maxAgeDays(env)
  try {
    const names = (await readdir(dir)).filter((name) => name.endsWith(".json"))
    let latestMs: number | null = null
    for (const name of names) {
      const info = await stat(join(dir, name))
      if (latestMs === null || info.mtimeMs > latestMs) latestMs = info.mtimeMs
    }
    const ageDays = latestMs === null ? null : Math.max(0, Math.floor((nowMs - latestMs) / DAY_MS))
    return {
      dir,
      latest_at: latestMs === null ? null : new Date(latestMs).toISOString(),
      age_days: ageDays,
      stale: ageDays === null || ageDays > maxDays,
      max_age_days: maxDays,
      count: names.length,
    }
  } catch {
    // Missing directory is a valid state (fresh clone without recordings).
    return {
      dir,
      latest_at: null,
      age_days: null,
      stale: true,
      max_age_days: maxDays,
      count: 0,
    }
  }
}
