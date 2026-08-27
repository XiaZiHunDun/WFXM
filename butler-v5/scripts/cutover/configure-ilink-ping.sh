#!/usr/bin/env bash
# Set BUTLER_V5_ILINK_PING_TO for smoke:ilink --send-ping (one-line outbound probe).
#
#   bash scripts/cutover/configure-ilink-ping.sh <wechat_user_id>
#
# Typical id: same as loopback fromUserId in smokes, or your real WeChat user id from ilink.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <wechat_user_id>" >&2
  echo "example: $0 wx-owner-abc123" >&2
  exit 1
fi

TO="$1"
ENV_FILE="${HOME}/.config/butler-v5/env"
mkdir -p "$(dirname "$ENV_FILE")"
touch "$ENV_FILE"

if grep -q '^BUTLER_V5_ILINK_PING_TO=' "$ENV_FILE" 2>/dev/null; then
  sed -i "s|^BUTLER_V5_ILINK_PING_TO=.*|BUTLER_V5_ILINK_PING_TO=${TO}|" "$ENV_FILE"
else
  echo "BUTLER_V5_ILINK_PING_TO=${TO}" >>"$ENV_FILE"
fi

echo "Updated ${ENV_FILE}:"
grep 'BUTLER_V5_ILINK_PING_TO' "$ENV_FILE"
echo ""
echo "Probe outbound: cd butler-v5 && pnpm smoke:ilink -- --send-ping"
