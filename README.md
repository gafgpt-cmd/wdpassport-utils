# WD My Passport Utility for Linux

A Linux CLI and GTK GUI for managing Western Digital My Passport hardware
encryption and power behavior.

WD My Passport drives support hardware encryption. New drives arrive in a
passwordless state. After a password is set, drives become locked when unplugged
and must be unlocked before Linux can mount the real data volume.

This utility can:

* show drive status, cipher, supported ciphers, and password hint;
* unlock an encrypted drive;
* set, change, and remove the drive password;
* disable or set the drive sleep timer;
* keep the drive awake during long copies or other intensive work;
* toggle WD virtual CD and LED state where the model supports it;
* run a basic self-test;
* report S.M.A.R.T. drive health (temperature, power-on hours, sector counts);
* reset the drive encryption key in case of a lost password.

This tool was originally written by
[0-duke](https://github.com/0-duke/wdpassport-utils) in 2015 based on reverse
engineering research by [DanLukes](https://github.com/DanLukes) and an
implementation by DanLukes and [KenMacD](https://github.com/KenMacD/wdpassport-utils).
[crypto-universe](https://github.com/crypto-universe/wdpassport-utils) converted
the project and `py_sg` interface to Python 3. This version keeps the Python
Linux base and ports Linux-relevant features from
`maboroshinokiseki/My-My-Passport-Utility`.

The Linux packaging (Debian `.deb`), the GTK system-tray applet and control
window, drive identification, and the dependency-free pure-Python SCSI transport
(`sgio.py`, replacing the compiled `py_sg` extension) in this version were
developed with [Claude Code](https://claude.com/claude-code) (Anthropic).

## Installing on Linux

The installer supports Debian/Ubuntu (including MX Linux), Fedora/RHEL, Arch
Linux, and openSUSE. It installs the application into a user-owned virtual
environment with [uv](https://docs.astral.sh/uv/); only GTK and other system
prerequisites are installed with elevated privileges. The program still needs
root privileges, polkit, or equivalent permissions when it opens the physical
drive.

From this repository, run:

```bash
./install-linux.sh
```

The installer automatically detects `apt`, `dnf`, `pacman`, or `zypper`, then:

* installs Python, PyGObject, GTK4, libadwaita, PolicyKit, udisks2, util-linux,
  notifications, SMART tools, compiler, and libudev/systemd development
  prerequisites using the native package manager;
* installs `uv` into `$HOME/.local/bin` when it is not already available;
* creates or updates `$HOME/.local/share/wdpassport-utils-venv` with access to
  the distro-provided GTK bindings;
* installs this checkout and its Python dependencies into that environment
  through `uv`;
* links `$HOME/.local/bin/wdpassport`, `$HOME/.local/bin/wdpassport-gui`, and
  `$HOME/.local/bin/wd-tray`;
* installs the application icon and desktop launcher;
* installs a tray autostart entry under `$HOME/.config/autostart`.

If `$HOME/.local/bin` is not in your `PATH`, add it in your shell profile:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

For automation or unusual systems, set `WDPASSPORT_PACKAGE_MANAGER` explicitly
to `apt`, `dnf`, `pacman`, or `zypper`. `WDPASSPORT_VENV_DIR` and
`WDPASSPORT_BIN_DIR` override the virtual-environment and command directories;
the standard `XDG_DATA_HOME` and `XDG_CONFIG_HOME` variables control desktop
data and autostart locations. After installing the system prerequisites listed
in `install-linux.sh`, the equivalent manual `uv` commands are:

```bash
uv venv --system-site-packages --python python3 "$HOME/.local/share/wdpassport-utils-venv"
uv pip install --python "$HOME/.local/share/wdpassport-utils-venv/bin/python" --upgrade .
ln -sfn "$HOME/.local/share/wdpassport-utils-venv/bin/wdpassport" "$HOME/.local/bin/wdpassport"
ln -sfn "$HOME/.local/share/wdpassport-utils-venv/bin/wdpassport-gui" "$HOME/.local/bin/wdpassport-gui"
ln -sfn "$HOME/.local/share/wdpassport-utils-venv/bin/wd-tray" "$HOME/.local/bin/wd-tray"
```

## CLI Usage

Run the CLI as root, or as a user that has permission to manage the raw block
device. Use the disk path, such as `/dev/sdb`, not a partition path.

`--device` is optional: omit it and the tool auto-detects the single connected
WD My Passport (for example `sudo wdpassport status`). Pass `--device` only when
several WD drives are attached — the tool then lists them so you can pick one.

Show status:

```bash
sudo wdpassport status --device /dev/sdX
```

Unlock (add `--mount` / `-m` to rescan and mount the drive right after):

```bash
sudo wdpassport unlock
sudo wdpassport unlock --mount
```

Drive health (S.M.A.R.T., needs the `smartmontools` package):

```bash
sudo wdpassport health          # overall health, temperature, power-on hours, sectors
sudo wdpassport health --raw    # full smartctl report
```

Password operations:

```bash
sudo wdpassport password set --device /dev/sdX
sudo wdpassport password change --device /dev/sdX
sudo wdpassport password remove --device /dev/sdX
```

Drive sleep and long-copy protection:

```bash
sudo wdpassport sleep status --device /dev/sdX
sudo wdpassport sleep off --device /dev/sdX
sudo wdpassport sleep set 3600 --device /dev/sdX
sudo wdpassport keep-awake --device /dev/sdX --interval 60
```

`sleep off` asks the drive firmware not to enter standby. `keep-awake` is an
active guard that periodically reads status so the drive does not go idle while
you are copying data for hours.

Device controls:

```bash
sudo wdpassport vcd status --device /dev/sdX
sudo wdpassport vcd off --device /dev/sdX
sudo wdpassport led status --device /dev/sdX
sudo wdpassport led off --device /dev/sdX
sudo wdpassport led on --device /dev/sdX
sudo wdpassport self-test --device /dev/sdX
```

Advanced password blob operations:

```bash
sudo wdpassport blob generate --output ./unlock.blob
sudo wdpassport blob unlock ./unlock.blob --device /dev/sdX
```

Password blob files are unlock material. Treat them like passwords.

Secure erase:

```bash
sudo wdpassport erase --device /dev/sdX
```

Erase resets the drive encryption key. Existing data becomes unrecoverable and
you will need to create a new partition table and filesystem.

## GUI

```bash
wdpassport-gui
```

The GUI provides normal Linux controls: status, unlock, password dialogs, sleep
off/set, keep-awake, virtual CD, LED, self-test, and secure erase confirmation.
Advanced salt/iteration options and password blob files are CLI-only.

## Disclaimer

Use this tool and any information in this repository at your own risk. It was
developed without official Western Digital documentation for the raw SCSI vendor
interface. No responsibility is accepted for data loss or device damage.
