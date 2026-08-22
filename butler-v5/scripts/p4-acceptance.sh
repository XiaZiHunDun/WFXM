#!/usr/bin/env bash
# P4 real-path acceptance (simulated WeChat + Schedule + Task + Traces).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec pnpm exec vitest run apps/api/src/p4-acceptance.harness.test.ts packages/persistence/src/migrations/migrations-registry.test.ts packages/domain/src/observability/local-trace.test.ts
