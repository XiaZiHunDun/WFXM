// tests/guard/no-layer-violation.test.ts
// 守卫测试 [NEW-OPT-21] — 架构约束验证
// 验证 FC/IS 分层依赖规则，禁止跨层反向导入

import { describe, it, expect } from "vitest"
import { readFileSync, readdirSync, existsSync } from "fs"
import { resolve, relative } from "path"

const ROOT = resolve(import.meta.dirname ?? __dirname, "../..")
const PACKAGES_DIR = resolve(ROOT, "packages")

// 读取所有 .ts 源文件
function collectTsFiles(dir: string): string[] {
  const files: string[] = []
  if (!existsSync(dir)) return files
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const fullPath = resolve(dir, entry.name)
    if (entry.isDirectory() && !entry.name.startsWith(".") && entry.name !== "node_modules") {
      files.push(...collectTsFiles(fullPath))
    } else if (entry.isFile() && entry.name.endsWith(".ts") && !entry.name.endsWith(".test.ts")) {
      files.push(fullPath)
    }
  }
  return files
}

// 检查单个文件是否有跨层违规
function checkLayerViolations(filePath: string): string[] {
  const rel = relative(ROOT, filePath)
  const violations: string[] = []

  try {
    const content = readFileSync(filePath, "utf-8")

    // domain/ 不能导入任何项目包
    if (rel.includes("packages/domain/")) {
      if (content.includes("@butler/infrastructure")) {
        violations.push(`domain 层导入 @butler/infrastructure`)
      }
      if (content.includes("@butler/application")) {
        violations.push(`domain 层导入 @butler/application`)
      }
      if (content.includes("@butler/ports")) {
        violations.push(`domain 层导入 @butler/ports`)
      }
      if (content.includes("@butler/config")) {
        violations.push(`domain 层导入 @butler/config`)
      }
    }

    // ports/ 不能导入 application/ 或 infrastructure/
    if (rel.includes("packages/ports/")) {
      if (content.includes("@butler/infrastructure")) {
        violations.push(`ports 层导入 @butler/infrastructure`)
      }
      if (content.includes("@butler/application")) {
        violations.push(`ports 层导入 @butler/application`)
      }
    }

    // infrastructure/ 不能导入 application/
    if (rel.includes("packages/infrastructure/")) {
      if (content.includes("@butler/application")) {
        violations.push(`infrastructure 层导入 @butler/application`)
      }
    }
  } catch {
    // 文件读取失败，跳过
  }

  return violations
}

describe("守卫测试：架构分层约束 [NEW-OPT-21]", () => {
  it("domain/ 层不导入任何项目包（零依赖）", () => {
    const domainDir = resolve(PACKAGES_DIR, "domain/src")
    const files = collectTsFiles(domainDir)
    const allViolations: string[] = []

    for (const file of files) {
      const violations = checkLayerViolations(file)
      if (violations.length > 0) {
        allViolations.push(`${relative(ROOT, file)}: ${violations.join(", ")}`)
      }
    }

    expect(allViolations).toEqual([])
  })

  it("ports/ 层不导入 application/ 或 infrastructure/", () => {
    const portsDir = resolve(PACKAGES_DIR, "ports/src")
    const files = collectTsFiles(portsDir)
    const allViolations: string[] = []

    for (const file of files) {
      const violations = checkLayerViolations(file)
      if (violations.length > 0) {
        allViolations.push(`${relative(ROOT, file)}: ${violations.join(", ")}`)
      }
    }

    expect(allViolations).toEqual([])
  })

  it("infrastructure/ 层不导入 application/", () => {
    const infraDir = resolve(PACKAGES_DIR, "infrastructure/src")
    const files = collectTsFiles(infraDir)
    const allViolations: string[] = []

    for (const file of files) {
      const violations = checkLayerViolations(file)
      if (violations.length > 0) {
        allViolations.push(`${relative(ROOT, file)}: ${violations.join(", ")}`)
      }
    }

    expect(allViolations).toEqual([])
  })
})

describe("守卫测试：危险模式检测 [NEW-OPT-21]", () => {
  it("domain/ 层不使用 throw 语句（应使用 Effect.fail）", () => {
    const domainDir = resolve(PACKAGES_DIR, "domain/src")
    const files = collectTsFiles(domainDir)
    const violations: string[] = []

    for (const file of files) {
      try {
        const content = readFileSync(file, "utf-8")
        // 检查是否有 throw 语句（排除注释和字符串中的 throw）
        const lines = content.split("\n")
        for (let i = 0; i < lines.length; i++) {
          const trimmed = lines[i]?.trim() ?? ""
          if (trimmed.startsWith("//") || trimmed.startsWith("*")) continue
          if (trimmed.startsWith("throw ") && !trimmed.includes("//")) {
            violations.push(`${relative(ROOT, file)}:${i + 1}: ${trimmed}`)
          }
        }
      } catch {
        // skip
      }
    }

    expect(violations).toEqual([])
  })

  it("所有 ADT 类型使用 _tag 区分（不将 type 作为 discriminator）", () => {
    const domainDir = resolve(PACKAGES_DIR, "domain/src")
    const files = collectTsFiles(domainDir)
    const violations: string[] = []

    for (const file of files) {
      try {
        const content = readFileSync(file, "utf-8")
        const lines = content.split("\n")
        for (const line of lines) {
          // 只检查 ADT union 成员中的 discriminator 字段
          // 排除 ContextNode.type（它是普通字段名，不是 discriminator）
          if (
            /\breadonly\s+type\s*:\s*["']/.test(line) &&
            !line.includes("_tag") &&
            !line.includes("brand") &&
            !line.includes("ContextNode") &&
            !line.includes("message") &&
            !line.includes("tool_call") &&
            !line.includes("tool_result")
          ) {
            violations.push(`${relative(ROOT, file)}: ${line.trim()}`)
          }
        }
      } catch {
        // skip
      }
    }

    expect(violations).toEqual([])
  })
})
