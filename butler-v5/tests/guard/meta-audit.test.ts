// tests/guard/meta-audit.test.ts
// 元审计测试 [NEW-OPT-22] — 测试维护质量验证
// 检查 Mock 恢复、循环依赖、测试文件覆盖率

import { describe, it, expect } from "vitest"
import { readFileSync, readdirSync, existsSync } from "fs"
import { resolve, relative } from "path"

const ROOT = resolve(import.meta.dirname ?? __dirname, "../..")
const PACKAGES_DIR = resolve(ROOT, "packages")

function collectFiles(dir: string, pattern: RegExp): string[] {
  const files: string[] = []
  if (!existsSync(dir)) return files
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const fullPath = resolve(dir, entry.name)
    if (entry.isDirectory() && !entry.name.startsWith(".") && entry.name !== "node_modules") {
      files.push(...collectFiles(fullPath, pattern))
    } else if (entry.isFile() && pattern.test(entry.name)) {
      files.push(fullPath)
    }
  }
  return files
}

describe("元审计测试：Mock 恢复完整性 [NEW-OPT-22]", () => {
  it("每个基础设施 service 都有对应的 Mock 变体", () => {
    const infraDir = resolve(PACKAGES_DIR, "infrastructure/src")
    const srcFiles = collectFiles(infraDir, /\.ts$/).filter((f) => !f.endsWith(".test.ts"))

    const hasMockInContent: Record<string, boolean> = {
      llm: false,
      wechat: false,
      mcp: false,
      eventstore: false,
    }

    for (const file of srcFiles) {
      const content = readFileSync(file, "utf-8")
      const rel = relative(ROOT, file)
      if (rel.includes("llm/") && content.includes("Mock")) hasMockInContent.llm = true
      if (rel.includes("wechat/") && content.includes("Mock")) hasMockInContent.wechat = true
      if (rel.includes("mcp/") && content.includes("Mock")) hasMockInContent.mcp = true
      if (rel.includes("persistence/") && (content.includes("Mock") || content.includes("mock")))
        hasMockInContent.eventstore = true
    }

    expect(hasMockInContent.llm).toBe(true)
    expect(hasMockInContent.wechat).toBe(true)
    expect(hasMockInContent.mcp).toBe(true)
    expect(hasMockInContent.eventstore).toBe(true)
    // GuardService Mock 在 application 层（run-loop），不在 infrastructure 层
  })

  it("每个 Mock 都有对应的测试", () => {
    const infraDir = resolve(PACKAGES_DIR, "infrastructure/src")
    const testFiles = collectFiles(infraDir, /\.test\.ts$/)

    // 核心服务：每个目录都应该有测试文件（llm 测试在 application 层，跳过）
    const coreDirs = ["guards", "wechat", "mcp", "persistence", "acl", "migration", "shadow"]
    const testDirs = new Set(
      testFiles.map((f) => {
        const parts = relative(ROOT, f).split("/")
        return parts[parts.length - 2] ?? ""
      }),
    )

    for (const dir of coreDirs) {
      expect(testDirs.has(dir)).toBe(true)
    }
  })
})

describe("元审计测试：循环依赖检测 [NEW-OPT-22]", () => {
  it("包之间无循环依赖", () => {
    // 定义允许的依赖关系
    const allowedDeps: Record<string, string[]> = {
      "@butler/domain": [],
      "@butler/ports": ["@butler/domain"],
      "@butler/application": ["@butler/domain", "@butler/ports"],
      "@butler/infrastructure": [
        "@butler/domain",
        "@butler/ports",
        "@butler/config",
        "@butler/shared",
      ],
      "@butler/config": ["@butler/ports"],
      "@butler/shared": [],
    }

    const pkgDirs = ["domain", "ports", "application", "infrastructure", "config", "shared"]

    for (const pkg of pkgDirs) {
      const pkgPath = resolve(PACKAGES_DIR, pkg, "src")
      const files = collectFiles(pkgPath, /\.ts$/).filter((f) => !f.endsWith(".test.ts"))
      const pkgName = `@butler/${pkg}`
      const allowed = allowedDeps[pkgName] ?? []

      for (const file of files) {
        const content = readFileSync(file, "utf-8")

        for (const [importedPkg] of Object.entries(allowedDeps)) {
          // 跳过自身引用
          if (importedPkg === pkgName) continue
          if (content.includes(importedPkg)) {
            expect(allowed).toContain(importedPkg)
          }
        }
      }
    }
  })
})

describe("元审计测试：测试文件覆盖率 [NEW-OPT-22]", () => {
  it("每个领域纯函数文件都有对应的测试文件", () => {
    const domainDir = resolve(PACKAGES_DIR, "domain/src")

    const pureFiles = collectFiles(domainDir, /pure\.ts$/)
    const testFiles = collectFiles(domainDir, /pure\.test\.ts$/)

    for (const pureFile of pureFiles) {
      const testFile = pureFile.replace(/\.ts$/, ".test.ts")
      const testExists = testFiles.some((t) => t === testFile)
      expect(testExists).toBe(true)
    }
  })

  it("每个应用层用例都有对应的测试文件", () => {
    const appDir = resolve(PACKAGES_DIR, "application/src")

    const srcFiles = collectFiles(appDir, /\.ts$/).filter(
      (f) => !f.endsWith(".test.ts") && !f.endsWith("/index.ts"),
    )
    const testFiles = collectFiles(appDir, /\.test\.ts$/)

    const testFileNames = new Set(
      testFiles.map((f) => relative(ROOT, f).replace(".test.ts", ".ts")),
    )

    for (const srcFile of srcFiles) {
      expect(testFileNames.has(relative(ROOT, srcFile))).toBe(true)
    }
  })
})
