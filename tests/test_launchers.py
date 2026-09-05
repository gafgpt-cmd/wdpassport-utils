from unittest import mock
import unittest


class PrivilegedLauncherTests(unittest.TestCase):
    def test_user_install_uses_absolute_cli_from_path(self):
        from wdpassport.launchers import privileged_command

        with mock.patch(
            "wdpassport.launchers.os.path.exists", return_value=False
        ), mock.patch(
            "wdpassport.launchers._sibling_of_current_interpreter", return_value=""
        ), mock.patch(
            "wdpassport.launchers.shutil.which",
            return_value="/home/test/.local/bin/wdpassport",
        ):
            command = privileged_command("unlock", "-d", "/dev/sda")

        self.assertEqual(
            command,
            [
                "pkexec",
                "/home/test/.local/bin/wdpassport",
                "unlock",
                "-d",
                "/dev/sda",
            ],
        )

    def test_packaged_install_prefers_privileged_helper(self):
        from wdpassport.launchers import privileged_command

        with mock.patch("wdpassport.launchers.os.path.exists", return_value=True):
            command = privileged_command("status")

        self.assertEqual(
            command, ["pkexec", "/usr/lib/wdpassport/wd-priv", "status"]
        )


class SingleWindowTests(unittest.TestCase):
    def test_activation_reuses_and_presents_existing_window(self):
        from wdpassport.gui import activate_main_window

        existing = mock.Mock()
        app = mock.Mock()
        app.props.active_window = existing
        factory = mock.Mock()

        activate_main_window(app, factory)

        factory.assert_not_called()
        existing.set_icon_name.assert_called_once_with("wdpassport")
        existing.present.assert_called_once_with()

    def test_first_activation_creates_and_presents_window(self):
        from wdpassport.gui import activate_main_window

        created = mock.Mock()
        app = mock.Mock()
        app.props.active_window = None
        factory = mock.Mock(return_value=created)

        activate_main_window(app, factory)

        factory.assert_called_once_with(app)
        created.set_icon_name.assert_called_once_with("wdpassport")
        created.present.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()


class ExecutableResolutionTests(unittest.TestCase):
    """The tray must find our console scripts even when bin/ is off PATH."""

    def test_sibling_of_interpreter_beats_path(self):
        # A venv or --user install the desktop session never exported: the
        # entry point sits beside the interpreter, so prefer it over any
        # same-named binary that happens to be on PATH.
        from wdpassport.launchers import find_executable

        with mock.patch(
            "wdpassport.launchers._sibling_of_current_interpreter",
            return_value="/opt/venv/bin/wdpassport",
        ), mock.patch(
            "wdpassport.launchers.shutil.which", return_value="/usr/bin/wdpassport"
        ), mock.patch("wdpassport.launchers.os.path.realpath", side_effect=lambda p: p):
            self.assertEqual(find_executable("wdpassport"), "/opt/venv/bin/wdpassport")

    def test_env_override_wins(self):
        from wdpassport.launchers import find_executable

        with mock.patch.dict("os.environ", {"WDPASSPORT_BIN": "/custom/wdpassport"}), \
             mock.patch("wdpassport.launchers.os.path.realpath", side_effect=lambda p: p):
            self.assertEqual(
                find_executable("wdpassport", "WDPASSPORT_BIN"), "/custom/wdpassport"
            )

    def test_missing_executable_returns_empty(self):
        from wdpassport.launchers import find_executable

        with mock.patch(
            "wdpassport.launchers._sibling_of_current_interpreter", return_value=""
        ), mock.patch("wdpassport.launchers.shutil.which", return_value=None):
            self.assertEqual(find_executable("nope"), "")

    def test_gui_command_falls_back_to_module(self):
        """No console script installed at all must still open the panel."""
        import sys

        from wdpassport.launchers import gui_command

        with mock.patch("wdpassport.launchers.find_executable", return_value=""):
            self.assertEqual(
                gui_command(), [sys.executable, "-m", "wdpassport.gui"]
            )

    def test_gui_command_uses_resolved_executable(self):
        from wdpassport.launchers import gui_command

        with mock.patch(
            "wdpassport.launchers.find_executable",
            return_value="/opt/venv/bin/wdpassport-gui",
        ):
            self.assertEqual(gui_command(), ["/opt/venv/bin/wdpassport-gui"])
