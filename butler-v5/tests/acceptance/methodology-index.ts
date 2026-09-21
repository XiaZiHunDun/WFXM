/**
 * D77 methodology index — registers methodology check vitest test files.
 * vitest auto-discovers *.test.ts files via the workspace, so this index
 * serves as the canonical list of registered M-numbered checks.
 *
 * D77 ships M15 (docker deploy artifacts + cross-link consistency).
 */

export const REGISTERED_METHODOLOGY_CHECKS = ["M15"] as const;

export type RegisteredMethodologyCheck =
  (typeof REGISTERED_METHODOLOGY_CHECKS)[number];
