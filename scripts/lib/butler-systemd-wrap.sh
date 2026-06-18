#!/usr/bin/env bash
# Run a bash script under user systemd with a safe PATH (.env may clobber PATH).
# Usage: butler-systemd-wrap.sh /path/to/script.sh [args...]
set -euo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

_wrap="$(/usr/bin/readlink -f "${BASH_SOURCE[0]}")"
_root="$(cd "$(/usr/bin/dirname "$_wrap")/../.." && pwd)"
# shellcheck source=scripts/lib/butler-systemd-install.sh
source "$_root/scripts/lib/butler-systemd-install.sh"

export PATH="$(butler_systemd_path)"
if [[ -f "$_root/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$_root/.env" 2>/dev/null || true
  set +a
fi
export PATH="$(butler_systemd_path)"

target="${1:?missing script path}"
shift
exec /bin/bash "$target" "$@"
