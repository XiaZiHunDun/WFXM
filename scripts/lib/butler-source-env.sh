# Safe .env loader for bash scripts with `set -u` (source, do not execute).
# Usage: ROOT=... source scripts/lib/butler-source-env.sh
#        butler_source_env "$ROOT/.env"

_lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

butler_fix_path_after_env() {
  # shellcheck source=scripts/lib/butler-systemd-install.sh
  source "$_lib_dir/butler-systemd-install.sh"
  export PATH="$(butler_systemd_path)"
}

butler_source_env() {
  local env_file="${1:-}"
  if [[ -z "$env_file" || ! -f "$env_file" ]]; then
    return 1
  fi
  local had_u=0
  case $- in *u*) had_u=1 ;; esac
  set +u
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
  if [[ "$had_u" -eq 1 ]]; then
    set -u
  fi
  butler_fix_path_after_env
  return 0
}
