import { spawn } from "node:child_process"
import type { StdioSpawnFn } from "@butler/adapters/mcp/stdio-transport.js"

/** Production stdio spawn for MCP subprocess servers. */
export const nodeStdioSpawn: StdioSpawnFn = (command, args, options) => {
  const child = spawn(command, [...args], {
    stdio: ["pipe", "pipe", "pipe"],
    env: options.env,
  })
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
