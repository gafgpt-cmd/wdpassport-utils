from .keepawake import run_keep_awake


def main(argv=None) -> int:
    import sys

    if argv is None:
        argv = sys.argv[1:]
    if "--help" in argv or "-h" in argv:
        print("Usage: wdpassport-gui")
        print()
        print("Launch the WD Passport GTK utility. Run with privileges that can access the block device.")
        return 0

    import threading

    import gi

    gi.require_version("Gtk", "4.0")
    try:
        gi.require_version("Adw", "1")
        from gi.repository import Adw
    except (ImportError, ValueError):
        Adw = None
    from gi.repository import Gio, Gtk

    from .actions import status_summary
    from .cli import open_device
    from .devices import find_passport_devices

    class PassportWindow(Gtk.ApplicationWindow):
        def __init__(self, app):
            super().__init__(application=app, title="WD Passport Utility")
            self.set_default_size(760, 560)
            self.keep_awake_stop = None
            self.keep_awake_thread = None
            self.device_paths = []

            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            root.set_margin_top(16)
            root.set_margin_bottom(16)
            root.set_margin_start(16)
            root.set_margin_end(16)
            self.set_child(root)

            header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            root.append(header)

            title = Gtk.Label(label="WD Passport Utility")
            title.add_css_class("title-2")
            title.set_hexpand(True)
            title.set_halign(Gtk.Align.START)
            header.append(title)

            self.device_combo = Gtk.ComboBoxText()
            self.device_combo.set_hexpand(False)
            header.append(self.device_combo)

            refresh_button = Gtk.Button(label="Refresh")
            refresh_button.connect("clicked", lambda _button: self.refresh_devices())
            header.append(refresh_button)

            self.status = Gtk.Label(label="Select a drive, then refresh status.")
            self.status.set_wrap(True)
            self.status.set_xalign(0)
            root.append(self.status)

            grid = Gtk.Grid(column_spacing=8, row_spacing=8)
            grid.set_column_homogeneous(True)
            root.append(grid)

            self._add_button(grid, "Status", 0, 0, self.refresh_status)
            self._add_button(grid, "Unlock", 1, 0, self.unlock_dialog)
            self._add_button(grid, "Set Password", 2, 0, self.set_password_dialog)
            self._add_button(grid, "Change Password", 0, 1, self.change_password_dialog)
            self._add_button(grid, "Remove Password", 1, 1, self.remove_password_dialog)
            self._add_button(grid, "Hint", 2, 1, self.hint_dialog)
            self._add_button(grid, "Sleep Off", 0, 2, lambda: self.with_device(lambda d: d.set_sleep_timer(0), "Sleep disabled."))
            self._add_button(grid, "Sleep 1h", 1, 2, lambda: self.with_device(lambda d: d.set_sleep_timer(3600), "Sleep timer set to 1 hour."))
            self._add_button(grid, "Keep Awake", 2, 2, self.toggle_keep_awake)
            self._add_button(grid, "Virtual CD Off", 0, 3, lambda: self.with_device(lambda d: d.set_virtual_cd_enabled(False), "Virtual CD disabled."))
            self._add_button(grid, "LED On", 1, 3, lambda: self.with_device(lambda d: d.set_led_brightness(255), "LED enabled."))
            self._add_button(grid, "LED Off", 2, 3, lambda: self.with_device(lambda d: d.set_led_brightness(0), "LED disabled."))
            self._add_button(grid, "Self Test", 0, 4, self.self_test)
            erase = self._add_button(grid, "Secure Erase", 2, 4, self.erase_dialog)
            erase.add_css_class("destructive-action")

            self.refresh_devices()

        def _add_button(self, grid, label, column, row, callback):
            button = Gtk.Button(label=label)
            button.set_hexpand(True)
            button.connect("clicked", lambda _button: callback())
            grid.attach(button, column, row, 1, 1)
            return button

        def selected_path(self):
            index = self.device_combo.get_active()
            if index < 0 or index >= len(self.device_paths):
                self.set_message("No drive selected.")
                return None
            return self.device_paths[index]

        def refresh_devices(self):
            self.device_combo.remove_all()
            self.device_paths = []
            try:
                import pyudev

                devices = find_passport_devices(pyudev.Context())
                self.device_paths = [device.device_node for device in devices]
            except Exception as exc:
                self.set_message(f"Device scan failed: {exc}")
                return
            for path in self.device_paths:
                self.device_combo.append_text(path)
            if self.device_paths:
                self.device_combo.set_active(0)
                self.refresh_status()
            else:
                self.set_message("No WD My Passport drive found.")

        def with_device(self, operation, success_message):
            path = self.selected_path()
            if not path:
                return
            try:
                operation(open_device(path))
                self.set_message(success_message)
            except Exception as exc:
                self.set_message(str(exc))

        def refresh_status(self):
            path = self.selected_path()
            if not path:
                return
            try:
                summary = status_summary(open_device(path), path)
                text = "\n".join(
                    [
                        f"Device: {summary['device']}",
                        f"Security status: {summary['security_status']}",
                        f"Encryption type: {summary['cipher']}",
                        f"Supported ciphers: {', '.join(summary['supported_ciphers'])}",
                        f"Hint: {summary['hint'] or '(none)'}",
                    ]
                )
                self.set_message(text)
            except Exception as exc:
                self.set_message(str(exc))

        def set_message(self, message):
            self.status.set_label(message)

        def password_entry(self):
            entry = Gtk.Entry()
            entry.set_visibility(False)
            entry.set_activates_default(True)
            return entry

        def simple_dialog(self, title, fields, on_submit):
            dialog = Gtk.Dialog(title=title, transient_for=self, modal=True)
            dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
            dialog.add_button("Apply", Gtk.ResponseType.OK)
            box = dialog.get_content_area()
            box.set_spacing(8)
            entries = {}
            for name, entry in fields:
                label = Gtk.Label(label=name)
                label.set_xalign(0)
                box.append(label)
                box.append(entry)
                entries[name] = entry
            dialog.connect("response", lambda d, response: self._dialog_response(d, response, entries, on_submit))
            dialog.present()

        def _dialog_response(self, dialog, response, entries, on_submit):
            if response == Gtk.ResponseType.OK:
                try:
                    on_submit({name: entry.get_text() for name, entry in entries.items()})
                except Exception as exc:
                    self.set_message(str(exc))
            dialog.destroy()

        def unlock_dialog(self):
            self.simple_dialog("Unlock Drive", [("Password", self.password_entry())], lambda fields: self.with_device(lambda d: d.unlock(fields["Password"]), "Device unlocked."))

        def set_password_dialog(self):
            fields = [("Password", self.password_entry()), ("Hint", Gtk.Entry())]
            self.simple_dialog("Set Password", fields, lambda _fields: self.set_message("Use CLI for first-pass password setup until hardware-tested."))

        def change_password_dialog(self):
            fields = [("Current Password", self.password_entry()), ("New Password", self.password_entry()), ("Hint", Gtk.Entry())]
            self.simple_dialog("Change Password", fields, lambda _fields: self.set_message("Use CLI for first-pass password changes until hardware-tested."))

        def remove_password_dialog(self):
            self.simple_dialog("Remove Password", [("Current Password", self.password_entry())], lambda _fields: self.set_message("Use CLI for first-pass password removal until hardware-tested."))

        def hint_dialog(self):
            self.simple_dialog("Set Hint", [("Hint", Gtk.Entry())], lambda _fields: self.set_message("Hint writing is available in CLI-backed protocol and awaits hardware validation."))

        def toggle_keep_awake(self):
            path = self.selected_path()
            if not path:
                return
            if self.keep_awake_stop:
                self.keep_awake_stop.set()
                self.keep_awake_stop = None
                self.set_message("Keep-awake stopped.")
                return
            self.keep_awake_stop = threading.Event()
            device = open_device(path)
            self.keep_awake_thread = threading.Thread(
                target=run_keep_awake,
                kwargs={"device": device, "interval": 60, "stop_event": self.keep_awake_stop},
                daemon=True,
            )
            self.keep_awake_thread.start()
            self.set_message("Keep-awake active. The drive will be touched every 60 seconds.")

        def self_test(self):
            self.with_device(lambda d: self.set_message(f"Self-test: {d.self_test()}"), "Self-test complete.")

        def erase_dialog(self):
            path = self.selected_path()
            if not path:
                return
            entry = Gtk.Entry()
            self.simple_dialog(
                "Secure Erase",
                [(f"Type {path} to erase all data", entry)],
                lambda fields: self._erase_if_confirmed(path, fields[f"Type {path} to erase all data"]),
            )

        def _erase_if_confirmed(self, path, confirmation):
            if confirmation != path:
                self.set_message("Erase cancelled.")
                return
            drive = open_device(path)
            status = drive.encryption_status()
            drive.reset_data_encryption_key(status.current_cipher, status.key_reset_enabler)
            self.set_message("Device erased.")

    if Adw is not None:
        class PassportApp(Adw.Application):
            def __init__(self):
                super().__init__(application_id="dev.wdpassport.utility")

            def do_activate(self):
                PassportWindow(self).present()
    else:
        class PassportApp(Gtk.Application):
            def __init__(self):
                super().__init__(application_id="dev.wdpassport.utility", flags=Gio.ApplicationFlags.FLAGS_NONE)

            def do_activate(self):
                PassportWindow(self).present()

    return PassportApp().run(argv)
