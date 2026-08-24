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
      "**/_archive/**",
      "packages/contracts/**",
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
    alias: [
      {
        find: "@butler/domain/runtime.js",
        replacement: resolve(__dirname, "packages/domain/src/runtime/index.ts"),
      },
      {
        find: "@butler/domain/governance/types.js",
        replacement: resolve(__dirname, "packages/domain/src/governance/types.ts"),
      },
      {
        find: "@butler/domain/governance/wechat-network-hosts.js",
        replacement: resolve(__dirname, "packages/domain/src/governance/wechat-network-hosts.ts"),
      },
      {
        find: "@butler/domain/governance/grant-network-hosts.js",
        replacement: resolve(__dirname, "packages/domain/src/governance/grant-network-hosts.ts"),
      },
      {
        find: "@butler/domain/governance/network-allowlist.js",
        replacement: resolve(__dirname, "packages/domain/src/governance/network-allowlist.ts"),
      },
      {
        find: "@butler/domain/governance/mcp-tool-capability.js",
        replacement: resolve(__dirname, "packages/domain/src/governance/mcp-tool-capability.ts"),
      },
      {
        find: "@butler/domain/mcp/manifest.js",
        replacement: resolve(__dirname, "packages/domain/src/mcp/manifest.ts"),
      },
      {
        find: "@butler/domain/knowledge/durable-memory.js",
        replacement: resolve(__dirname, "packages/domain/src/knowledge/durable-memory.ts"),
      },
      {
        find: "@butler/domain/knowledge/document-ingest.js",
        replacement: resolve(__dirname, "packages/domain/src/knowledge/document-ingest.ts"),
      },
      {
        find: "@butler/domain/knowledge/project-knowledge.js",
        replacement: resolve(__dirname, "packages/domain/src/knowledge/project-knowledge.ts"),
      },
      {
        find: "@butler/domain/knowledge/task-procedure.js",
        replacement: resolve(__dirname, "packages/domain/src/knowledge/task-procedure.ts"),
      },
      {
        find: "@butler/domain/observability/local-trace.js",
        replacement: resolve(__dirname, "packages/domain/src/observability/local-trace.ts"),
      },
      { find: "@butler/domain", replacement: resolve(__dirname, "packages/domain/src/index.ts") },
      { find: "@butler/runtime", replacement: resolve(__dirname, "packages/runtime/src") },
      { find: "@butler/persistence", replacement: resolve(__dirname, "packages/persistence/src") },
      { find: "@butler/ports", replacement: resolve(__dirname, "packages/ports/src") },
      {
        find: "@butler/application",
        replacement: resolve(__dirname, "packages/application/src"),
      },
      {
        find: "@butler/infrastructure",
        replacement: resolve(__dirname, "packages/infrastructure/src"),
      },
      { find: "@butler/config", replacement: resolve(__dirname, "packages/config/src") },
      { find: "@butler/shared", replacement: resolve(__dirname, "packages/shared/src") },
      { find: "@butler/adapters", replacement: resolve(__dirname, "packages/adapters/src") },
      {
        find: "@butler/adapters/mcp/client.js",
        replacement: resolve(__dirname, "packages/adapters/src/mcp/client.ts"),
      },
      {
        find: "@butler/adapters/mcp/http-transport.js",
        replacement: resolve(__dirname, "packages/adapters/src/mcp/http-transport.ts"),
      },
      {
        find: "@butler/adapters/mcp/stdio-transport.js",
        replacement: resolve(__dirname, "packages/adapters/src/mcp/stdio-transport.ts"),
      },
      {
        find: "@butler/adapters/mcp/sse-transport.js",
        replacement: resolve(__dirname, "packages/adapters/src/mcp/sse-transport.ts"),
      },
      {
        find: "@butler/adapters/mcp/session.js",
        replacement: resolve(__dirname, "packages/adapters/src/mcp/session.ts"),
      },
      { find: "@butler/migration", replacement: resolve(__dirname, "packages/migration/src") },
      { find: "@butler/api/bootstrap-wiring.js", replacement: resolve(__dirname, "apps/api/src/bootstrap-wiring.ts") },
      { find: "@butler/api/cli-run.js", replacement: resolve(__dirname, "apps/api/src/cli-run.ts") },
      { find: "@butler/api", replacement: resolve(__dirname, "apps/api/src") },
      { find: "@butler/cli", replacement: resolve(__dirname, "cli/src") },
    ],
  },
})
