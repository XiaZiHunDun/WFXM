import { defineConfig } from "vitest/config"
import { resolve } from "path"

export default defineConfig({
  test: {
    globals: true,
    environment: "node",
    include: [
      "packages/**/*.test.ts",
      "apps/**/*.test.ts",
      "cli/**/*.test.ts",
      "tests/**/*.test.ts",
      "tests/e2e/**/*.test.ts",
      "scripts/**/*.test.{ts,mjs}",
    ],
    exclude: [
      "**/node_modules/**",
      "**/dist/**",
      "**/.turbo/**",
      "**/*.tsbuildinfo",
      // Nested pnpm typecheck/lint/format:check. Duplicate of `pnpm gate`;
      // closed in docs/plans/decisions/v5-optional-debt-triage-2026-08-20.md.
      "tests/architecture/r2-end-to-end.test.ts",
      "tests/architecture/r3-end-to-end.test.ts",
      "tests/architecture/r4-end-to-end.test.ts",
      "tests/architecture/r5-end-to-end.test.ts",
      "tests/architecture/r6-end-to-end.test.ts",
    ],
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
      "@butler/migration": resolve(__dirname, "packages/migration/src"),
      "@butler/api": resolve(__dirname, "apps/api/src"),
      "@butler/cli": resolve(__dirname, "cli/src"),
    },
  },
})
