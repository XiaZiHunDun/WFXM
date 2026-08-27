#!/usr/bin/env node
// hooks/pre-tool-use.js
// PreToolUse 钩子 — 在 AI 工具执行 Edit/Write/DeleteFile 之前运行
// 检查受保护文件、危险模式、跨层导入等

import { readFileSync, existsSync } from "node:fs"
import { resolve, relative } from "node:path"
import { exit } from "node:process"

const PROTECTED_FILES = [
  "packages/domain/src/errors.ts",
  "packages/ports/src/index.ts",
  ".cursorrules",
  "AGENTS.md",
  ".butler/scope-boundaries.json",
  ".butler/load-bearing-marks.json",
]

const DANGEROUS_PATTERNS = [
  { pattern: /from\s+['"].*import\s+\*['"]/, severity: "BLOCK", message: "禁止 `import *` 模式" },
  { pattern: /export\s+\*\s+from/, severity: "PASS", message: "barrel 文件 export * 合法" },
  { pattern: /\bthrow\s+new\s+Error/, severity: "WARN", message: "建议用 Effect.fail 替代 throw" },
  { pattern: /new\s+Map\(\)/, severity: "WARN", message: "模块级可变状态，应放在 Layer 内部" },
  { pattern: /as\s+any\b/, severity: "WARN", message: "避免使用 any 类型断言" },
]

// 从 stdin 读取工具调用信息
function readStdin() {
  try {
    const input = readFileSync(0, "utf-8")
    return JSON.parse(input)
  } catch {
    return null
  }
}

function checkProtectedFiles(filePath) {
  const rel = relative(process.cwd(), resolve(filePath))
  for (const pf of PROTECTED_FILES) {
    if (rel === pf || rel.endsWith(pf)) {
      return {
        blocked: true,
        reason: `受保护文件禁止修改: ${pf}。如需修改请使用 [MANUAL-OVERRIDE] 标记。`,
      }
    }
  }
  return { blocked: false }
}

function checkDangerousPatterns(content) {
  const findings = []
  for (const check of DANGEROUS_PATTERNS) {
    if (check.severity === "PASS") continue
    if (check.pattern.test(content)) {
      findings.push({
        severity: check.severity,
        message: check.message,
      })
    }
  }
  return findings
}

function checkLayerImports(filePath, content) {
  const rel = relative(process.cwd(), resolve(filePath))
  const findings = []

  if (rel.includes("packages/domain/") && content.includes("@butler/infrastructure")) {
    findings.push({ severity: "BLOCK", message: "domain 层不能导入 infrastructure 层" })
  }
  if (rel.includes("packages/domain/") && content.includes("@butler/application")) {
    findings.push({ severity: "BLOCK", message: "domain 层不能导入 application 层" })
  }
  if (rel.includes("packages/ports/") && content.includes("@butler/infrastructure")) {
    findings.push({ severity: "BLOCK", message: "ports 层不能导入 infrastructure 层" })
  }
  if (rel.includes("packages/ports/") && content.includes("@butler/application")) {
    findings.push({ severity: "BLOCK", message: "ports 层不能导入 application 层" })
  }
  if (
    (rel.includes("packages/infrastructure/") || rel.includes("_archive/packages/infrastructure/")) &&
    content.includes("@butler/application")
  ) {
    findings.push({ severity: "BLOCK", message: "infrastructure 层不能导入 application 层" })
  }

  return findings
}

// ─── 主逻辑 ─────────────────────────────────────────────
const toolCall = readStdin()

if (!toolCall) {
  console.log(JSON.stringify({ allow: true }))
  exit(0)
}

const filePath = toolCall.file_path || toolCall.path || ""
const toolName = toolCall.tool_name || ""

// 只对 Edit/Write/DeleteFile 做检查
if (!["Edit", "Write", "DeleteFile"].includes(toolName)) {
  console.log(JSON.stringify({ allow: true }))
  exit(0)
}

// 1. 检查受保护文件
const protectedCheck = checkProtectedFiles(filePath)
if (protectedCheck.blocked) {
  console.log(
    JSON.stringify({
      allow: false,
      reason: protectedCheck.reason,
    }),
  )
  exit(0)
}

// 2. 检查文件内容（如果存在）
if (existsSync(filePath)) {
  const content = readFileSync(filePath, "utf-8")

  const dangerousPatterns = checkDangerousPatterns(content)
  const layerViolations = checkLayerImports(filePath, content)

  const blockFindings = [
    ...dangerousPatterns.filter((f) => f.severity === "BLOCK"),
    ...layerViolations.filter((f) => f.severity === "BLOCK"),
  ]

  if (blockFindings.length > 0) {
    console.log(
      JSON.stringify({
        allow: false,
        reason: blockFindings.map((f) => f.message).join("; "),
      }),
    )
    // eslint-disable-next-line no-undef
    process.exit(0)
  }

  const warnFindings = [
    ...dangerousPatterns.filter((f) => f.severity === "WARN"),
    ...layerViolations.filter((f) => f.severity === "WARN"),
  ]

  if (warnFindings.length > 0) {
    console.log(
      JSON.stringify({
        allow: true,
        warnings: warnFindings.map((f) => f.message),
      }),
    )
    // eslint-disable-next-line no-undef
    process.exit(0)
  }
}

// 所有检查通过
console.log(JSON.stringify({ allow: true }))
// eslint-disable-next-line no-undef
process.exit(0)
