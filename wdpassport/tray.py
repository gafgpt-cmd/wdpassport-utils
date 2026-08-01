"""System-tray applet for WD My Passport drives (Xfce/GTK3 + AppIndicator).

Goal: make it obvious WHICH drive to unlock. Drives are discovered through the
frozen :func:`wdpassport.devices.list_drives` (rich identification: friendly
alias, serial tail, size, USB port, lock state, mountpoint). Menu items use
``Drive.label()`` so two identical drives stay distinguishable, an LED-blink
"identify" action lights the physical unit, and aliases give drives memorable
names.

Privileged actions (unlock, identify) go through pkexec of the root helper.
Non-privileged actions (mount/unmount/lock/open) run as the user via udisksctl
and xdg-open. No password is ever stored; it is prompted per unlock and piped
to the helper on stdin.
"""

import os
import subprocess
import time

from .devices import list_drives, set_alias, virtual_cd_nodes
from .launchers import privileged_command

REFRESH_SECONDS = 5


# ---------------------------------------------------------------------------
# Privileged command builder (always pkexec the root helper)
# ---------------------------------------------------------------------------

def priv(*args):
    """Build a pkexec invocation of the privileged wdpassport helper."""
    return privileged_command(*args)


def _pkexec_message(returncode: int, proc=None) -> str:
    if returncode in (126, 127):
        return "Authorization cancelled or denied."
    if proc is not None:
        return (proc.stderr or proc.stdout or "operation failed").strip()
    return "operation failed"


# ---------------------------------------------------------------------------
# Actions (all wrapped; never raise into the GTK main loop)
# ---------------------------------------------------------------------------

def notify(summary: str, body: str = "", icon: str = "wdpassport"):
    try:
        subprocess.Popen(["notify-send", "-i", icon, summary, body])
    except Exception:
        pass


def do_unlock(node: str, password: str) -> tuple:
    """pkexec the root helper, feeding the drive password on stdin.

    Returns (ok: bool, message: str).
    """
    cmd = priv("unlock", "-d", node, "--password-stdin")
    try:
        proc = subprocess.run(cmd, input=password + "\n", text=True,
                              capture_output=True, timeout=60)
    except Exception as exc:
        return False, str(exc)
    if proc.returncode == 0:
        return True, "unlocked"
    return False, _pkexec_message(proc.returncode, proc)


def do_identify(node: str) -> tuple:
    """Blink the drive LED so the user can spot the physical unit."""
    cmd = priv("identify", "-d", node, "--count", "8")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception as exc:
        return False, str(exc)
    if proc.returncode == 0:
        return True, "identifying"
    return False, _pkexec_message(proc.returncode, proc)


def do_priv(node: str, *args) -> tuple:
    """Run a privileged read/toggle CLI subcommand; return (ok, text)."""
    try:
        proc = subprocess.run(priv(*args, "-d", node),
                              capture_output=True, text=True, timeout=60)
    except Exception as exc:
        return False, str(exc)
    if proc.returncode == 0:
        return True, (proc.stdout or "done").strip()
    return False, _pkexec_message(proc.returncode, proc)


def _wait_for_part(node: str, timeout: int = 20) -> str:
    """Poll for the partition to appear after an unlock (up to ~timeout s)."""
    for _ in range(timeout):
        for p in (f"{node}1", f"{node}p1"):
            if os.path.exists(p):
                return p
        try:
            subprocess.run(["udevadm", "settle", "--timeout=2"],
                           capture_output=True)
        except Exception:
            pass
        time.sleep(1)
    return ""


def _findmnt(source: str) -> str:
    if not source:
        return ""
    try:
        out = subprocess.run(
            ["findmnt", "-nro", "TARGET", "--source", source],
            capture_output=True, text=True, timeout=5,
        )
        lines = out.stdout.strip().splitlines()
        return lines[0] if lines else ""
    except Exception:
        return ""


def do_mount(partition: str) -> tuple:
    if not partition:
        return False, "no partition"
    mp = _findmnt(partition)
    if mp:
        return True, mp
    last = "mount failed"
    # A freshly-appeared partition (e.g. right after unlock) can be briefly not
    # ready; retry with a settle so a single click succeeds.
    for _ in range(3):
        out = ""
        try:
            proc = subprocess.run(["udisksctl", "mount", "-b", partition],
                                  capture_output=True, text=True, timeout=30)
            out = (proc.stderr or proc.stdout or "").strip()
        except Exception as exc:
            out = str(exc)
        mp = _findmnt(partition)
        if mp:
            return True, mp
        if "already mounted" in out.lower() or "AlreadyMounted" in out:
            return True, _findmnt(partition) or "mounted"
        if out:
            last = out
        try:
            subprocess.run(["udevadm", "settle", "--timeout=2"],
                           capture_output=True)
        except Exception:
            pass
        time.sleep(0.6)
    return False, last


def do_unmount(partition: str) -> tuple:
    if not partition:
        return False, "no partition"
    try:
        proc = subprocess.run(["udisksctl", "unmount", "-b", partition],
                              capture_output=True, text=True, timeout=30)
    except Exception as exc:
        return False, str(exc)
    return proc.returncode == 0, (proc.stderr or proc.stdout or "").strip()


def do_poweroff(node: str, serial: str = "") -> tuple:
    """WD re-locks on power loss, so power-off is the 'lock' action.

    The WD Virtual CD ('WD Unlocker') is a second unit on the same device;
    udisks blocks power-off while it is mounted, so unmount it first.
    """
    for vcd in virtual_cd_nodes(serial):
        try:
            subprocess.run(["udisksctl", "unmount", "-b", vcd],
                           capture_output=True, text=True, timeout=15)
        except Exception:
            pass
    try:
        proc = subprocess.run(["udisksctl", "power-off", "-b", node],
                              capture_output=True, text=True, timeout=30)
    except Exception as exc:
        return False, str(exc)
    return proc.returncode == 0, (proc.stderr or proc.stdout or "").strip()


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    if argv is None:
        import sys
        argv = sys.argv[1:]
    if "--help" in argv or "-h" in argv:
        print("Usage: wd-tray")
        print()
        print("WD My Passport system-tray applet. Lists connected drives with")
        print("rich labels (alias, serial, size, USB port, lock state) and offers")
        print("unlock/mount/lock/identify/rename actions. Privileged unlock and")
        print("identify go through pkexec; run inside your desktop session.")
        return 0

    import gi
    gi.require_version("Gtk", "3.0")
    gi.require_version("AyatanaAppIndicator3", "0.1")
    from gi.repository import Gtk, GLib, AyatanaAppIndicator3 as AppIndicator

    class Tray:
        def __init__(self):
            self.ind = AppIndicator.Indicator.new(
                "wdpassport-tray",
                "wdpassport",
                AppIndicator.IndicatorCategory.HARDWARE,
            )
            self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
            self.ind.set_title("WD Passport")
            self.menu = Gtk.Menu()
            self.ind.set_menu(self.menu)
            self.rebuild()
            GLib.timeout_add_seconds(REFRESH_SECONDS, self._tick)

        def _tick(self):
            self.rebuild()
            return True  # keep the periodic timer alive

        # --- menu construction ----------------------------------------------
        def rebuild(self):
            try:
                drives = list_drives()
            except Exception as exc:
                drives = []
                notify("WD Passport", f"Discovery failed: {exc}", "dialog-error")

            for child in self.menu.get_children():
                self.menu.remove(child)

            if not drives:
                item = Gtk.MenuItem(label="No WD Passport connected")
                item.set_sensitive(False)
                self.menu.append(item)
            else:
                for d in drives:
                    self._append_drive(d)

            self.menu.append(Gtk.SeparatorMenuItem())
            panel = Gtk.MenuItem(label="Open Control Panel…")
            panel.connect("activate", lambda _w: self.on_open_control_panel())
            self.menu.append(panel)
            refresh = Gtk.MenuItem(label="Refresh")
            refresh.connect("activate", lambda _w: self.rebuild())
            self.menu.append(refresh)
            quit_item = Gtk.MenuItem(label="Quit")
            quit_item.connect("activate", lambda _w: Gtk.main_quit())
            self.menu.append(quit_item)
            self.menu.show_all()

            self._update_icon(drives)

        def _update_icon(self, drives):
            try:
                if not drives:
                    # None connected / just powered off (Lock removes the device).
                    self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
                    self.ind.set_icon_full("wdpassport-off", "No WD Passport")
                elif any(d.is_locked for d in drives):
                    # A locked drive should be visually obvious.
                    self.ind.set_status(AppIndicator.IndicatorStatus.ATTENTION)
                    self.ind.set_attention_icon_full(
                        "wdpassport-locked", "WD Passport locked")
                    self.ind.set_icon_full("wdpassport-off", "WD Passport")
                else:
                    self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
                    self.ind.set_icon_full("wdpassport", "WD Passport")
            except Exception:
                pass

        def _drive_header_label(self, d):
            """Two-line label. AppIndicator exports menus over DBusMenu, which
            carries only a plain label string (no custom widgets/markup), but a
            newline in that string renders as two rows.
            row 1 = name + id, row 2 = size · port · status.
            """
            state = "LOCKED" if d.is_locked else "unlocked"
            loc = "port %s" % d.usb_port if d.usb_port else d.node
            line1 = "%s  #%s" % (d.alias or d.model, d.serial_tail)
            line2 = "%s · %s · %s" % (d.size, loc, state)
            if d.mountpoint:
                line2 += " · %s" % d.mountpoint
            return "%s\n%s" % (line1, line2)

        def _append_drive(self, d):
            head = Gtk.MenuItem(label=self._drive_header_label(d))
            sub = Gtk.Menu()
            head.set_submenu(sub)

            def add(label, handler):
                mi = Gtk.MenuItem(label=label)
                mi.connect("activate", lambda _w: handler())
                sub.append(mi)
                return mi

            if d.is_locked:
                add("Unlock + Mount", lambda dd=d: self.on_unlock(dd))
                add("Identify (blink LED)", lambda dd=d: self.on_identify(dd))
                add("Status", lambda dd=d: self.on_status(dd))
                add("Health (S.M.A.R.T.)", lambda dd=d: self.on_health(dd))
                add("Rename…", lambda dd=d: self.on_rename(dd))
            else:
                if d.mountpoint:
                    add(f"Open  ({d.mountpoint})", lambda dd=d: self.on_open(dd))
                    add("Unmount", lambda dd=d: self.on_unmount(dd))
                else:
                    add("Mount", lambda dd=d: self.on_mount(dd))
                sub.append(Gtk.SeparatorMenuItem())
                add("Lock (power off)", lambda dd=d: self.on_lock(dd))
                add("Identify (blink LED)", lambda dd=d: self.on_identify(dd))
                add("Status", lambda dd=d: self.on_status(dd))
                add("Health (S.M.A.R.T.)", lambda dd=d: self.on_health(dd))
                add("Disable standby (sleep off)",
                    lambda dd=d: self.on_sleep_off(dd))
                add("Change Password…",
                    lambda dd=d: self.on_change_password(dd))
                add("Rename…", lambda dd=d: self.on_rename(dd))

            self.menu.append(head)

        # --- action handlers ------------------------------------------------
        def on_unlock(self, d):
            try:
                pw = self._ask_password(d)
                if pw is None:
                    return
                ok, msg = do_unlock(d.node, pw)
                if not ok:
                    notify("Unlock failed", msg, "dialog-error")
                    self.rebuild()
                    return
                part = _wait_for_part(d.node)
                if not part:
                    notify("Unlocked",
                           "Partition did not appear; try Mount.",
                           "dialog-warning")
                    self.rebuild()
                    return
                mok, mmsg = do_mount(part)
                if mok:
                    notify("Drive unlocked", f"Mounted at {mmsg}",
                           "wdpassport")
                else:
                    notify("Drive unlocked",
                           f"Unlocked; mount failed: {mmsg}", "dialog-warning")
            except Exception as exc:
                notify("Unlock error", str(exc), "dialog-error")
            finally:
                self.rebuild()

        def on_identify(self, d):
            try:
                ok, msg = do_identify(d.node)
                if ok:
                    notify("Identifying drive",
                           f"LED blinking on {d.label()}", "wdpassport")
                else:
                    notify("Identify failed", msg, "dialog-error")
            except Exception as exc:
                notify("Identify error", str(exc), "dialog-error")

        def on_status(self, d):
            try:
                ok, text = do_priv(d.node, "status")
                notify("WD Passport status" if ok else "Status failed",
                       text, "wdpassport" if ok else "dialog-error")
            except Exception as exc:
                notify("Status error", str(exc), "dialog-error")

        def on_health(self, d):
            try:
                ok, text = do_priv(d.node, "health")
                notify("WD Passport health" if ok else "Health check failed",
                       text, "wdpassport" if ok else "dialog-error")
            except Exception as exc:
                notify("Health error", str(exc), "dialog-error")

        def on_sleep_off(self, d):
            try:
                ok, text = do_priv(d.node, "sleep", "off")
                notify("Standby disabled" if ok else "Sleep-off failed",
                       text or "The drive will not spin down.",
                       "wdpassport" if ok else "dialog-error")
            except Exception as exc:
                notify("Sleep-off error", str(exc), "dialog-error")

        def on_open_control_panel(self):
            try:
                subprocess.Popen(["wdpassport-gui"])
            except Exception as exc:
                notify("Cannot open control panel", str(exc), "dialog-error")

        def on_change_password(self, d):
            try:
                creds = self._ask_change_password(d)
                if creds is None:
                    return
                current, new = creds
                if not current or not new:
                    notify("Change password",
                           "Both current and new passwords are required.",
                           "dialog-error")
                    return
                try:
                    proc = subprocess.run(
                        priv("password", "change", "-d", d.node, "--stdin"),
                        input="%s\n%s\n" % (current, new), text=True,
                        capture_output=True, timeout=60)
                except Exception as exc:
                    notify("Change password failed", str(exc), "dialog-error")
                    return
                if proc.returncode == 0:
                    notify("Password changed",
                           "The drive password was updated.", "wdpassport")
                else:
                    notify("Change password failed",
                           _pkexec_message(proc.returncode, proc), "dialog-error")
            except Exception as exc:
                notify("Change password error", str(exc), "dialog-error")

        def on_mount(self, d):
            try:
                ok, msg = do_mount(d.partition)
                notify("Mounted" if ok else "Mount failed", msg,
                       "wdpassport" if ok else "dialog-error")
            except Exception as exc:
                notify("Mount error", str(exc), "dialog-error")
            finally:
                self.rebuild()

        def on_unmount(self, d):
            try:
                ok, msg = do_unmount(d.partition)
                notify("Unmounted" if ok else "Unmount failed", msg or "",
                       "wdpassport" if ok else "dialog-error")
            except Exception as exc:
                notify("Unmount error", str(exc), "dialog-error")
            finally:
                self.rebuild()

        def on_open(self, d):
            try:
                if d.mountpoint:
                    subprocess.Popen(["xdg-open", d.mountpoint])
            except Exception as exc:
                notify("Open failed", str(exc), "dialog-error")

        def on_lock(self, d):
            try:
                if d.mountpoint:
                    uok, umsg = do_unmount(d.partition)
                    if not uok:
                        notify("Lock failed", f"Unmount failed: {umsg}",
                               "dialog-error")
                        self.rebuild()
                        return
                ok, msg = do_poweroff(d.node, d.serial)
                if ok:
                    notify("Drive locked",
                           "Powered off; re-plug or Unlock to use.",
                           "wdpassport")
                else:
                    notify("Lock failed", msg, "dialog-error")
            except Exception as exc:
                notify("Lock error", str(exc), "dialog-error")
            finally:
                self.rebuild()

        def on_rename(self, d):
            try:
                name = self._ask_alias(d)
                if name is None:
                    return
                set_alias(d.serial, name)
                notify("Drive renamed",
                       f"#{d.serial_tail} → {name}", "wdpassport")
            except Exception as exc:
                notify("Rename failed", str(exc), "dialog-error")
            finally:
                self.rebuild()

        # --- dialogs --------------------------------------------------------
        def _ask_password(self, d):
            dlg = Gtk.Dialog(title="Unlock WD Passport", flags=0)
            dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                            "Unlock", Gtk.ResponseType.OK)
            dlg.set_default_response(Gtk.ResponseType.OK)
            box = dlg.get_content_area()
            box.set_spacing(8)
            box.set_border_width(12)
            box.add(Gtk.Label(label="Unlock this drive:", xalign=0))
            id_label = Gtk.Label(label=d.label(), xalign=0)
            id_label.set_selectable(True)
            box.add(id_label)
            box.add(Gtk.Label(label="Drive password:", xalign=0))
            entry = Gtk.Entry()
            entry.set_visibility(False)
            entry.set_activates_default(True)
            box.add(entry)
            dlg.show_all()
            resp = dlg.run()
            pw = entry.get_text() if resp == Gtk.ResponseType.OK else None
            dlg.destroy()
            return pw

        def _ask_change_password(self, d):
            dlg = Gtk.Dialog(title="Change WD Passport Password", flags=0)
            dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                            "Change", Gtk.ResponseType.OK)
            dlg.set_default_response(Gtk.ResponseType.OK)
            box = dlg.get_content_area()
            box.set_spacing(8)
            box.set_border_width(12)
            id_label = Gtk.Label(label=d.label(), xalign=0)
            id_label.set_selectable(True)
            box.add(id_label)
            box.add(Gtk.Label(label="Current password:", xalign=0))
            cur = Gtk.Entry()
            cur.set_visibility(False)
            box.add(cur)
            box.add(Gtk.Label(label="New password:", xalign=0))
            new = Gtk.Entry()
            new.set_visibility(False)
            new.set_activates_default(True)
            box.add(new)
            dlg.show_all()
            resp = dlg.run()
            result = ((cur.get_text(), new.get_text())
                      if resp == Gtk.ResponseType.OK else None)
            dlg.destroy()
            return result

        def _ask_alias(self, d):
            dlg = Gtk.Dialog(title="Rename WD Passport", flags=0)
            dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                            "Save", Gtk.ResponseType.OK)
            dlg.set_default_response(Gtk.ResponseType.OK)
            box = dlg.get_content_area()
            box.set_spacing(8)
            box.set_border_width(12)
            box.add(Gtk.Label(label=f"Friendly name for #{d.serial_tail} "
                                    f"({d.size}):", xalign=0))
            entry = Gtk.Entry()
            entry.set_text(d.alias or "")
            entry.set_activates_default(True)
            box.add(entry)
            dlg.show_all()
            resp = dlg.run()
            name = entry.get_text().strip() if resp == Gtk.ResponseType.OK else None
            dlg.destroy()
            if name == "":
                name = None
            return name

    Tray()
    Gtk.main()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
