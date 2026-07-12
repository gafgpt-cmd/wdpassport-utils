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

## Installing on MX Linux or Debian

This project installs into a user-owned virtual environment instead of using
`sudo pip`. The program still needs root privileges, polkit, or equivalent
permissions when it opens the physical drive.

From this repository, run:

```bash
./install-mx-debian.sh
```

The installer:

* installs Debian package prerequisites with `apt-get`;
* creates or updates `$HOME/.local/share/wdpassport-utils-venv`;
* installs this checkout and its Python dependencies into that venv;
* links `$HOME/.local/bin/wdpassport` and `$HOME/.local/bin/wdpassport-gui`;
* installs a desktop launcher under `$HOME/.local/share/applications`.

If `$HOME/.local/bin` is not in your `PATH`, add it in your shell profile:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Manual prerequisite install:

```bash
sudo apt-get install python3 python3-dev python3-venv python3-pip python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 git build-essential libudev-dev
python3 -m venv --system-site-packages "$HOME/.local/share/wdpassport-utils-venv"
"$HOME/.local/share/wdpassport-utils-venv/bin/python" -m pip install --upgrade pip setuptools wheel
"$HOME/.local/share/wdpassport-utils-venv/bin/python" -m pip install .
ln -sfn "$HOME/.local/share/wdpassport-utils-venv/bin/wdpassport" "$HOME/.local/bin/wdpassport"
ln -sfn "$HOME/.local/share/wdpassport-utils-venv/bin/wdpassport-gui" "$HOME/.local/bin/wdpassport-gui"
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

Unlock:

```bash
sudo wdpassport unlock --device /dev/sdX
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
sudo wdpassport-gui
```

The GUI provides normal Linux controls: status, unlock, password dialogs, sleep
off/set, keep-awake, virtual CD, LED, self-test, and secure erase confirmation.
Advanced salt/iteration options and password blob files are CLI-only.

## Disclaimer

Use this tool and any information in this repository at your own risk. It was
developed without official Western Digital documentation for the raw SCSI vendor
interface. No responsibility is accepted for data loss or device damage.
