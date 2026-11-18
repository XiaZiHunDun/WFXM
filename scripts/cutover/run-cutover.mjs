#!/usr/bin/env node
/**
 * R6 Cutover orchestrator (dry-run only — live cutover is R6.3+ scope).
 *
 * Steps (all flagged behind --dry-run):
 *   1. v4 read-only window
 *   2. final delta import
 *   3. manifest verification
 *   4. v5 start (no-op in dry-run)
 *   5. smoke test (no-op in dry-run)
 *
 * Usage:
 *   node scripts/cutover/run-cutover.mjs --v4-root <path> [--dry-run] [--write-manifest] [--out-dir <path>]
 *
 * Exits 0 on success, 1 on fatal error.
 */
import { existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs"
import { resolve } from "node:path"

function parseArgs(argv) {
  const out = { dryRun: false, writeManifest: false, v4Root: null, outDir: null }
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i]
    if (a === "--dry-run") out.dryRun = true
    else if (a === "--write-manifest") out.writeManifest = true
    else if (a === "--v4-root") out.v4Root = argv[++i]
    else if (a === "--out-dir") out.outDir = argv[++i]
    else if (a === "--help" || a === "-h") {
      console.log("Usage: --v4-root <path> [--dry-run] [--write-manifest] [--out-dir <path>]")
    }
  }
  return out
}

function main() {
  const args = parseArgs(process.argv)
  if (!args.v4Root) {
    console.error("error: --v4-root <path> is required")
    process.exit(1)
  }
  if (!existsSync(args.v4Root)) {
    console.error(`error: v4 root does not exist: ${args.v4Root}`)
    process.exit(1)
  }

  const outDir = resolve(args.outDir ?? "./cutover-out")
  rmSync(outDir, { recursive: true, force: true })
  mkdirSync(outDir, { recursive: true })

  const manifest = {
    startedAt: new Date().toISOString(),
    v4Root: args.v4Root,
    dryRun: args.dryRun,
    steps: [
      {
        name: "v4-read-only-window",
        status: "skipped",
        reason: args.dryRun ? "dry-run" : "would-stop-v4-writes",
      },
      {
        name: "final-delta-import",
        status: "skipped",
        reason: args.dryRun ? "dry-run" : "r6.1-pipeline-not-run",
      },
      {
        name: "manifest-verification",
        status: "skipped",
        reason: args.dryRun ? "dry-run" : "no-events-written",
      },
      {
        name: "v5-start",
        status: "skipped",
        reason: args.dryRun ? "dry-run" : "smoke-test-required-first",
      },
      {
        name: "smoke-test",
        status: "skipped",
        reason: args.dryRun ? "dry-run" : "no-v5-deployment-yet",
      },
    ],
    eventsWritten: 0,
  }

  if (args.writeManifest) {
    writeFileSync(resolve(outDir, "cutover-manifest.json"), JSON.stringify(manifest, null, 2))
  }

  console.log(args.dryRun ? "dry-run cutover manifest:" : "cutover manifest:")
  console.log(JSON.stringify(manifest, null, 2))
}

main()
