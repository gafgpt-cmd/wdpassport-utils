#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="${WDPASSPORT_VENV_DIR:-$HOME/.local/share/wdpassport-utils-venv}"
BIN_DIR="${WDPASSPORT_BIN_DIR:-$HOME/.local/bin}"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
# Default desktop launcher directory: $HOME/.local/share/applications
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if command -v apt-get >/dev/null 2>&1; then
  echo "Installing MX/Debian package prerequisites..."
  sudo apt-get update
  sudo apt-get install -y \
    python3 \
    python3-dev \
    python3-venv \
    python3-pip \
    python3-gi \
    gir1.2-gtk-4.0 \
    gir1.2-adw-1 \
    git \
    build-essential \
    libudev-dev
else
  echo "apt-get was not found. Install Python 3, venv, development headers, PyGObject, GTK4, libadwaita, git, build tools, and libudev headers manually." >&2
fi

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV_DIR/bin/python" -m pip install --upgrade "$SCRIPT_DIR"

mkdir -p "$BIN_DIR"
ln -sfn "$VENV_DIR/bin/wdpassport" "$BIN_DIR/wdpassport"
ln -sfn "$VENV_DIR/bin/wdpassport-gui" "$BIN_DIR/wdpassport-gui"

mkdir -p "$APPLICATIONS_DIR"
sed "s|@BINDIR@|$BIN_DIR|g" "$SCRIPT_DIR/wdpassport-gui.desktop.in" > "$APPLICATIONS_DIR/wdpassport-gui.desktop"

cat <<EOF
wdpassport-utils installed.

Entrypoints:
  $BIN_DIR/wdpassport
  $BIN_DIR/wdpassport-gui

Desktop launcher:
  $APPLICATIONS_DIR/wdpassport-gui.desktop

Run with a connected WD My Passport drive:
  sudo "$BIN_DIR/wdpassport" status --device /dev/sdX
  sudo "$BIN_DIR/wdpassport-gui"

If $BIN_DIR is not in PATH, add this to your shell profile:
  export PATH="\$HOME/.local/bin:\$PATH"
EOF
