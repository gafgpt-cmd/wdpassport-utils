"""WD My Passport drive discovery.

Two layers:

* Legacy udev predicate helpers (``is_passport_device`` / ``find_passport_devices``)
  kept for the existing tests and any pyudev-based callers.
* A pure-stdlib ``list_drives()`` used by the CLI, GUI and tray. It needs no
  third-party module, so the package stays flavor-agnostic, and it returns rich
  identification data (friendly name, serial, size, model, USB port, lock
  state, mountpoint) to make "which drive do I unlock?" obvious.
"""

from dataclasses import dataclass
import glob
import os
import subprocess

BYID = "/dev/disk/by-id"
ALIAS_FILE = os.path.expanduser(
    os.environ.get("WD_ALIASES", "~/.config/wd-drives.conf")
)


# ---------------------------------------------------------------------------
# Legacy pyudev-based helpers (used by tests)
# ---------------------------------------------------------------------------

def is_passport_device(disk_device) -> bool:
    device = disk_device
    while device is not None:
        if "ID_SERIAL" in device:
            if device.properties["ID_SERIAL"].startswith("Western_Digital_My_"):
                return True
        device = device.parent
    return False


def find_passport_devices(context, forced_device=None) -> list:
    passport_devices = []
    for disk_device in context.list_devices(subsystem="block", DEVTYPE="disk"):
        if forced_device and disk_device.device_node != forced_device:
            continue
        if is_passport_device(disk_device):
            passport_devices.append(disk_device)
    return passport_devices


# ---------------------------------------------------------------------------
# Pure-stdlib rich discovery
# ---------------------------------------------------------------------------

@dataclass
class Drive:
    node: str            # /dev/sda
    serial: str          # full serial
    model: str           # WD My Passport 0820
    size: str            # 1.8T
    usb_port: str        # e.g. 1-2  (physical port; distinguishes identical drives)
    is_locked: bool
    partition: str = ""  # /dev/sda1 when unlocked
    mountpoint: str = ""
    alias: str = ""      # friendly name from the alias file

    @property
    def serial_tail(self) -> str:
        return self.serial[-8:] if self.serial else ""

    def label(self) -> str:
        """Human label for menus/pickers — leads with the friendly name."""
        state = "LOCKED" if self.is_locked else "unlocked"
        head = self.alias or f"WD {self.size}"
        parts = [head, f"#{self.serial_tail}"]
        if self.alias:
            parts.append(self.size)
        loc = f"port {self.usb_port}" if self.usb_port else self.node
        return f"{' · '.join(parts)}  [{loc}]  – {state}"


def _read_aliases() -> dict:
    aliases = {}
    try:
        with open(ALIAS_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # format: "<name...> <serial>" — serial is the last token, so the
                # friendly name may contain spaces.
                parts = line.rsplit(None, 1)
                if len(parts) == 2 and parts[1]:
                    aliases[parts[1]] = parts[0]
    except OSError:
        pass
    return aliases


def set_alias(serial: str, name: str) -> None:
    """Add/replace a friendly name for a serial in the alias file."""
    os.makedirs(os.path.dirname(ALIAS_FILE), exist_ok=True)
    lines, replaced = [], False
    if os.path.exists(ALIAS_FILE):
        with open(ALIAS_FILE, encoding="utf-8") as fh:
            for line in fh:
                s = line.strip()
                existing = s.rsplit(None, 1)[-1] if s and not s.startswith("#") else ""
                if existing == serial:
                    lines.append(f"{name} {serial}\n")
                    replaced = True
                else:
                    lines.append(line)
    if not replaced:
        lines.append(f"{name} {serial}\n")
    with open(ALIAS_FILE, "w", encoding="utf-8") as fh:
        fh.writelines(lines)


def _serial_of(link_name: str) -> str:
    base = os.path.basename(link_name)
    core = base[len("usb-WD_My_Passport_"):] if base.startswith("usb-WD_My_Passport_") else base
    core = core.rsplit("-", 1)[0]
    if "_" in core:
        core = core.split("_", 1)[1]
    return core


def _model_of(link_name: str) -> str:
    base = os.path.basename(link_name)
    core = base[len("usb-WD_"):].rsplit("-", 1)[0] if base.startswith("usb-WD_") else base
    core = core.rsplit("_", 1)[0]  # drop serial
    return "WD " + core.replace("_", " ")


def _human(nbytes: int) -> str:
    step = float(nbytes)
    for unit in ("B", "K", "M", "G", "T", "P"):
        if step < 1024 or unit == "P":
            if unit in ("B", "K"):
                return f"{int(step)}{unit}"
            return f"{step:.1f}".rstrip("0").rstrip(".") + unit
        step /= 1024
    return f"{nbytes}"


def _blk_size(name: str) -> str:
    try:
        with open(f"/sys/block/{name}/size") as fh:
            sectors = int(fh.read().strip())
        return _human(sectors * 512)
    except OSError:
        return "?"


def _usb_port(name: str) -> str:
    """Best-effort physical USB port id (e.g. '1-2') from sysfs topology."""
    port = ""
    try:
        target = os.path.realpath(f"/sys/block/{name}")
        for part in target.split("/"):
            if "-" in part and ":" not in part and part[0].isdigit():
                port = part  # last match = closest to the device
    except Exception:
        pass
    return port


def _mountpoint(part: str) -> str:
    if not part:
        return ""
    try:
        out = subprocess.run(["findmnt", "-nro", "TARGET", "--source", part],
                             capture_output=True, text=True, timeout=5)
        s = out.stdout.strip().splitlines()
        return s[0] if s else ""
    except Exception:
        return ""


def list_drives(selector: str = "") -> list:
    """All connected WD My Passport drives as :class:`Drive`, locked first.

    ``selector`` optionally filters by alias / serial substring / /dev path.
    """
    aliases = _read_aliases()
    drives = []
    for link in sorted(glob.glob(f"{BYID}/usb-WD_My_Passport_*")):
        if "-part" in link or not os.path.exists(link):
            continue
        node = os.path.realpath(link)
        name = os.path.basename(node)
        serial = _serial_of(link)
        part = ""
        for cand in (f"{node}1", f"{node}p1"):
            if os.path.exists(cand):
                part = cand
                break
        if not part:
            plink = f"{link}-part1"
            if os.path.exists(plink):
                part = os.path.realpath(plink)
        is_locked = not (part and os.path.exists(part))
        drives.append(Drive(
            node=node, serial=serial, model=_model_of(link),
            size=_blk_size(name), usb_port=_usb_port(name),
            is_locked=is_locked, partition="" if is_locked else part,
            mountpoint=_mountpoint(part) if not is_locked else "",
            alias=aliases.get(serial, ""),
        ))
    if selector:
        sel = selector
        drives = [d for d in drives
                  if sel in (d.alias, d.node) or sel in d.serial
                  or (d.alias and sel.lower() in d.alias.lower())]
    drives.sort(key=lambda d: (not d.is_locked, d.alias or d.serial))
    return drives
