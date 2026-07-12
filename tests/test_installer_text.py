from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InstallerTextTests(unittest.TestCase):
    def test_installer_mentions_gui_prerequisites_and_launchers(self):
        text = (ROOT / "install-mx-debian.sh").read_text()
        self.assertIn("python3-gi", text)
        self.assertIn("gir1.2-gtk-4.0", text)
        self.assertIn("gir1.2-adw-1", text)
        self.assertIn("wdpassport", text)
        self.assertIn("wdpassport-gui", text)
        self.assertIn(".local/share/applications", text)
        self.assertIn("--system-site-packages", text)

    def test_desktop_launcher_execs_gui(self):
        text = (ROOT / "wdpassport-gui.desktop.in").read_text()
        self.assertIn("Name=WD Passport Utility", text)
        self.assertIn("Exec=wdpassport-gui", text)
        self.assertIn("Categories=Utility;", text)


if __name__ == "__main__":
    unittest.main()
