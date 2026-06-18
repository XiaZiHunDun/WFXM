# Shared helpers for Butler user systemd unit installation (source only).
# Usage: source scripts/lib/butler-systemd-install.sh

butler_resolve_python3() {
  if [[ -n "${BUTLER_PYTHON:-}" && -x "${BUTLER_PYTHON}" ]]; then
    printf '%s\n' "$BUTLER_PYTHON"
    return 0
  fi
  if [[ -x /home/ailearn/miniconda3/bin/python3 ]]; then
    printf '%s\n' /home/ailearn/miniconda3/bin/python3
    return 0
  fi
  command -v python3
}

butler_systemd_path() {
  local python="${1:-$(butler_resolve_python3)}"
  local py_dir
  py_dir="$(/usr/bin/dirname "$python")"
  printf '%s:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n' "$py_dir"
}

butler_render_systemd_unit() {
  local src="${1:?}"
  local dst="${2:?}"
  local root="${3:?}"
  local python="${4:-$(butler_resolve_python3)}"
  local path="${5:-$(butler_systemd_path "$python")}"
  sed "s|@WFXM_ROOT@|$root|g; s|@PYTHON@|$python|g; s|@SYSTEMD_PATH@|$path|g" "$src" >"$dst"
}
