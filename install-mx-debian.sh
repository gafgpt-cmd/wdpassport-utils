#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="${WDPASSPORT_VENV_DIR:-$HOME/.local/share/wdpassport-utils-venv}"
BIN_DIR="${WDPASSPORT_BIN_DIR:-$HOME/.local/bin}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if command -v apt-get >/dev/null 2>&1; then
  echo "Installing MX/Debian package prerequisites..."
  sudo apt-get update
  sudo apt-get install -y python3 python3-dev python3-venv python3-pip git build-essential libudev-dev
else
  echo "apt-get was not found. Install Python 3, venv, development headers, git, build tools, and libudev headers manually." >&2
fi

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV_DIR/bin/python" -m pip install --upgrade "$SCRIPT_DIR"

mkdir -p "$BIN_DIR"
ln -sfn "$VENV_DIR/bin/wdpassport-utils.py" "$BIN_DIR/wdpassport-utils.py"

cat <<EOF
wdpassport-utils installed.

Entrypoint:
  $BIN_DIR/wdpassport-utils.py

Run with a connected WD My Passport drive:
  sudo "$BIN_DIR/wdpassport-utils.py"

If $BIN_DIR is not in PATH, add this to your shell profile:
  export PATH="\$HOME/.local/bin:\$PATH"
EOF
