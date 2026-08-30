import { defineConfig } from "vitest/config"
import { resolve } from "path"

// 归档资产（根 _archive/packages/）的独立测试配置。
// 主配置 vitest.config.ts 通过 exclude `**/_archive/**` + include 白名单排除归档，
// 这里单独放开，供 `pnpm test:archived` 运行历史/脚手架测试资产。
// alias 与主配置保持一致（归档代码按 @butler/* 引用活动包类型，这些包仍在线）。
export default defineConfig({
  test: {
    globals: true,
    environment: "node",
    include: ["_archive/packages/**/*.test.ts", "_archive/tests/**/*.test.ts"],
    exclude: ["**/node_modules/**", "**/dist/**", "**/.turbo/**", "**/*.tsbuildinfo"],
    testTimeout: 10_000,
    hookTimeout: 10_000,
  },
  resolve: {
    alias: [
      { find: "@butler/domain", replacement: resolve(__dirname, "packages/domain/src/index.ts") },
      { find: "@butler/runtime", replacement: resolve(__dirname, "packages/runtime/src") },
      { find: "@butler/persistence", replacement: resolve(__dirname, "packages/persistence/src") },
      { find: "@butler/ports", replacement: resolve(__dirname, "packages/ports/src") },
      { find: "@butler/config", replacement: resolve(__dirname, "_archive/packages/config/src") },
      { find: "@butler/shared", replacement: resolve(__dirname, "_archive/packages/shared/src") },
      { find: "@butler/adapters", replacement: resolve(__dirname, "packages/adapters/src") },
      { find: "@butler/migration", replacement: resolve(__dirname, "_archive/packages/migration/src") },
    ],
  },
})