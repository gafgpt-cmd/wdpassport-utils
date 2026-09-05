"""Filesystem repair for drives that were removed without a clean unmount.

Yanking a WD Passport without unmounting leaves the filesystem flagged dirty.
The kernel then refuses a read-write mount, so udisks either fails outright or
silently falls back to read-only -- which reads to the user as "the drive is
broken". Each filesystem has its own way of clearing that flag; this module
picks the right one and runs it.
"""

import os
import shutil
import subprocess


# fstype (as reported by blkid) -> (tool, argv builder, human description)
_REPAIRS = {
    "ntfs":  ("ntfsfix",    lambda p: ["ntfsfix", "-d", p],
              "clear the NTFS dirty flag and empty the journal"),
    "ntfs3": ("ntfsfix",    lambda p: ["ntfsfix", "-d", p],
              "clear the NTFS dirty flag and empty the journal"),
    "exfat": ("fsck.exfat", lambda p: ["fsck.exfat", "-p", p],
              "repair the exFAT allocation tables"),
    "vfat":  ("fsck.vfat",  lambda p: ["fsck.vfat", "-a", p],
              "repair the FAT tables"),
    "ext2":  ("e2fsck",     lambda p: ["e2fsck", "-p", "-f", p], "replay and check the ext journal"),
    "ext3":  ("e2fsck",     lambda p: ["e2fsck", "-p", "-f", p], "replay and check the ext journal"),
    "ext4":  ("e2fsck",     lambda p: ["e2fsck", "-p", "-f", p], "replay and check the ext journal"),
}

# Packages that provide each repair tool, per distro family.
_PACKAGES = {
    # Arch splits the NTFS utilities out: the ntfs-3g package ships only the
    # mount helpers, and ntfsfix/ntfsinfo live in ntfsprogs.
    "ntfsfix":    {"pacman": "ntfsprogs",  "apt": "ntfs-3g",       "dnf": "ntfsprogs"},
    "ntfsinfo":   {"pacman": "ntfsprogs",  "apt": "ntfs-3g",       "dnf": "ntfsprogs"},
    "fsck.exfat": {"pacman": "exfatprogs", "apt": "exfatprogs",    "dnf": "exfatprogs"},
    "fsck.vfat":  {"pacman": "dosfstools", "apt": "dosfstools",    "dnf": "dosfstools"},
    "e2fsck":     {"pacman": "e2fsprogs",  "apt": "e2fsprogs",     "dnf": "e2fsprogs"},
}

# e2fsck/fsck exit codes are bit flags; 1 and 2 mean "fixed", not "failed".
_FSCK_FIXED_CODES = (0, 1, 2)


def detect_fstype(partition: str) -> str:
    """Return the filesystem type of a partition, or "" if it can't be read."""
    try:
        proc = subprocess.run(
            ["blkid", "-o", "value", "-s", "TYPE", partition],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def is_mounted(partition: str) -> bool:
    """True if the partition currently has a mountpoint."""
    try:
        proc = subprocess.run(
            ["findmnt", "-nro", "TARGET", "--source", partition],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(proc.stdout.strip())


_INSTALL_ARGV = {
    "pacman": ["pacman", "-S", "--needed", "--noconfirm"],
    "apt": ["apt-get", "install", "-y"],
    "dnf": ["dnf", "install", "-y"],
    "zypper": ["zypper", "--non-interactive", "install"],
}


def package_manager() -> str:
    """Name of this system's package manager, or "" if none is recognised."""
    for manager in ("pacman", "apt", "dnf", "zypper"):
        # Debian systems ship apt-get rather than a binary called "apt".
        probe = "apt-get" if manager == "apt" else manager
        if shutil.which(probe):
            return manager
    return ""


def package_for(tool: str) -> str:
    """Package providing a repair tool on this distro, or "" if unknown."""
    return _PACKAGES.get(tool, {}).get(package_manager(), "")


def missing_packages() -> list:
    """Packages needed for repair tools that are not installed yet."""
    wanted = []
    for tool in sorted(_PACKAGES):
        if shutil.which(tool):
            continue
        package = package_for(tool)
        if package and package not in wanted:
            wanted.append(package)
    return wanted


def install_command(packages) -> list:
    """Full privileged argv to install packages, or [] if unsupported."""
    manager = package_manager()
    if not manager or not packages:
        return []
    elevate = ["pkexec"] if not _is_root() else []
    return elevate + _INSTALL_ARGV[manager] + list(packages)


def _is_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


def install_dependencies(packages=None) -> tuple:
    """Install the system packages the repair tools come from.

    Returns (ok, message). Package installation is deliberately kept out of the
    pkexec helper's allowlist -- that boundary exists to run one narrow set of
    disk commands, and letting it install arbitrary packages would widen it far
    beyond its purpose. This elevates separately instead.
    """
    packages = list(packages) if packages else missing_packages()
    if not packages:
        return True, "All filesystem repair tools are already installed."

    argv = install_command(packages)
    if not argv:
        return False, ("No supported package manager found; install these "
                       "manually: %s" % " ".join(packages))
    try:
        proc = subprocess.run(argv, timeout=1800)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, "Could not run the installer: %s" % exc
    if proc.returncode != 0:
        return False, ("Installing %s failed (exit %d). Authorization may have "
                       "been cancelled." % (" ".join(packages), proc.returncode))

    still_missing = missing_packages()
    if still_missing:
        return False, "Still missing after install: %s" % " ".join(still_missing)
    return True, "Installed: %s" % " ".join(packages)


def missing_tool_hint(tool: str) -> str:
    """Explain how to get a missing repair tool, preferring the built-in fix."""
    package = package_for(tool)
    if package:
        return ("%s is not installed (provided by %s).\n"
                "Install it with:  wdpassport install-deps" % (tool, package))
    return "%s is not installed." % tool


def describe(fstype: str) -> str:
    """Human description of what a repair would do, or "" if unsupported."""
    entry = _REPAIRS.get(fstype.lower())
    return entry[2] if entry else ""


def repair_partition(partition: str) -> tuple:
    """Repair a dirty filesystem in place.

    Returns (ok, message). The partition must be unmounted -- repairing a
    mounted filesystem corrupts it, so this refuses rather than risking data.
    """
    if not os.path.exists(partition):
        return False, "No such partition: %s" % partition
    if is_mounted(partition):
        return False, ("%s is mounted; unmount it before repairing "
                       "(repairing a mounted filesystem corrupts it)." % partition)

    fstype = detect_fstype(partition)
    if not fstype:
        return False, ("Could not identify the filesystem on %s. If the drive is "
                       "still locked, unlock it first." % partition)

    entry = _REPAIRS.get(fstype.lower())
    if not entry:
        return False, "No repair tool is known for %s filesystems." % fstype

    tool, build_argv, _ = entry
    if not shutil.which(tool):
        return False, missing_tool_hint(tool)

    try:
        proc = subprocess.run(build_argv(partition), capture_output=True,
                              text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return False, "%s timed out after 10 minutes on %s." % (tool, partition)
    except OSError as exc:
        return False, "Could not run %s: %s" % (tool, exc)

    output = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    if proc.returncode in _FSCK_FIXED_CODES:
        return True, output or "%s reported no remaining errors." % tool
    return False, output or "%s exited with status %d." % (tool, proc.returncode)


# Explicit "this filesystem is dirty" wording, mostly from ntfs-3g and fsck.
_EXPLICIT_DIRTY = (
    "unclean", "dirty", "was not cleanly unmounted", "hibernated",
    "windows is hibernated", "ntfs_attr", "falling back to read-only",
    "unsafe", "metadata kept in windows cache", "run chkdsk",
    "needs checking", "recommended to use chkdsk",
    # ntfsinfo's wording for a set dirty flag, confirmed on a real WD Passport:
    #   "Volume is scheduled for check. Please boot into Windows TWICE, or
    #    use the 'force' option."
    "scheduled for check",
)

# The kernel ntfs3 driver refuses a dirty volume without logging why to
# userspace: udisks only relays mount(8)'s generic failure. Verified against a
# real dirty WD Passport, where the whole message was:
#   "wrong fs type, bad option, bad superblock on /dev/sdb1, missing codepage
#    or helper program, or other error"
# Treating that as a repair candidate is safe because repair_partition() still
# re-checks the filesystem type and only runs a known tool.
_GENERIC_MOUNT_FAILURE = (
    "wrong fs type", "bad superblock", "bad option", "missing codepage",
    "input/output error", "can't read superblock",
)


def looks_dirty(mount_error: str) -> bool:
    """True if a failed mount could plausibly be fixed by a repair.

    Used to decide whether offering a repair is worth the user's attention;
    a wrong password or a non-mountable object should not suggest fsck.
    """
    if not mount_error:
        return False
    text = mount_error.lower()
    if "not a mountable" in text or "wrong password" in text:
        return False
    return any(m in text for m in _EXPLICIT_DIRTY + _GENERIC_MOUNT_FAILURE)


def is_dirty(partition: str) -> bool:
    """Probe the filesystem itself for a dirty flag. Requires root.

    More reliable than reading mount errors, but only usable where we already
    have privileges (the pkexec helper), so callers treat False as "unknown"
    rather than "definitely clean".
    """
    fstype = detect_fstype(partition).lower()
    if fstype in ("ntfs", "ntfs3"):
        # `ntfsfix -n` reports success on a dirty volume (ntfs-3g can still
        # mount it; only the ntfs3 kernel driver refuses), so it is useless as
        # a probe. `ntfsinfo -m` refuses outright and names the reason.
        if not shutil.which("ntfsinfo"):
            return False
        probe = ["ntfsinfo", "-m", partition]
    elif fstype.startswith("ext"):
        if not shutil.which("dumpe2fs"):
            return False
        probe = ["dumpe2fs", "-h", partition]
    else:
        return False

    try:
        proc = subprocess.run(probe, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return False

    text = ((proc.stdout or "") + (proc.stderr or "")).lower()
    if fstype.startswith("ext"):
        # dumpe2fs prints e.g. "Filesystem state:  clean" or "not clean".
        return "filesystem state:" in text and "clean" not in text.split(
            "filesystem state:", 1)[1].splitlines()[0]
    return any(m in text for m in _EXPLICIT_DIRTY)
