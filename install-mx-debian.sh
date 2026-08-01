#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="${WDPASSPORT_VENV_DIR:-$HOME/.local/share/wdpassport-utils-venv}"
BIN_DIR="${WDPASSPORT_BIN_DIR:-$HOME/.local/bin}"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
# Default desktop launcher directory: $HOME/.local/share/applications
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

install_system_dependencies() {
  local package_manager=${WDPASSPORT_PACKAGE_MANAGER:-}

  if [[ -z "$package_manager" ]]; then
    if command -v apt-get >/dev/null 2>&1; then
      package_manager=apt
    elif command -v dnf >/dev/null 2>&1; then
      package_manager=dnf
    elif command -v pacman >/dev/null 2>&1; then
      package_manager=pacman
    elif command -v zypper >/dev/null 2>&1; then
      package_manager=zypper
    else
      echo "No supported package manager found (apt, dnf, pacman, or zypper)." >&2
      return 1
    fi
  fi

  case "$package_manager" in
    apt)
      echo "Installing Debian/Ubuntu package prerequisites..."
      sudo apt-get update
      sudo apt-get install -y \
        python3 \
        python3-dev \
        python3-venv \
        python3-gi \
        gir1.2-gtk-4.0 \
        gir1.2-adw-1 \
        git \
        build-essential \
        libudev-dev \
        curl
      ;;
    dnf)
      echo "Installing Fedora/RHEL package prerequisites..."
      sudo dnf install -y \
        python3 \
        python3-devel \
        python3-gobject \
        gtk4 \
        libadwaita \
        git \
        gcc \
        gcc-c++ \
        make \
        systemd-devel \
        curl
      ;;
    pacman)
      echo "Installing Arch Linux package prerequisites..."
      sudo pacman -Syu --needed --noconfirm \
        python \
        python-gobject \
        gtk4 \
        libadwaita \
        git \
        base-devel \
        systemd \
        curl
      ;;
    zypper)
      echo "Installing openSUSE package prerequisites..."
      sudo zypper --non-interactive install \
        python3 \
        python3-devel \
        python3-gobject \
        typelib-1_0-Gtk-4_0 \
        typelib-1_0-Adw-1 \
        gtk4 \
        libadwaita-devel \
        git \
        gcc \
        make \
        systemd-devel \
        curl
      ;;
    *)
      echo "Unsupported package manager: $package_manager; expected apt, dnf, pacman, or zypper." >&2
      return 1
      ;;
  esac
}

ensure_uv() {
  UV_BIN=$(command -v uv || true)
  if [[ -n "$UV_BIN" ]]; then
    return
  fi

  local installer
  installer=$(mktemp)
  if ! curl -LsSf https://astral.sh/uv/install.sh -o "$installer"; then
    rm -f "$installer"
    return 1
  fi
  if ! UV_INSTALL_DIR="$BIN_DIR" sh "$installer"; then
    rm -f "$installer"
    return 1
  fi
  rm -f "$installer"
  UV_BIN="$BIN_DIR/uv"
}

install_system_dependencies
mkdir -p "$BIN_DIR"
UV_BIN=""
ensure_uv

"$UV_BIN" venv --system-site-packages --python python3 "$VENV_DIR"
"$UV_BIN" pip install --python "$VENV_DIR/bin/python" --upgrade "$SCRIPT_DIR"

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
