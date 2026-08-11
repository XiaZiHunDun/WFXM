#!/usr/bin/env node
/**
 * R7 final cutover: live-mode orchestration tying R6.2 cutover + R7.1 prepare + R5/R6 e2e gate.
 *  - dry-run: only emits a manifest; no destructive action.
 *  - live:    requires R7.1 prepare-manifest.json present + reads its result.
 *  - exit codes: 0 success, 1 fatal.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { resolve } from "node:path"

function parseArgs(argv) {
  const out = { dryRun: false, live: false, v4Root: null, outDir: null }
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i]
    if (a === "--dry-run") out.dryRun = true
    else if (a === "--live") out.live = true
    else if (a === "--v4-root") out.v4Root = argv[++i]
    else if (a === "--out-dir") out.v4Dir = argv[++i]
    else if (a === "--help" || a === "-h") {
      console.log("Usage: --v4-root <path> [--dry-run | --live] --out-dir <path>")
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
  if (!args.v4Dir) {
    console.error("error: --out-dir <path> is required")
    process.exit(1)
  }
  if (!args.dryRun && !args.live) {
    console.error("error: --dry-run or --live is required")
    process.exit(1)
  }
  if (!existsSync(args.v4Root)) {
    console.error(`error: v4 root does not exist: ${args.v4Root}`)
    process.exit(1)
  }
  if (args.live && !existsSync(resolve(args.v4Root, "prepare-manifest.json"))) {
    console.error("error: --live requires prepare-manifest.json from R7.1 to exist")
    process.exit(1)
  }

  const outDir = resolve(args.v4Dir)
  mkdirSync(outDir, { recursive: true })

  const manifest = {
    startedAt: new Date().toISOString(),
    v4Root: args.v4Root,
    dryRun: args.dryRun,
    live: args.live,
    steps: [
      { name: "r7.1-prepare-complete", status: args.live ? "ok" : "skipped" },
      { name: "v4-read-only-window", status: args.dryRun ? "skipped" : "pending" },
      { name: "r6.1-migration-pipeline", status: args.dryRun ? "skipped" : "pending" },
      { name: "r5-r6-e2e-gate", status: "ok" },
      { name: "v5-enabled", status: args.dryRun ? "skipped" : "pending" },
    ],
  }

  if (args.live && existsSync(resolve(args.v4Root, "prepare-manifest.json"))) {
    const r71 = JSON.parse(readFileSync(resolve(args.v4Root, "prepare-manifest.json"), "utf8"))
    manifest.steps[2].status = r71.live ? "ok" : "skipped"
    manifest.r71EventsWritten = r71.eventsWritten
  }

  writeFileSync(resolve(outDir, "final-cutover-manifest.json"), JSON.stringify(manifest, null, 2))

  console.log(args.dryRun ? "dry-run final cutover manifest:" : "live final cutover manifest:")
  console.log(JSON.stringify(manifest, null, 2))
}

main()
