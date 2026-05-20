#!/usr/bin/env bash
# Install Butler gateway as a systemd --user service.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/butler-gateway-preflight.sh
source "$ROOT/scripts/lib/butler-gateway-preflight.sh"

PYTHON="$(command -v python3)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
TEMPLATE="$ROOT/scripts/systemd/butler-gateway.service"
DEST="$UNIT_DIR/butler-gateway.service"

NO_RESTART=0
CHECK_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-restart) NO_RESTART=1 ;;
    --check-only) CHECK_ONLY=1 ;;
    -h|--help)
      echo "Usage: $(basename "$0") [--check-only] [--no-restart]"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
  shift
done

ROOT="$ROOT" butler_gateway_preflight || {
  if [[ "$CHECK_ONLY" -eq 1 ]]; then
    exit 1
  fi
  echo "Preflight failed; fix errors above before installing." >&2
  exit 1
}

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  exit 0
fi

# Avoid Hermes stealing the same Bot session.
if systemctl --user cat hermes-gateway.service >/dev/null 2>&1; then
  systemctl --user stop hermes-gateway.service 2>/dev/null || true
  systemctl --user disable hermes-gateway.service 2>/dev/null || true
  echo "Disabled hermes-gateway.service (Butler-only WeChat)."
fi

mkdir -p "$UNIT_DIR" "$ROOT/logs"
sed "s|@WFXM_ROOT@|$ROOT|g; s|@PYTHON@|$PYTHON|g" "$TEMPLATE" >"$DEST"
systemctl --user daemon-reload
systemctl --user enable butler-gateway.service

if [[ "$NO_RESTART" -eq 0 ]]; then
  systemctl --user restart butler-gateway.service
else
  echo "Unit installed; skipped restart (--no-restart)."
fi

systemctl --user --no-pager status butler-gateway.service | head -15
echo ""
echo "Installed: $DEST"
echo "Ops: bash scripts/butler-gateway-ops.sh status|restart|logs|preflight"
echo "Docs: docs/guides/wechat-gateway-ops.md"
