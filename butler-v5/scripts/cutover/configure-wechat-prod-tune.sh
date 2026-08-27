#!/usr/bin/env bash
# Apply WeChat production tuning to ~/.config/butler-v5/env (idempotent).
# Run from butler-v5: bash scripts/cutover/configure-wechat-prod-tune.sh
set -euo pipefail

ENV_FILE="${BUTLER_V5_ENV_FILE:-$HOME/.config/butler-v5/env}"
ROOT_ENV="${WFXM_ROOT_ENV:-$(cd "$(dirname "$0")/../../.." && pwd)/.env}"
MARKER="prod-tune 2026-08-26"

mkdir -p "$(dirname "$ENV_FILE")"
touch "$ENV_FILE"

if ! grep -q '^MINIMAX_API_KEY=' "$ENV_FILE" && [[ -f "$ROOT_ENV" ]]; then
  echo "[prod-tune] copying MINIMAX_* from $ROOT_ENV"
  grep '^MINIMAX_' "$ROOT_ENV" >> "$ENV_FILE"
fi

if grep -q "$MARKER" "$ENV_FILE"; then
  echo "[prod-tune] already applied ($MARKER)"
else
  cat >> "$ENV_FILE" <<'EOF'

# [prod-tune 2026-08-26] WeChat intake / dev verify / model router
BUTLER_V5_INTAKE_ENABLED=1
BUTLER_V5_INTAKE_LLM=1
BUTLER_V5_MODEL_PLAN=deepseek-v4-flash
BUTLER_V5_MODEL_EXEC=MiniMax-M3
BUTLER_V5_MODEL_INTAKE=deepseek-v4-flash
BUTLER_V5_DEEPSEEK_THINKING=disabled
BUTLER_V5_DEV_SESSION_GRANT_MINUTES=30
BUTLER_V5_DEV_SESSION_MAX_USES=50
BUTLER_V5_DEV_VERIFY_ENABLED=1
BUTLER_V5_DEV_VERIFY_CMD=["pnpm","exec","vitest","run","apps/api/src/dev-quality-gate.test.ts"]
BUTLER_V5_DEV_VERIFY_TIMEOUT_MS=120000
BUTLER_V5_DEV_VERIFY_INLINE=0
BUTLER_V5_SUBAGENT_ENABLED=1
# Scheme B default: no BUTLER_V5_DEV_DIRECT_EXEC (Child Run via delegate)
BUTLER_V5_POST_APPROVAL_LOOP=0
EOF
  echo "[prod-tune] appended tuning block to $ENV_FILE"
fi

if grep -q '^MINIMAX_BASE_URL=.*api\.minimax\.chat' "$ENV_FILE" 2>/dev/null; then
  sed -i 's|^MINIMAX_BASE_URL=.*api\.minimax\.chat.*|MINIMAX_BASE_URL=https://api.minimax.io/v1|' "$ENV_FILE"
  echo "[prod-tune] migrated MINIMAX_BASE_URL api.minimax.chat → api.minimax.io/v1"
fi

# Domestic CN: api.minimaxi.com + MINIMAX_CN_API_KEY (drop intl MINIMAX_API_KEY to avoid wrong host)
if grep -q '^MINIMAX_BASE_URL=.*api\.minimax\.io' "$ENV_FILE" 2>/dev/null; then
  sed -i 's|^MINIMAX_BASE_URL=.*api\.minimax\.io.*|MINIMAX_BASE_URL=https://api.minimaxi.com/v1|' "$ENV_FILE"
  echo "[prod-tune] migrated MINIMAX_BASE_URL api.minimax.io → api.minimaxi.com/v1 (CN)"
fi
if grep -q '^MINIMAX_API_KEY=' "$ENV_FILE" && grep -q '^MINIMAX_BASE_URL=.*api\.minimaxi\.com' "$ENV_FILE" 2>/dev/null; then
  if ! grep -q '^MINIMAX_CN_API_KEY=' "$ENV_FILE" 2>/dev/null; then
    MM_KEY="$(grep '^MINIMAX_API_KEY=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
    echo "MINIMAX_CN_API_KEY=${MM_KEY}" >> "$ENV_FILE"
  fi
  sed -i '/^MINIMAX_API_KEY=/d' "$ENV_FILE"
  echo "[prod-tune] moved MINIMAX_API_KEY → MINIMAX_CN_API_KEY for CN endpoint"
fi

WFXM_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SANDBOX_WS="${WFXM_ROOT}/butler-v5"
if grep -q '^BUTLER_V5_SANDBOX_WORKSPACE_ROOT=' "$ENV_FILE" 2>/dev/null; then
  sed -i "s|^BUTLER_V5_SANDBOX_WORKSPACE_ROOT=.*|BUTLER_V5_SANDBOX_WORKSPACE_ROOT=${SANDBOX_WS}|" "$ENV_FILE"
else
  echo "BUTLER_V5_SANDBOX_WORKSPACE_ROOT=${SANDBOX_WS}" >> "$ENV_FILE"
fi
echo "[prod-tune] sandbox workspace root → ${SANDBOX_WS}"

if ! grep -q '^BUTLER_V5_SANDBOX_SLIRP_FALLBACK=' "$ENV_FILE" 2>/dev/null; then
  echo "BUTLER_V5_SANDBOX_SLIRP_FALLBACK=1" >> "$ENV_FILE"
  echo "[prod-tune] enabled BUTLER_V5_SANDBOX_SLIRP_FALLBACK=1 (proxy retry when slirp fails)"
fi

echo "[prod-tune] restart gateway: systemctl --user restart butler-v5-gateway.service"
echo "[prod-tune] verify: cd butler-v5 && pnpm smoke:prod-tune"
