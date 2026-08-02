#!/usr/bin/env bash
set -euo pipefail

VENV_DIR="${WDPASSPORT_VENV_DIR:-$HOME/.local/share/wdpassport-utils-venv}"
BIN_DIR="${WDPASSPORT_BIN_DIR:-$HOME/.local/bin}"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
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
        gir1.2-ayatanaappindicator3-0.1 \
        git \
        build-essential \
        libudev-dev \
        policykit-1 \
        udisks2 \
        util-linux \
        libnotify-bin \
        smartmontools \
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
        libayatana-appindicator-gtk3 \
        git \
        gcc \
        gcc-c++ \
        make \
        systemd-devel \
        polkit \
        udisks2 \
        util-linux \
        libnotify \
        smartmontools \
        curl
      ;;
    pacman)
      echo "Installing Arch Linux package prerequisites..."
      sudo pacman -Syu --needed --noconfirm \
        python \
        python-gobject \
        gtk4 \
        libadwaita \
        libayatana-appindicator \
        git \
        base-devel \
        systemd \
        polkit \
        udisks2 \
        util-linux \
        libnotify \
        smartmontools \
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
        typelib-1_0-AyatanaAppIndicator3-0_1 \
        git \
        gcc \
        make \
        systemd-devel \
        polkit \
        udisks2 \
        util-linux \
        libnotify-tools \
        smartmontools \
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

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  if [[ -e "$VENV_DIR" ]]; then
    "$UV_BIN" venv --clear --system-site-packages --python python3 "$VENV_DIR"
  else
    "$UV_BIN" venv --system-site-packages --python python3 "$VENV_DIR"
  fi
fi
"$UV_BIN" pip install --python "$VENV_DIR/bin/python" --upgrade "$SCRIPT_DIR"

ln -sfn "$VENV_DIR/bin/wdpassport" "$BIN_DIR/wdpassport"
ln -sfn "$VENV_DIR/bin/wdpassport-gui" "$BIN_DIR/wdpassport-gui"
ln -sfn "$VENV_DIR/bin/wd-tray" "$BIN_DIR/wd-tray"

mkdir -p "$APPLICATIONS_DIR" "$AUTOSTART_DIR" "$ICON_DIR"
rm -f "$APPLICATIONS_DIR/wdpassport-gui.desktop"
DESKTOP_BIN_DIR=${BIN_DIR//\\/\\\\}
DESKTOP_BIN_DIR=${DESKTOP_BIN_DIR//\"/\\\"}
DESKTOP_BIN_DIR=${DESKTOP_BIN_DIR//\`/\\\`}
DESKTOP_BIN_DIR=${DESKTOP_BIN_DIR//\$/\\\$}

render_desktop() {
  local template=$1
  local output=$2
  local executable=$3
  local line
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == Exec=* ]]; then
      printf 'Exec="%s/%s"\n' "$DESKTOP_BIN_DIR" "$executable"
    else
      printf '%s\n' "$line"
    fi
  done < "$template" > "$output"
}

render_desktop "$SCRIPT_DIR/wdpassport-gui.desktop.in" \
  "$APPLICATIONS_DIR/dev.wdpassport.utility.desktop" wdpassport-gui
render_desktop "$SCRIPT_DIR/wd-tray.desktop.in" \
  "$APPLICATIONS_DIR/wd-tray.desktop" wd-tray
cp "$APPLICATIONS_DIR/wd-tray.desktop" "$AUTOSTART_DIR/wd-tray.desktop"
cp "$SCRIPT_DIR/packaging/icons/wdpassport.svg" "$ICON_DIR/wdpassport.svg"
cp "$SCRIPT_DIR/packaging/icons/wdpassport-locked.svg" "$ICON_DIR/wdpassport-locked.svg"
cp "$SCRIPT_DIR/packaging/icons/wdpassport-off.svg" "$ICON_DIR/wdpassport-off.svg"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPLICATIONS_DIR" || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -f -t "${ICON_DIR%/scalable/apps}" || true
fi

cat <<EOF
wdpassport-utils installed.

Entrypoints:
  $BIN_DIR/wdpassport
  $BIN_DIR/wdpassport-gui
  $BIN_DIR/wd-tray

Desktop launcher:
  $APPLICATIONS_DIR/dev.wdpassport.utility.desktop

Tray autostart:
  $AUTOSTART_DIR/wd-tray.desktop

Run with a connected WD My Passport drive:
  sudo "$BIN_DIR/wdpassport" status --device /dev/sdX
  "$BIN_DIR/wdpassport-gui"

If $BIN_DIR is not in PATH, add this to your shell profile:
  export PATH="\$HOME/.local/bin:\$PATH"
EOF
