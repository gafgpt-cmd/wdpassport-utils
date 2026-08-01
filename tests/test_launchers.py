from unittest import mock
import unittest


class PrivilegedLauncherTests(unittest.TestCase):
    def test_user_install_uses_absolute_cli_from_path(self):
        from wdpassport.launchers import privileged_command

        with mock.patch(
            "wdpassport.launchers.os.path.exists", return_value=False
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
