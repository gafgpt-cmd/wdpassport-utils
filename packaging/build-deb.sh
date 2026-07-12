#!/usr/bin/env bash
# Build a flavor-resilient .deb for MX / Debian / Ubuntu.
#
# The package is now PURE PYTHON (the SCSI layer uses a ctypes SG_IO transport,
# wdpassport/sgio.py, instead of the compiled py3_sg C-extension). So there is
# no venv and no ABI lock: it installs the module into the distro's
# /usr/lib/python3/dist-packages and runs on whatever python3 the flavor ships
# (>= 3.8). Architecture is therefore "all".
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
WT="$(cd -- "$HERE/.." && pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$WT/wdpassport/__init__.py")"
ARCH="all"
PKG="wdpassport-utils"
OUT="$WT/dist"
STAGE="$OUT/pkgroot"

command -v dpkg-deb >/dev/null || { echo "dpkg-deb missing" >&2; exit 1; }

echo ">> version $VERSION, arch $ARCH (pure-python)"
rm -rf "$STAGE"
mkdir -p "$STAGE"/DEBIAN \
         "$STAGE"/usr/bin \
         "$STAGE"/usr/lib/wdpassport \
         "$STAGE"/usr/lib/python3/dist-packages/wdpassport \
         "$STAGE"/usr/share/applications \
         "$STAGE"/usr/share/polkit-1/actions \
         "$STAGE"/usr/share/doc/"$PKG" \
         "$STAGE"/etc/xdg/autostart

# --- 1. the python package --------------------------------------------------
echo ">> installing python module"
cp -f "$WT"/wdpassport/*.py "$STAGE/usr/lib/python3/dist-packages/wdpassport/"

# --- 2. /usr/bin wrappers (use whatever python3 the flavor provides) ---------
mkwrap() { # $1=name $2=module
  cat > "$STAGE/usr/bin/$1" <<EOF
#!/bin/sh
exec /usr/bin/python3 -c 'import sys; from $2 import main; sys.exit(main())' "\$@"
EOF
  chmod 755 "$STAGE/usr/bin/$1"
}
mkwrap wdpassport     wdpassport.cli
mkwrap wdpassport-gui wdpassport.gui
mkwrap wd-tray        wdpassport.tray

# --- 3. privileged helper (single pkexec target for ALL root subcommands) ---
cat > "$STAGE/usr/lib/wdpassport/wd-priv" <<'EOF'
#!/bin/sh
# Runs the wdpassport CLI as root via pkexec. Any subcommand + args are passed
# through; stdin is preserved (used by unlock/password --stdin). Callers invoke:
#   pkexec /usr/lib/wdpassport/wd-priv <subcommand> [args...]
exec /usr/bin/python3 -c 'import sys; from wdpassport.cli import main; sys.exit(main())' "$@"
EOF
chmod 755 "$STAGE/usr/lib/wdpassport/wd-priv"

# --- 4. polkit policy for the helper ----------------------------------------
cat > "$STAGE/usr/share/polkit-1/actions/com.wdpassport.manage.policy" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC
 "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/PolicyKit/1.0/policyconfig.dtd">
<policyconfig>
  <vendor>wdpassport-utils</vendor>
  <action id="com.wdpassport.manage">
    <description>Manage a WD My Passport drive (unlock, password, LED, erase)</description>
    <message>Authentication is required to manage the WD Passport drive</message>
    <defaults>
      <allow_any>auth_admin</allow_any>
      <allow_inactive>auth_admin</allow_inactive>
      <allow_active>auth_admin_keep</allow_active>
    </defaults>
    <annotate key="org.freedesktop.policykit.exec.path">/usr/lib/wdpassport/wd-priv</annotate>
    <annotate key="org.freedesktop.policykit.exec.allow_gui">true</annotate>
  </action>
</policyconfig>
EOF

# --- 5. desktop entries + autostart -----------------------------------------
cat > "$STAGE/usr/share/applications/wd-tray.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=WD Passport Tray
Comment=Unlock, mount and lock WD My Passport drives from the system tray
Exec=wd-tray
Icon=wdpassport
Terminal=false
Categories=Utility;System;
Keywords=WD;Passport;encryption;unlock;
EOF
cp "$STAGE/usr/share/applications/wd-tray.desktop" \
   "$STAGE/etc/xdg/autostart/wd-tray.desktop"
echo 'X-GNOME-Autostart-enabled=true' >> "$STAGE/etc/xdg/autostart/wd-tray.desktop"

cat > "$STAGE/usr/share/applications/wdpassport-gui.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=WD Passport Utility
Comment=Manage WD My Passport hardware encryption and power settings
Exec=wdpassport-gui
Icon=wdpassport
Terminal=false
Categories=Utility;System;
EOF

# --- 5c. application icons (ship our own so they render on any theme) --------
ICONBASE="$STAGE/usr/share/icons/hicolor"
mkdir -p "$ICONBASE/scalable/apps"
cp "$HERE/icons/wdpassport.svg"        "$ICONBASE/scalable/apps/wdpassport.svg"
cp "$HERE/icons/wdpassport-locked.svg" "$ICONBASE/scalable/apps/wdpassport-locked.svg"
cp "$HERE/icons/wdpassport-off.svg"    "$ICONBASE/scalable/apps/wdpassport-off.svg"
# Render raster sizes too (some panels need PNG); best-effort, SVG is enough otherwise.
RSVG="$(command -v rsvg-convert || true)"
INK="$(command -v inkscape || true)"
for sz in 22 24 32 48 64 128; do
  dst="$ICONBASE/${sz}x${sz}/apps"; mkdir -p "$dst"
  for name in wdpassport wdpassport-locked wdpassport-off; do
    if [ -n "$RSVG" ]; then
      "$RSVG" -w "$sz" -h "$sz" "$HERE/icons/$name.svg" -o "$dst/$name.png" 2>/dev/null || true
    elif [ -n "$INK" ]; then
      "$INK" -w "$sz" -h "$sz" "$HERE/icons/$name.svg" -o "$dst/$name.png" >/dev/null 2>&1 || true
    fi
  done
done
# drop empty raster dirs if no converter was available
find "$ICONBASE" -type d -empty -delete 2>/dev/null || true

# --- 6. dependency manifest -------------------------------------------------
cp "$HERE/manifest.txt" "$STAGE/usr/share/doc/$PKG/manifest.txt"

# --- 7. control + maintainer scripts ----------------------------------------
INSTALLED_KB="$(du -sk "$STAGE" | cut -f1)"
cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: python3 (>= 3.8), python3-gi, gir1.2-gtk-3.0, gir1.2-gtk-4.0, gir1.2-ayatanaappindicator3-0.1, python3-typer, udisks2, util-linux, policykit-1, libnotify-bin
Recommends: python3-pyudev, smartmontools
Installed-Size: $INSTALLED_KB
Maintainer: wdpassport-utils <wdpassport-utils@users.noreply.github.com>
Description: WD My Passport hardware-encryption utility (CLI, GTK GUI, tray)
 Unlock, lock, mount and manage WD My Passport hardware-encrypted USB drives on
 Linux. Pure Python (ctypes SG_IO), so it runs on any Debian/MX/Ubuntu flavor
 regardless of the system Python version. Includes a command-line tool, a GTK4
 window, and an Xfce/AppIndicator system-tray applet with rich drive
 identification (friendly names + LED-blink "identify"). Passwords are never
 stored; privileged actions run through PolicyKit.
EOF

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
py3compile -p wdpassport-utils 2>/dev/null || true
update-desktop-database -q 2>/dev/null || true
gtk-update-icon-cache -q -f -t /usr/share/icons/hicolor 2>/dev/null || true
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/postinst"

cat > "$STAGE/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
py3clean -p wdpassport-utils 2>/dev/null || true
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/prerm"

cat > "$STAGE/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
update-desktop-database -q 2>/dev/null || true
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/postrm"

echo "/etc/xdg/autostart/wd-tray.desktop" > "$STAGE/DEBIAN/conffiles"

# --- 8. build ---------------------------------------------------------------
DEB="$OUT/${PKG}_${VERSION}_${ARCH}.deb"
echo ">> building $DEB"
fakeroot dpkg-deb --build "$STAGE" "$DEB"
echo ">> done: $DEB"
dpkg-deb --info "$DEB" | sed -n '1,22p'
