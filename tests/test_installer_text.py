import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install-linux.sh"


class InstallerTests(unittest.TestCase):
    def run_installer(self, package_manager: str, *, uv_available: bool = True,
                      existing_venv: bool = False, bin_name: str = "commands"):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            bin_dir = temp / "bin"
            bin_dir.mkdir()
            log = temp / "commands.log"

            (bin_dir / "sudo").write_text(
                "#!/usr/bin/env bash\nprintf 'sudo %s\\n' \"$*\" >> \"$WDPASSPORT_TEST_LOG\"\n"
            )
            fake_uv = temp / "fake-uv"
            fake_uv.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    printf 'uv %s\n' "$*" >> "$WDPASSPORT_TEST_LOG"
                    if [[ "$1" == "venv" ]]; then
                      target="${@: -1}"
                      [[ -d "$target" ]] && exit 2
                      mkdir -p "$target/bin"
                      touch "$target/bin/python"
                    fi
                    """
                )
            )
            if uv_available:
                (bin_dir / "uv").symlink_to(fake_uv)
            else:
                (bin_dir / "curl").write_text(
                    textwrap.dedent(
                        """\
                        #!/usr/bin/env bash
                        output="${@: -1}"
                        cat > "$output" <<'INSTALLER'
                        #!/usr/bin/env sh
                        echo 'installing uv'
                        cp "$WDPASSPORT_FAKE_UV" "$UV_INSTALL_DIR/uv"
                        chmod +x "$UV_INSTALL_DIR/uv"
                        INSTALLER
                        """
                    )
                )
                (bin_dir / "curl").chmod(0o755)
            (bin_dir / "sudo").chmod(0o755)
            fake_uv.chmod(0o755)

            env = os.environ.copy()
            venv = temp / "venv"
            if existing_venv:
                (venv / "bin").mkdir(parents=True)
                (venv / "bin/python").write_text("")
                (venv / "bin/python").chmod(0o755)
                (venv / "sentinel").write_text("keep")
            commands_dir = temp / bin_name
            env.update(
                {
                    "HOME": str(temp / "home"),
                    "PATH": (
                        f"{bin_dir}:/usr/bin:/bin"
                        if not uv_available
                        else f"{bin_dir}:{env['PATH']}"
                    ),
                    "WDPASSPORT_BIN_DIR": str(commands_dir),
                    "WDPASSPORT_FAKE_UV": str(fake_uv),
                    "WDPASSPORT_PACKAGE_MANAGER": package_manager,
                    "WDPASSPORT_TEST_LOG": str(log),
                    "WDPASSPORT_VENV_DIR": str(venv),
                    "XDG_CONFIG_HOME": str(temp / "config"),
                    "XDG_DATA_HOME": str(temp / "data"),
                }
            )
            result = subprocess.run(
                [str(INSTALLER)],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            commands = log.read_text() if log.exists() else ""
            launcher = temp / "data/applications/dev.wdpassport.utility.desktop"
            autostart = temp / "config/autostart/wd-tray.desktop"
            artifacts = {
                "cli": (commands_dir / "wdpassport").is_symlink(),
                "gui": (commands_dir / "wdpassport-gui").is_symlink(),
                "tray": (commands_dir / "wd-tray").is_symlink(),
                "venv_preserved": (venv / "sentinel").is_file(),
                "icon": (temp / "data/icons/hicolor/scalable/apps/wdpassport.svg").is_file(),
                "autostart": autostart.read_text() if autostart.exists() else "",
                "tray_desktop": (temp / "data/applications/wd-tray.desktop").is_file(),
            }
            return (
                result,
                commands,
                launcher.read_text() if launcher.exists() else "",
                artifacts,
            )

    def test_apt_install_uses_uv_and_preserves_gui_and_desktop_support(self):
        result, commands, launcher, artifacts = self.run_installer("apt")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sudo apt-get update", commands)
        self.assertIn("python3-gi", commands)
        self.assertIn("gir1.2-gtk-4.0", commands)
        self.assertIn("gir1.2-adw-1", commands)
        self.assertNotIn("python3-pip", commands)
        self.assertIn("uv venv --system-site-packages", commands)
        self.assertIn("uv pip install --python", commands)
        self.assertIn("Exec=", launcher)
        self.assertIn("wdpassport-gui", launcher)
        self.assertIn("Icon=wdpassport", launcher)
        self.assertTrue(artifacts["cli"])
        self.assertTrue(artifacts["gui"])
        self.assertTrue(artifacts["tray"])
        self.assertTrue(artifacts["icon"])
        self.assertIn("Exec=", artifacts["autostart"])
        self.assertIn("wd-tray", artifacts["autostart"])
        self.assertTrue(artifacts["tray_desktop"])

    def test_installer_bootstraps_uv_when_it_is_not_on_path(self):
        result, commands, _, _ = self.run_installer("apt", uv_available=False)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("uv venv --system-site-packages", commands)
        self.assertIn("uv pip install --python", commands)

    def test_existing_environment_is_updated_without_recreation(self):
        result, commands, _, artifacts = self.run_installer("apt", existing_venv=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("uv venv", commands)
        self.assertIn("uv pip install --python", commands)
        self.assertTrue(artifacts["venv_preserved"])

    def test_desktop_launcher_escapes_unusual_bin_path(self):
        result, _, launcher, artifacts = self.run_installer(
            "apt", bin_name='bin & "tools" \\ local'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Exec="', launcher)
        self.assertIn(r'bin & \"tools\" \\ local/wdpassport-gui', launcher)
        self.assertIn(r'bin & \"tools\" \\ local/wd-tray', artifacts["autostart"])
        self.assertNotIn("@BINDIR@", launcher)

    def test_dnf_install_preserves_gui_and_system_dependencies(self):
        result, commands, _, _ = self.run_installer("dnf")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sudo dnf install -y", commands)
        self.assertIn("python3-gobject", commands)
        self.assertIn("gtk4", commands)
        self.assertIn("libadwaita", commands)
        self.assertIn("systemd-devel", commands)
        self.assertIn("polkit", commands)
        self.assertIn("udisks2", commands)

    def test_pacman_install_preserves_gui_and_system_dependencies(self):
        result, commands, _, _ = self.run_installer("pacman")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sudo pacman -Syu --needed --noconfirm", commands)
        self.assertIn("python-gobject", commands)
        self.assertIn("gtk4", commands)
        self.assertIn("libadwaita", commands)
        self.assertIn("systemd", commands)

    def test_zypper_install_preserves_gui_and_system_dependencies(self):
        result, commands, _, _ = self.run_installer("zypper")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sudo zypper --non-interactive install", commands)
        self.assertIn("python3-gobject", commands)
        self.assertIn("typelib-1_0-Gtk-4_0", commands)
        self.assertIn("typelib-1_0-Adw-1", commands)
        self.assertIn("systemd-devel", commands)

    def test_unsupported_package_manager_fails_with_supported_choices(self):
        result, _, _, _ = self.run_installer("apk")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("apt, dnf, pacman, or zypper", result.stderr)

    def test_desktop_launcher_execs_gui(self):
        text = (ROOT / "wdpassport-gui.desktop.in").read_text()
        self.assertIn("Name=WD Passport Utility", text)
        self.assertIn('Exec="@BINDIR@/wdpassport-gui"', text)
        self.assertIn("Categories=Utility;", text)

    def test_cross_distribution_installer_has_generic_name(self):
        self.assertTrue((ROOT / "install-linux.sh").is_file())
        self.assertFalse((ROOT / "install-mx-debian.sh").exists())


if __name__ == "__main__":
    unittest.main()
