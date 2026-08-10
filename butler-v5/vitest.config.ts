import { defineConfig } from "vitest/config"
import { resolve } from "path"

export default defineConfig({
  test: {
    globals: true,
    environment: "node",
    include: ["packages/**/*.test.ts", "apps/**/*.test.ts", "tests/**/*.test.ts"],
    exclude: ["**/node_modules/**", "**/dist/**", "**/.turbo/**", "**/*.tsbuildinfo"],
    coverage: {
      provider: "v8",
      include: [
        "packages/domain/src/**/*.ts",
        "packages/application/src/**/*.ts",
        "packages/infrastructure/src/**/*.ts",
      ],
      exclude: ["**/*.test.ts", "**/index.ts"],
      thresholds: {
        branches: 60,
        functions: 70,
        lines: 70,
        statements: 70,
      },
    },
    testTimeout: 10_000,
    hookTimeout: 10_000,
  },
  resolve: {
    alias: {
      "@butler/domain": resolve(__dirname, "packages/domain/src"),
      "@butler/ports": resolve(__dirname, "packages/ports/src"),
      "@butler/application": resolve(__dirname, "packages/application/src"),
      "@butler/infrastructure": resolve(__dirname, "packages/infrastructure/src"),
      "@butler/config": resolve(__dirname, "packages/config/src"),
      "@butler/shared": resolve(__dirname, "packages/shared/src"),
      "@butler/adapters": resolve(__dirname, "packages/adapters/src"),
    },
  },
})
