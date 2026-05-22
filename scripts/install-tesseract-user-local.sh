#!/usr/bin/env bash
# Install tesseract + chi_sim under ~/.local/tesseract without sudo (Ubuntu deb unpack).
set -euo pipefail

PREFIX="${TESSERACT_PREFIX:-$HOME/.local/tesseract}"
TMP="${TMPDIR:-/tmp}"

mkdir -p "$PREFIX"
cd "$TMP"

pkgs=(
  tesseract-ocr
  tesseract-ocr-eng
  tesseract-ocr-chi-sim
  tesseract-ocr-osd
  libtesseract4
  liblept5
  libwebpmux3
  libopenjp2-7
  libwebp7
  libgif7
  libjpeg-turbo8
  libpng16-16
  libtiff5
)

for pkg in "${pkgs[@]}"; do
  apt-get download -qq "$pkg" 2>/dev/null || true
  for deb in "$TMP"/${pkg}_*.deb "$TMP"/*${pkg}*.deb; do
    [[ -f "$deb" ]] || continue
    dpkg -x "$deb" "$PREFIX"
    break
  done
done

if [[ ! -x "$PREFIX/usr/bin/tesseract" ]]; then
  echo "tesseract binary missing under $PREFIX" >&2
  exit 1
fi

export PATH="$PREFIX/usr/bin:$PATH"
export LD_LIBRARY_PATH="$PREFIX/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export TESSDATA_PREFIX="$PREFIX/usr/share/tesseract-ocr/4.00/tessdata"

tesseract --version
tesseract --list-langs | head -5

ENV_FILE="${1:-}"
if [[ -n "$ENV_FILE" && -f "$ENV_FILE" ]]; then
  marker="# tesseract user-local (install-tesseract-user-local.sh)"
  if ! grep -qF "$marker" "$ENV_FILE" 2>/dev/null; then
    cat >>"$ENV_FILE" <<EOF

$marker
PATH=$PREFIX/usr/bin:\$PATH
LD_LIBRARY_PATH=$PREFIX/usr/lib/x86_64-linux-gnu:\$LD_LIBRARY_PATH
TESSDATA_PREFIX=$TESSDATA_PREFIX
EOF
    echo "Appended tesseract PATH to $ENV_FILE"
  else
    echo "Already configured in $ENV_FILE"
  fi
fi

echo "Done. Prefix: $PREFIX"
