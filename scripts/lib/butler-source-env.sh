# Safe .env loader for bash scripts with `set -u` (source, do not execute).
# Usage: ROOT=... source scripts/lib/butler-source-env.sh
#        butler_source_env "$ROOT/.env"

_lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

butler_fix_path_after_env() {
  # shellcheck source=scripts/lib/butler-systemd-install.sh
  source "$_lib_dir/butler-systemd-install.sh"
  local safe merged env_path
  safe="$(butler_systemd_path)"
  env_path="${PATH:-}"
  # systemd EnvironmentFile does not expand $PATH; strip literal artifact
  env_path="${env_path//:\$PATH/}"
  env_path="${env_path//\$PATH:/}"
  env_path="${env_path//\$PATH/}"
  merged="$safe"
  if [[ -n "$env_path" ]]; then
    merged="$merged:$env_path"
  fi
  local nvm_bin=""
  local IFS=':'
  for seg in $merged; do
    if [[ "$seg" == *"/.nvm/versions/node/"* ]]; then
      nvm_bin="$seg"
      break
    fi
  done
  if [[ -n "$nvm_bin" ]]; then
    local rest=""
    for seg in $merged; do
      [[ "$seg" == "$nvm_bin" ]] && continue
      rest="${rest:+$rest:}$seg"
    done
    merged="${nvm_bin}:${rest}"
  fi
  export PATH="$merged"
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
