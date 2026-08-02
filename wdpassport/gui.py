"""GTK4 desktop GUI for the WD My Passport utility.

Privileged SCSI operations are delegated to the ``wd-priv`` helper through
``pkexec`` (we never open the block device directly), while mount / unmount /
lock go through ``udisksctl`` as the normal user. Every long-running command
runs on a worker thread and marshals its result back to the main loop with
``GLib.idle_add`` so the window never freezes.
"""

import os
import subprocess

from .launchers import privileged_command

COMMAND_TIMEOUT_SECONDS = 90


def run_cmd(cmd, stdin_text=None, timeout=COMMAND_TIMEOUT_SECONDS):
    """Run a bounded child command and return ``(returncode, stdout, stderr)``."""
    try:
        proc = subprocess.run(
            cmd, input=stdin_text, capture_output=True, text=True, timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"Command timed out after {timeout} seconds."
    except FileNotFoundError as exc:
        return 127, "", str(exc)


def priv(*args):
    """Build a ``pkexec`` argv for the privileged helper."""
    return privileged_command(*args)


def activate_main_window(app, window_factory):
    """Present the one control window owned by the application."""
    window = app.props.active_window
    if window is None:
        window = window_factory(app)
    window.set_icon_name("wdpassport")
    window.present()


def main(argv=None) -> int:
    import sys

    if argv is None:
        argv = sys.argv[1:]
    if "--help" in argv or "-h" in argv:
        print("Usage: wdpassport-gui")
        print()
        print("Launch the WD Passport GTK utility. Runs as a normal user; "
              "privileged operations are elevated per-command via pkexec.")
        return 0

    import threading
    import time

    import gi

    gi.require_version("Gtk", "4.0")
    try:
        gi.require_version("Adw", "1")
        from gi.repository import Adw
    except (ImportError, ValueError):
        Adw = None
    from gi.repository import Gdk, Gio, GLib, Gtk

    from .devices import list_drives, set_alias, virtual_cd_nodes

    CSS = """
    .locked   { color: #e01b24; font-weight: bold; }
    .unlocked { color: #2ec27e; font-weight: bold; }
    .drive-badge { padding: 4px 10px; border-radius: 6px; }
    """

    def priv_error(rc, out, err):
        """Return a friendly message for a failed pkexec run, or None on success."""
        if rc == 126:
            return "Authorization dismissed / cancelled."
        if rc == 127:
            return "Not authorized (pkexec)."
        if rc != 0:
            detail = (err or out).strip()
            return f"Command failed (rc={rc}): {detail}" if detail else \
                   f"Command failed (rc={rc})."
        return None

    class PassportWindow(Gtk.ApplicationWindow):
        def __init__(self, app):
            super().__init__(application=app, title="WD Passport Utility")
            self.set_default_size(780, 620)
            self.drives = []
            self._install_css()

            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            for setter in ("set_margin_top", "set_margin_bottom",
                           "set_margin_start", "set_margin_end"):
                getattr(root, setter)(16)
            self.set_child(root)

            # --- Header: title + drive picker + refresh -------------------
            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            root.append(header)

            title = Gtk.Label(label="WD Passport Utility")
            title.add_css_class("title-2")
            title.set_hexpand(True)
            title.set_halign(Gtk.Align.START)
            header.append(title)

            self.combo = Gtk.ComboBoxText()
            self.combo.set_hexpand(True)
            self.combo.connect("changed", lambda _c: self._update_selection())
            header.append(self.combo)

            self.refresh_button = Gtk.Button(label="Refresh")
            self.refresh_button.connect(
                "clicked", lambda _b: self.refresh_devices())
            header.append(self.refresh_button)

            # --- Selected-drive summary -----------------------------------
            info = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            root.append(info)

            self.lock_badge = Gtk.Label(label="—")
            self.lock_badge.add_css_class("drive-badge")
            self.lock_badge.set_halign(Gtk.Align.START)
            info.append(self.lock_badge)

            self.details = Gtk.Label(label="")
            self.details.set_wrap(True)
            self.details.set_xalign(0)
            self.details.set_hexpand(True)
            info.append(self.details)

            # --- Action grid ----------------------------------------------
            self.grid = Gtk.Grid(column_spacing=8, row_spacing=8)
            self.grid.set_column_homogeneous(True)
            root.append(self.grid)

            buttons = [
                ("Status",          self.act_status),
                ("Unlock",          self.dlg_unlock),
                ("Mount",           self.act_mount),
                ("Unmount",         self.act_unmount),
                ("Lock",            self.act_lock),
                ("Open Folder",     self.act_open),
                ("Identify",        self.act_identify),
                ("Set Password",    self.dlg_set_password),
                ("Change Password", self.dlg_change_password),
                ("Remove Password", self.dlg_remove_password),
                ("Sleep Off",       self.act_sleep_off),
                ("Sleep 1h",        self.act_sleep_1h),
                ("Virtual CD Off",  self.act_vcd_off),
                ("LED On",          self.act_led_on),
                ("LED Off",         self.act_led_off),
                ("Self Test",       self.act_self_test),
                ("Health",          self.act_health),
                ("Rename",          self.dlg_rename),
                ("Secure Erase",    self.dlg_erase),
            ]
            for i, (label, cb) in enumerate(buttons):
                btn = Gtk.Button(label=label)
                btn.set_hexpand(True)
                btn.connect("clicked", lambda _b, cb=cb: cb())
                if label == "Secure Erase":
                    btn.add_css_class("destructive-action")
                self.grid.attach(btn, i % 3, i // 3, 1, 1)

            # --- Status / output area -------------------------------------
            self.status = Gtk.Label(
                label="Select a drive, then choose an action.")
            self.status.set_wrap(True)
            self.status.set_xalign(0)
            self.status.set_yalign(0)
            self.status.set_selectable(True)
            self.status.set_vexpand(True)
            self.status.set_valign(Gtk.Align.START)
            root.append(self.status)

            self.refresh_devices()

        # -- infrastructure -----------------------------------------------
        def _install_css(self):
            # CSS is cosmetic (lock-badge colors). GTK4's CssProvider API varies
            # by version, so pick the right call and never let it block the
            # window from showing.
            try:
                provider = Gtk.CssProvider()
                if hasattr(provider, "load_from_string"):
                    provider.load_from_string(CSS)              # GTK 4.12+
                else:
                    provider.load_from_data(CSS.encode("utf-8"))  # older: bytes, 1 arg
                display = Gdk.Display.get_default()
                if display is not None:
                    Gtk.StyleContext.add_provider_for_display(
                        display, provider,
                        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            except Exception:
                pass

        def set_message(self, message):
            self.status.set_label(message)

        def selected_drive(self):
            idx = self.combo.get_active()
            if idx < 0 or idx >= len(self.drives):
                return None
            return self.drives[idx]

        def require_drive(self):
            drive = self.selected_drive()
            if drive is None:
                self.set_message("No drive selected.")
            return drive

        def refresh_devices(self, preserve_serial=None, completion_message=None):
            if preserve_serial is None:
                cur = self.selected_drive()
                preserve_serial = cur.serial if cur else None

            self.refresh_button.set_sensitive(False)

            def worker():
                try:
                    drives = list_drives()
                    error = None
                except Exception as exc:
                    drives = []
                    error = str(exc)
                GLib.idle_add(
                    self._apply_drives, drives, preserve_serial, error,
                    completion_message)

            threading.Thread(target=worker, daemon=True).start()

        def _apply_drives(self, drives, preserve_serial, error=None,
                          completion_message=None):
            self.refresh_button.set_sensitive(True)
            self.drives = drives
            if error is not None:
                self.set_message(f"Drive scan failed: {error}")
            self.combo.remove_all()
            for drive in self.drives:
                self.combo.append_text(drive.label())
            if self.drives:
                target = 0
                for i, drive in enumerate(self.drives):
                    if preserve_serial and drive.serial == preserve_serial:
                        target = i
                        break
                self.combo.set_active(target)
            else:
                self.set_message("No WD My Passport drive found. "
                                 "Connect a drive and press Refresh.")
            self._update_selection()
            if completion_message is not None and error is None:
                self.set_message(completion_message)
            return False

        def _update_selection(self):
            drive = self.selected_drive()
            self.lock_badge.remove_css_class("locked")
            self.lock_badge.remove_css_class("unlocked")
            if drive is None:
                self.lock_badge.set_label("—")
                self.details.set_label("")
                return
            if drive.is_locked:
                self.lock_badge.set_label("LOCKED")
                self.lock_badge.add_css_class("locked")
            else:
                self.lock_badge.set_label("UNLOCKED")
                self.lock_badge.add_css_class("unlocked")
            rows = [
                drive.label(),
                f"node {drive.node}   serial {drive.serial or '?'}   "
                f"size {drive.size}",
                f"model {drive.model}   port {drive.usb_port or '?'}",
            ]
            if drive.mountpoint:
                rows.append(f"mounted at {drive.mountpoint}")
            elif not drive.is_locked and drive.partition:
                rows.append(f"partition {drive.partition} (not mounted)")
            self.details.set_label("\n".join(rows))

        def _set_busy(self, busy, message=None):
            self.grid.set_sensitive(not busy)
            self.combo.set_sensitive(not busy)
            self.refresh_button.set_sensitive(not busy)
            if message is not None:
                self.set_message(message)

        def run_async(self, fn, working="Working…"):
            """Run ``fn`` (returns a status string) off the main thread."""
            self._set_busy(True, working)

            def worker():
                try:
                    msg = fn()
                except Exception as exc:  # never lose the worker to an exception
                    msg = f"Error: {exc}"
                GLib.idle_add(self._worker_done, msg)

            threading.Thread(target=worker, daemon=True).start()

        def _worker_done(self, msg):
            self._set_busy(False)
            self.refresh_devices(completion_message=msg)
            return False

        # -- privileged actions -------------------------------------------
        def act_status(self):
            drive = self.require_drive()
            if not drive:
                return
            node = drive.node

            def fn():
                rc, out, err = run_cmd(priv("status", "-d", node))
                problem = priv_error(rc, out, err)
                return problem or (out.strip() or "Status: (no output).")
            self.run_async(fn, "Reading status…")

        def act_identify(self):
            drive = self.require_drive()
            if not drive:
                return
            node = drive.node

            def fn():
                rc, out, err = run_cmd(
                    priv("identify", "-d", node, "--count", "8"))
                problem = priv_error(rc, out, err)
                return problem or "Identify: the drive LED is blinking."
            self.run_async(fn, "Blinking drive LED…")

        def _simple_priv(self, args, ok_msg, working):
            drive = self.require_drive()
            if not drive:
                return
            argv = list(args)

            def fn():
                rc, out, err = run_cmd(priv(*argv, "-d", drive.node))
                problem = priv_error(rc, out, err)
                return problem or ok_msg
            self.run_async(fn, working)

        def act_sleep_off(self):
            self._simple_priv(["sleep", "off"], "Sleep timer disabled.",
                              "Disabling sleep…")

        def act_sleep_1h(self):
            self._simple_priv(["sleep", "set", "3600"],
                              "Sleep timer set to 1 hour.", "Setting sleep…")

        def act_vcd_off(self):
            self._simple_priv(["vcd", "off"], "Virtual CD disabled.",
                              "Disabling virtual CD…")

        def act_led_on(self):
            self._simple_priv(["led", "on"], "LED enabled.", "Enabling LED…")

        def act_led_off(self):
            self._simple_priv(["led", "off"], "LED disabled.", "Disabling LED…")

        def act_self_test(self):
            drive = self.require_drive()
            if not drive:
                return
            node = drive.node

            def fn():
                rc, out, err = run_cmd(priv("self-test", "-d", node))
                problem = priv_error(rc, out, err)
                return problem or (out.strip() or "Self-test started.")
            self.run_async(fn, "Running self-test…")

        def act_health(self):
            drive = self.require_drive()
            if not drive:
                return
            node = drive.node

            def fn():
                rc, out, err = run_cmd(priv("health", "-d", node))
                if out.strip():
                    return out.strip()
                return priv_error(rc, out, err) or "No SMART data available."
            self.run_async(fn, "Reading S.M.A.R.T. health…")

        # -- unlock (privileged) then mount (user) ------------------------
        def dlg_unlock(self):
            drive = self.require_drive()
            if not drive:
                return
            entry = self._password_entry()
            self._form_dialog(
                "Unlock Drive", [("Password", entry)],
                lambda vals: self._do_unlock(drive.node, vals["Password"]))

        def _do_unlock(self, node, password):
            def fn():
                rc, out, err = run_cmd(
                    priv("unlock", "-d", node, "--password-stdin"),
                    stdin_text=password)
                problem = priv_error(rc, out, err)
                if problem:
                    return f"Unlock failed: {problem}"
                part = self._wait_for_partition(node)
                if not part:
                    return "Unlocked, but the partition did not appear."
                m_rc, m_out, m_err = run_cmd(
                    ["udisksctl", "mount", "-b", part])
                if m_rc == 0:
                    return f"Unlocked and mounted. {m_out.strip()}"
                return (f"Unlocked. Mount it manually — "
                        f"{(m_err or m_out).strip()}")
            self.run_async(fn, "Unlocking…")

        def _wait_for_partition(self, node, timeout=20):
            for _ in range(timeout):
                run_cmd(["udevadm", "settle"])
                for cand in (f"{node}1", f"{node}p1"):
                    if os.path.exists(cand):
                        return cand
                time.sleep(1)
            return None

        # -- mount / unmount / lock / open (unprivileged) -----------------
        def act_mount(self):
            drive = self.require_drive()
            if not drive:
                return
            if not drive.partition:
                self.set_message("No partition to mount — the drive is locked.")
                return
            part = drive.partition

            def fn():
                rc, out, err = run_cmd(["udisksctl", "mount", "-b", part])
                if rc == 0:
                    return out.strip() or "Mounted."
                return f"Mount failed: {(err or out).strip()}"
            self.run_async(fn, "Mounting…")

        def act_unmount(self):
            drive = self.require_drive()
            if not drive:
                return
            if not drive.partition:
                self.set_message("Nothing to unmount.")
                return
            part = drive.partition

            def fn():
                rc, out, err = run_cmd(["udisksctl", "unmount", "-b", part])
                if rc == 0:
                    return out.strip() or "Unmounted."
                return f"Unmount failed: {(err or out).strip()}"
            self.run_async(fn, "Unmounting…")

        def act_lock(self):
            drive = self.require_drive()
            if not drive:
                return
            node, part, mountpoint, serial = (
                drive.node, drive.partition, drive.mountpoint, drive.serial)

            def fn():
                if part and mountpoint:
                    run_cmd(["udisksctl", "unmount", "-b", part])
                # The WD Virtual CD unit blocks power-off while mounted.
                for vcd in virtual_cd_nodes(serial):
                    run_cmd(["udisksctl", "unmount", "-b", vcd])
                rc, out, err = run_cmd(
                    ["udisksctl", "power-off", "-b", node])
                if rc == 0:
                    return "Drive locked / powered off. Reconnect to reuse."
                return f"Power-off failed: {(err or out).strip()}"
            self.run_async(fn, "Locking…")

        def act_open(self):
            drive = self.require_drive()
            if not drive:
                return
            if not drive.mountpoint:
                self.set_message("Drive is not mounted.")
                return
            mountpoint = drive.mountpoint

            def fn():
                rc, out, err = run_cmd(["xdg-open", mountpoint])
                if rc == 0:
                    return f"Opened {mountpoint}"
                return f"Open failed: {(err or out).strip()}"
            self.run_async(fn, "Opening folder…")

        # -- password management ------------------------------------------
        def dlg_set_password(self):
            drive = self.require_drive()
            if not drive:
                return
            pw = self._password_entry()
            hint = Gtk.Entry()
            hint.set_activates_default(True)
            self._form_dialog(
                "Set Password",
                [("New Password", pw), ("Hint (optional)", hint)],
                lambda vals: self._do_set_password(
                    drive.node, vals["New Password"], vals["Hint (optional)"]))

        def _do_set_password(self, node, new_pw, hint):
            if not new_pw:
                self.set_message("Password must not be empty.")
                return
            args = ["password", "set", "-d", node, "--stdin"]
            if hint:
                args += ["--hint", hint]

            def fn():
                rc, out, err = run_cmd(priv(*args), stdin_text=new_pw)
                problem = priv_error(rc, out, err)
                return problem or "Password set. The drive is now protected."
            self.run_async(fn, "Setting password…")

        def dlg_change_password(self):
            drive = self.require_drive()
            if not drive:
                return
            cur = self._password_entry()
            new = self._password_entry()
            self._form_dialog(
                "Change Password",
                [("Current Password", cur), ("New Password", new)],
                lambda vals: self._do_change_password(
                    drive.node, vals["Current Password"], vals["New Password"]))

        def _do_change_password(self, node, cur_pw, new_pw):
            if not new_pw:
                self.set_message("New password must not be empty.")
                return

            def fn():
                rc, out, err = run_cmd(
                    priv("password", "change", "-d", node, "--stdin"),
                    stdin_text=f"{cur_pw}\n{new_pw}\n")
                problem = priv_error(rc, out, err)
                return problem or "Password changed."
            self.run_async(fn, "Changing password…")

        def dlg_remove_password(self):
            drive = self.require_drive()
            if not drive:
                return
            cur = self._password_entry()
            self._form_dialog(
                "Remove Password", [("Current Password", cur)],
                lambda vals: self._do_remove_password(
                    drive.node, vals["Current Password"]))

        def _do_remove_password(self, node, cur_pw):
            def fn():
                rc, out, err = run_cmd(
                    priv("password", "remove", "-d", node, "--stdin"),
                    stdin_text=cur_pw)
                problem = priv_error(rc, out, err)
                return problem or "Password removed. The drive is unprotected."
            self.run_async(fn, "Removing password…")

        # -- rename (alias) -----------------------------------------------
        def dlg_rename(self):
            drive = self.require_drive()
            if not drive:
                return
            entry = Gtk.Entry()
            entry.set_text(drive.alias or "")
            entry.set_activates_default(True)
            self._form_dialog(
                "Rename Drive", [("Friendly name", entry)],
                lambda vals: self._do_rename(
                    drive.serial, vals["Friendly name"].strip()))

        def _do_rename(self, serial, name):
            if not name:
                self.set_message("Name must not be empty.")
                return
            try:
                set_alias(serial, name)
            except Exception as exc:
                self.set_message(f"Rename failed: {exc}")
                return
            self.refresh_devices(preserve_serial=serial)
            self.set_message(f"Renamed to “{name}”.")

        # -- secure erase (destructive, typed confirmation) ---------------
        def dlg_erase(self):
            drive = self.require_drive()
            if not drive:
                return
            node = drive.node
            dialog = Gtk.Dialog(
                title="Secure Erase", transient_for=self, modal=True)
            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            erase_btn = dialog.add_button("Erase", Gtk.ResponseType.OK)
            erase_btn.add_css_class("destructive-action")

            box = dialog.get_content_area()
            box.set_spacing(8)
            for setter in ("set_margin_top", "set_margin_bottom",
                           "set_margin_start", "set_margin_end"):
                getattr(box, setter)(12)
            warn = Gtk.Label(
                label=("This ERASES ALL DATA on the drive and resets the "
                       "encryption key.\nThis cannot be undone."))
            warn.set_wrap(True)
            warn.set_xalign(0)
            box.append(warn)
            prompt = Gtk.Label(label=f"Type the node path {node} to confirm:")
            prompt.set_xalign(0)
            box.append(prompt)
            entry = Gtk.Entry()
            box.append(entry)

            def on_response(dlg, response):
                if response == Gtk.ResponseType.OK:
                    if entry.get_text().strip() == node:
                        dlg.destroy()
                        self._do_erase(node)
                        return
                    self.set_message("Erase cancelled — confirmation did not "
                                     "match the node path.")
                dlg.destroy()

            dialog.connect("response", on_response)
            dialog.present()

        def _do_erase(self, node):
            def fn():
                rc, out, err = run_cmd(priv("erase", "-d", node, "--force"))
                problem = priv_error(rc, out, err)
                return problem or "Secure erase complete. All data was wiped."
            self.run_async(fn, "Erasing…")

        # -- dialog helpers -----------------------------------------------
        def _password_entry(self):
            entry = Gtk.Entry()
            entry.set_visibility(False)
            entry.set_activates_default(True)
            return entry

        def _form_dialog(self, title, fields, on_submit):
            dialog = Gtk.Dialog(title=title, transient_for=self, modal=True)
            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            ok = dialog.add_button("Apply", Gtk.ResponseType.OK)
            ok.add_css_class("suggested-action")
            dialog.set_default_response(Gtk.ResponseType.OK)
            box = dialog.get_content_area()
            box.set_spacing(8)
            for setter in ("set_margin_top", "set_margin_bottom",
                           "set_margin_start", "set_margin_end"):
                getattr(box, setter)(12)
            for name, entry in fields:
                label = Gtk.Label(label=name)
                label.set_xalign(0)
                box.append(label)
                box.append(entry)

            def on_response(dlg, response):
                if response == Gtk.ResponseType.OK:
                    values = {name: entry.get_text() for name, entry in fields}
                    dlg.destroy()
                    try:
                        on_submit(values)
                    except Exception as exc:
                        self.set_message(str(exc))
                else:
                    dlg.destroy()

            dialog.connect("response", on_response)
            dialog.present()

    if Adw is not None:
        class PassportApp(Adw.Application):
            def __init__(self):
                super().__init__(application_id="dev.wdpassport.utility")

            def do_activate(self):
                activate_main_window(self, PassportWindow)
    else:
        class PassportApp(Gtk.Application):
            def __init__(self):
                super().__init__(
                    application_id="dev.wdpassport.utility",
                    flags=Gio.ApplicationFlags.FLAGS_NONE)

            def do_activate(self):
                activate_main_window(self, PassportWindow)

    # Pass None (not the stripped argv) so GApplication activates and shows the
    # window; an empty argv list is read as argc=0 and returns without activating.
    return PassportApp().run(None)
