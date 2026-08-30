/**
 * Arch guard (D17-arch-align §16 process boundary): 进程拆分不改
 * 变模块、端口和权限边界，也不引入第二套 Run Engine。
 *
 * Subprocess runners (bubblewrap, slirp, MCP server, migration shadow)
 * must NOT import Core engine modules. Importing `@butler/runtime/execution`,
 * `decision`, `agent-kernel`, or `run-engine` would mean the subprocess
 * is running its own LLM / policy / loop — a second Run Engine.
 *
 * Audit findings (D17, 2026-08-30):
 *   - packages/adapters/src/sandbox/bubblewrap-runner.ts — sandbox exec
 *     only (spawn + capture stdout/stderr); no LLM, no policy. Imports
 *     domain governance for network allowlist, runtime/sandbox for
 *     profile config — allowed.
 *   - packages/adapters/src/sandbox/slirp-egress.ts — network namespace
 *     setup only (slirp4netns + iptables); no LLM, no policy.
 *   - apps/api/src/mcp-spawn.ts — MCP server spawn (stdio); the spawned
 *     MCP server is a Capability provider, NOT a Run Engine. Per §9
 *     "MCP 是注册远程副作用 Capability 的适配器".
 *   - packages/migration/src/shadow-runner.ts — v4 → v5 migration
 *     shadow comparison; NOT in production runtime path.
 *
 * Static checks (no runtime):
 *   - Each subprocess runner must NOT import `@butler/runtime/execution`
 *     (the canonical conversation loop) — would imply running a second
 *     engine in the subprocess.
 *   - Each subprocess runner must NOT import `decision` or `agent-kernel`
 *     or `run-engine` modules — would imply second engine.
 *   - Each subprocess runner must NOT import `runButlerLoop`,
 *     `runConversationLoop`, or any LLM adapter directly.
 *
 * Runtime behavior is verified by:
 *   - sandbox-related tests under packages/adapters/src/sandbox/
 *     (sandbox runner lifecycle, network allowlist resolution)
 *   - tests/architecture/mcp-spawn-arch.test.ts (D17 sibling; locks the
 *     bwrap-or-bare-spawn ordering for MCP stdio)
 */

import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { join } from "node:path"

const SUBPROCESS_RUNNERS: readonly string[] = [
  join(
    __dirname,
    "../../packages/adapters/src/sandbox/bubblewrap-runner.ts",
  ),
  join(__dirname, "../../packages/adapters/src/sandbox/slirp-egress.ts"),
  join(__dirname, "../../apps/api/src/mcp-spawn.ts"),
  join(__dirname, "../../packages/migration/src/shadow-runner.ts"),
]

/** Forbidden imports — each one signals that the subprocess runner
 *  is running a second Run Engine or making policy decisions outside
 *  the canonical Core. */
const FORBIDDEN_IMPORT_PATTERNS: readonly RegExp[] = [
  /from\s+["']@butler\/runtime\/execution[^"']*["']/, // canonical loop
  /from\s+["']@butler\/runtime\/agent-kernel[^"']*["']/, // kernel
  /from\s+["']@butler\/runtime\/run-engine[^"']*["']/, // engine
  /from\s+["']@butler\/runtime\/decision[^"']*["']/, // decision ADT
  /from\s+["']@butler\/runtime\/policy-gate[^"']*["']/, // policy
  /from\s+["']@butler\/runtime\/capability-boundary[^"']*["']/, // boundary
  /from\s+["']@butler\/runtime\/scoped-grant-service[^"']*["']/, // grant service
  /from\s+["'][^"']*runtime\/execution\/conversation-loop[^"']*["']/,
  /from\s+["']@butler\/adapters\/llm-provider[^"']*["']/, // LLM adapter
  /from\s+["']@butler\/adapters\/llm\/anthropic[^"']*["']/,
  /from\s+["']@butler\/adapters\/llm\/openai-compatible[^"']*["']/,
  /from\s+["']@butler\/domain\/runtime\/delegate-runtime[^"']*["']/, // delegate
  /from\s+["']@butler\/domain\/runtime\/run-trigger[^"']*["']/,
]

/** Each subprocess runner is allowed these imports (legitimate boundary
 *  config). Anything else needs review. */
const ALLOWED_IMPORT_SUBSTRINGS: Readonly<Record<string, readonly RegExp[]>> = {
  [join(__dirname, "../../packages/adapters/src/sandbox/bubblewrap-runner.ts")]:
    [
      /@butler\/domain\/governance\/network-allowlist/, // governance config
      /@butler\/runtime\/sandbox/, // sandbox profile helpers
      /@butler\/adapters\/sandbox\//, // sibling sandbox primitives
      /@butler\/domain\/governance\/mcp-tool-capability/, // mcp gating
      /node:child_process/,
      /node:fs/,
      /node:path/,
    ],
  [join(__dirname, "../../packages/adapters/src/sandbox/slirp-egress.ts")]: [
    /@butler\/adapters\/sandbox\//, // sibling sandbox primitives
    /node:child_process/,
    /node:dns/,
    /node:fs/,
    /node:os/,
    /node:path/,
  ],
  [join(__dirname, "../../apps/api/src/mcp-spawn.ts")]: [
    /@butler\/adapters\/mcp\//, // mcp transport primitives
    /@butler\/runtime\/sandbox/, // sandbox profile for MCP stdio
    /@butler\/adapters\/sandbox\//, // sibling sandbox primitives
    /node:child_process/,
  ],
  [join(__dirname, "../../packages/migration/src/shadow-runner.ts")]: [
    /\.\/v4-source/, // local sibling
    /node:fs/,
    /node:path/,
  ],
}

describe("arch: §16 process boundary (no second Run Engine in subprocess runners)", () => {
  for (const file of SUBPROCESS_RUNNERS) {
    it(`${file.split("/").pop()} must NOT import Core (no second Run Engine)`, () => {
      const src = readFileSync(file, "utf-8")
      const violations: string[] = []
      for (const pattern of FORBIDDEN_IMPORT_PATTERNS) {
        const match = src.match(pattern)
        if (match) {
          violations.push(`${pattern.source} → ${match[0]}`)
        }
      }
      expect(
        violations,
        `${file} imports Core modules — would mean a second Run Engine: ${violations.join(", ")}`,
      ).toEqual([])
    })
  }

  it("subprocess runners may only import the boundary-config layer (governance / sandbox / mcp / child_process)", () => {
    // Each subprocess runner's imports should fall into the allowed list
    // for that file. This catches drift when someone adds a "helpful"
    // import from `@butler/runtime` or `@butler/domain/runtime`.
    for (const file of SUBPROCESS_RUNNERS) {
      const src = readFileSync(file, "utf-8")
      const allowed = ALLOWED_IMPORT_SUBSTRINGS[file] ?? []
      const importRegex = /from\s+["']([^"']+)["']/g
      const violations: string[] = []
      let match: RegExpExecArray | null
      while ((match = importRegex.exec(src)) !== null) {
        const spec = match[1] ?? ""
        // Skip relative + node: imports; only flag @butler/* and local
        // workspace imports.
        if (spec.startsWith(".")) continue
        if (spec.startsWith("node:")) continue
        if (!spec.startsWith("@butler/")) continue
        const matched = allowed.some((re) => re.test(spec))
        if (!matched) {
          violations.push(spec)
        }
      }
      expect(
        violations,
        `${file} has imports outside the allowed boundary list: ${violations.join(", ")}`,
      ).toEqual([])
    }
  })
})