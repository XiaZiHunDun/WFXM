import { spawn } from "node:child_process"
import type { StdioSpawnFn } from "@butler/adapters/mcp/stdio-transport.js"
import { isSandboxEnabled, currentSandboxProfileName } from "@butler/runtime/sandbox/index.js"
import { buildBubblewrapArgs, resolveSandboxProfile } from "@butler/adapters/sandbox/bubblewrap-runner.js"
import { recordExecAudit, type ExecAuditContext } from "./exec-audit.js"

/**
 * Production stdio spawn for MCP subprocess servers.
 *
 * R16 sandbox 扩面：当 `BUTLER_V5_SANDBOX=bubblewrap` 时，把 MCP server
 * 包到 bwrap 内（workspace --bind RW、--unshare-net、--die-with-parent），
 * 复用现有 bwrap primitive + `executeArgvInSandbox` 等价的 inline spawn
 * 路径（不走 `runInBubblewrap:403-405` argv[0] includes("/") 校验——MCP
 * command 来自 manifest `mcp-config.ts:121-124` 信任源，绝对路径合法）。
 *
 * ARCH GUARD: tests/architecture/mcp-spawn-arch.test.ts 锁住
 * `isSandboxEnabled` check 必须在 bare `spawn` 之前出现。
 *
 * Fallback: bwrap 关闭时维持现状裸 spawn（Q6 — 部署兼容）。
 */
export const nodeStdioSpawn: StdioSpawnFn = (command, args, options) => {
  // BUTLER_V5_SANDBOX 是宿主控制开关（控制当前 Node 进程行为），不应被
  // `options.env`（子进程环境）覆盖；否则 caller 显式传空 env 会绕开 bwrap。
  // 与 `executeArgvInSandbox` 的 host-side 读取模式一致（workspace-tools.ts:254）。
  const hostEnv = globalThis.process.env
  let child: ReturnType<typeof spawn>
  if (isSandboxEnabled(hostEnv)) {
    const ws = (hostEnv["BUTLER_V5_SANDBOX_WORKSPACE_ROOT"] ?? "").trim() || process.cwd()
    const profile = resolveSandboxProfile({
      workspaceRoot: ws,
      profileName: currentSandboxProfileName() ?? "workspace-write-network-deny",
    })
    const bwrapArgs = buildBubblewrapArgs(profile, [command, ...args], { readOnly: false })
    child = spawn("bwrap", bwrapArgs, {
      stdio: ["pipe", "pipe", "pipe"],
      env: { PATH: hostEnv["PATH"] ?? "/usr/bin:/bin" },
    })
  } else {
    child = spawn(command, [...args], {
      stdio: ["pipe", "pipe", "pipe"],
      env: options.env,
    })
  }
  const lineHandlers: ((line: string) => void)[] = []
  let buffer = ""
  child.stdout?.on("data", (chunk: Buffer) => {
    buffer += chunk.toString("utf8")
    let idx = buffer.indexOf("\n")
    while (idx >= 0) {
      const line = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 1)
      for (const handler of lineHandlers) {
        handler(line)
      }
      idx = buffer.indexOf("\n")
    }
  })
  return {
    writeLine: (line: string) => {
      child.stdin?.write(`${line}\n`)
    },
    onLine: (handler) => {
      lineHandlers.push(handler)
    },
    kill: () => {
      child.kill("SIGTERM")
    },
  }
}

/**
 * D47 exec audit: MCP stdio server spawn with behavior audit accounting.
 * Records one `exec.executed` event at spawn time (outcome "spawned";
 * exit is unknown for a long-lived server). Reuses `nodeStdioSpawn` so
 * sandbox gating is unchanged. Audit is observation only — it never
 * blocks the spawn and never issues permissions.
 */
export function makeNodeStdioSpawn(audit?: ExecAuditContext): StdioSpawnFn {
  return (command, args, options) => {
    void recordExecAudit(audit, {
      cmd: [command, ...args].join(" "),
      cwd: process.cwd(),
      exit: null,
      durationMs: 0,
      outcome: "spawned",
      detail: { kind: "mcp-server" },
    })
    return nodeStdioSpawn(command, args, options)
  }
}
