#!/bin/bash
# scripts/run-test-layer.sh
# Butler v5 测试层运行脚本 — 按测试等级运行测试子集
# 用法: bash scripts/run-test-layer.sh [domain|app|infra|guard|all]

set -euo pipefail

LEVEL="${1:-all}"
cd "$(dirname "$0")/.."

run_tests() {
  local pattern="$1"
  echo "=== Running: $pattern ==="
  pnpm vitest run "$pattern" --reporter=verbose
}

case "$LEVEL" in
  domain)
    run_tests "packages/domain/src/**/*.test.ts"
    ;;
  app|application)
    run_tests "_archive/packages/application/src/**/*.test.ts"
    ;;
  infra|infrastructure)
    run_tests "_archive/packages/infrastructure/src/**/*.test.ts"
    ;;
  guard)
    run_tests "tests/guard/**/*.test.ts"
    ;;
  all)
    run_tests "packages/domain/src/**/*.test.ts"
    run_tests "_archive/packages/application/src/**/*.test.ts"
    run_tests "_archive/packages/infrastructure/src/**/*.test.ts"
    run_tests "tests/guard/**/*.test.ts"
    ;;
  *)
    echo "Unknown level: $LEVEL"
    echo "Usage: bash scripts/run-test-layer.sh [domain|app|infra|guard|all]"
    exit 1
    ;;
esac

echo "=== Done ==="