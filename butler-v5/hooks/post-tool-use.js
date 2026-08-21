#!/usr/bin/env node
// hooks/post-tool-use.js
// PostToolUse 钩子 — 在 AI 工具 Edit/Write 后自动运行相关测试
// 超时 30s，仅运行受影响的测试子集

import { execSync } from "node:child_process"
import { readFileSync } from "node:fs"
import { relative, resolve } from "node:path"
import { exit } from "node:process"

const TEST_TIMEOUT_MS = 30_000

// 从 stdin 读取工具调用结果
function readStdin() {
  try {
    const input = readFileSync(0, "utf-8")
    return JSON.parse(input)
  } catch {
    return null
  }
}

// 根据被修改的文件路径决定运行哪些测试
function getTestSubset(filePath) {
  const rel = relative(process.cwd(), resolve(filePath))

  if (rel.includes("packages/domain/src/guards/")) {
    return "packages/domain/src/guards/pure.test.ts packages/infrastructure/_archive/guards/guard-service.test.ts"
  }
  if (rel.includes("packages/domain/src/conversation/")) {
    return "packages/domain/src/conversation/transitions.test.ts packages/domain/src/conversation/context.test.ts"
  }
  if (rel.includes("packages/domain/src/workflows/")) {
    return "packages/domain/src/workflows/transitions.test.ts"
  }
  if (rel.includes("packages/domain/src/errors.ts")) {
    return "packages/domain/src/errors.test.ts"
  }
  if (rel.includes("packages/domain/src/memory/")) {
    return "packages/domain/src/memory/pure.test.ts"
  }
  if (rel.includes("packages/domain/src/permissions/")) {
    return "packages/domain/src/permissions/decidePermission.test.ts"
  }
  if (rel.includes("packages/application/_archive/run-loop/")) {
    return "packages/application/_archive/run-loop/run-loop.test.ts"
  }
  if (rel.includes("packages/application/_archive/delegate-task/")) {
    return "packages/application/_archive/delegate-task/delegate-task.test.ts"
  }
  if (rel.includes("packages/application/_archive/run-workflow/")) {
    return "packages/application/_archive/run-workflow/run-workflow.test.ts"
  }
  if (rel.includes("packages/application/_archive/dream/")) {
    return "packages/application/_archive/dream/dream.test.ts"
  }
  if (rel.includes("packages/infrastructure/_archive/guards/")) {
    return "packages/infrastructure/_archive/guards/guard-service.test.ts"
  }
  if (rel.includes("packages/infrastructure/_archive/wechat/")) {
    return "packages/infrastructure/_archive/wechat/wechat.test.ts"
  }
  if (rel.includes("packages/infrastructure/_archive/mcp/")) {
    return "packages/infrastructure/_archive/mcp/mcp.test.ts"
  }
  if (rel.includes("packages/infrastructure/_archive/persistence/")) {
    return "packages/infrastructure/_archive/persistence/eventstore.test.ts"
  }
  if (rel.includes("packages/config/")) {
    return "packages/config/"
  }

  // 默认：运行所有测试
  return ""
}

// ─── 主逻辑 ─────────────────────────────────────────────
const toolResult = readStdin()

if (!toolResult) {
  exit(0)
}

const filePath = toolResult.file_path || toolResult.path || ""
const toolName = toolResult.tool_name || ""

// 只对 Edit/Write 做测试
if (!["Edit", "Write"].includes(toolName)) {
  exit(0)
}

const testSubset = getTestSubset(filePath)

if (!testSubset) {
  // 没有匹配的测试子集，跳过
  console.log("[PostToolUse] 未找到对应测试子集，跳过自动测试")
  exit(0)
}

try {
  console.log(`[PostToolUse] 运行测试子集: ${testSubset}`)
  execSync(`pnpm vitest run ${testSubset} --reporter=verbose`, {
    cwd: process.cwd(),
    timeout: TEST_TIMEOUT_MS,
    stdio: "inherit",
  })
  console.log("[PostToolUse] 测试通过")
} catch (err) {
  console.error(`[PostToolUse] 测试失败: ${err.message}`)
  // 不阻塞，仅警告
  exit(0)
}
