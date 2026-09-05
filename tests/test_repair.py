import subprocess

import pytest

from wdpassport import repair


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.mark.parametrize("text", [
    # Verified verbatim against a real dirty WD Passport (ntfs3 + udisks2):
    # the kernel logs "volume is dirty" but userspace only sees mount(8)'s
    # generic message, so the heuristic must accept it.
    "Error mounting /dev/sdb1: GDBus.Error:org.freedesktop.UDisks2.Error.Failed: "
    "Error mounting /dev/sdb1 at /run/media/u/PassWXD: wrong fs type, bad option, "
    "bad superblock on /dev/sdb1, missing codepage or helper program, or other error",
    # ntfsinfo's wording when the dirty flag is set.
    "Volume is scheduled for check. Please boot into Windows TWICE.",
    "The disk contains an unclean file system (0, 0).",
    "Windows is hibernated, refused to mount.",
    "Falling back to read-only mount because the NTFS partition is in an unsafe state",
    "Metadata kept in Windows cache, refused to mount.",
    "Volume is scheduled for a check; please run chkdsk",
])
def test_looks_dirty_detects_unclean_shutdown(text):
    assert repair.looks_dirty(text)


@pytest.mark.parametrize("text", [
    "",
    "Error unlocking device: wrong password",
    "Object /org/freedesktop/UDisks2/block_devices/sdb1 is not a mountable filesystem",
])
def test_looks_dirty_ignores_unrelated_failures(text):
    assert not repair.looks_dirty(text)


def test_describe_known_and_unknown():
    assert "NTFS" in repair.describe("ntfs")
    assert repair.describe("btrfs") == ""


def test_detect_fstype_reads_blkid(monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: _Proc(0, stdout="ntfs\n"))
    assert repair.detect_fstype("/dev/sdb1") == "ntfs"


def test_detect_fstype_empty_when_blkid_fails(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(2))
    assert repair.detect_fstype("/dev/sdb1") == ""


def test_repair_refuses_missing_partition():
    ok, message = repair.repair_partition("/dev/definitely-not-here")
    assert not ok
    assert "No such partition" in message


def test_repair_refuses_mounted_partition(monkeypatch):
    monkeypatch.setattr(repair.os.path, "exists", lambda p: True)
    monkeypatch.setattr(repair, "is_mounted", lambda p: True)
    ok, message = repair.repair_partition("/dev/sdb1")
    assert not ok
    assert "mounted" in message
    assert "corrupts it" in message


def test_repair_rejects_unknown_filesystem(monkeypatch):
    monkeypatch.setattr(repair.os.path, "exists", lambda p: True)
    monkeypatch.setattr(repair, "is_mounted", lambda p: False)
    monkeypatch.setattr(repair, "detect_fstype", lambda p: "zfs")
    ok, message = repair.repair_partition("/dev/sdb1")
    assert not ok
    assert "No repair tool" in message


def test_missing_ntfs_tool_names_the_arch_package(monkeypatch):
    """On Arch ntfsfix ships in ntfsprogs, not ntfs-3g."""
    monkeypatch.setattr(repair.shutil, "which",
                        lambda name: "/usr/bin/pacman" if name == "pacman" else None)
    assert "ntfsprogs" in repair.missing_tool_hint("ntfsfix")


def test_is_dirty_uses_ntfsinfo_not_ntfsfix(monkeypatch):
    """ntfsfix -n reports success on a dirty volume, so it must not be used."""
    seen = {}
    monkeypatch.setattr(repair, "detect_fstype", lambda p: "ntfs")
    monkeypatch.setattr(repair.shutil, "which", lambda name: "/usr/bin/" + name)

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return _Proc(1, stdout="Volume is scheduled for check.")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert repair.is_dirty("/dev/sdb1")
    assert seen["argv"][0] == "ntfsinfo"


def test_is_dirty_false_for_clean_ext(monkeypatch):
    monkeypatch.setattr(repair, "detect_fstype", lambda p: "ext4")
    monkeypatch.setattr(repair.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: _Proc(0, stdout="Filesystem state:  clean\n"))
    assert not repair.is_dirty("/dev/sdb1")


def test_repair_reports_missing_tool(monkeypatch):
    monkeypatch.setattr(repair.os.path, "exists", lambda p: True)
    monkeypatch.setattr(repair, "is_mounted", lambda p: False)
    monkeypatch.setattr(repair, "detect_fstype", lambda p: "ntfs")
    monkeypatch.setattr(repair.shutil, "which",
                        lambda name: "/usr/bin/pacman" if name == "pacman" else None)
    ok, message = repair.repair_partition("/dev/sdb1")
    assert not ok
    # Names the package that actually provides ntfsfix on this distro, and
    # points at the command that installs it.
    assert "ntfsprogs" in message
    assert "install-deps" in message


def test_repair_runs_ntfsfix_and_succeeds(monkeypatch):
    seen = {}
    monkeypatch.setattr(repair.os.path, "exists", lambda p: True)
    monkeypatch.setattr(repair, "is_mounted", lambda p: False)
    monkeypatch.setattr(repair, "detect_fstype", lambda p: "ntfs")
    monkeypatch.setattr(repair.shutil, "which", lambda name: "/usr/bin/" + name)

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return _Proc(0, stdout="NTFS volume version is 3.1.\nNTFS partition was processed successfully.")

    monkeypatch.setattr(subprocess, "run", fake_run)
    ok, message = repair.repair_partition("/dev/sdb1")
    assert ok
    assert seen["argv"] == ["ntfsfix", "-d", "/dev/sdb1"]
    assert "successfully" in message


@pytest.mark.parametrize("code", [0, 1, 2])
def test_fsck_partial_fix_codes_count_as_success(monkeypatch, code):
    """e2fsck/fsck exit 1 and 2 mean 'errors corrected', not failure."""
    monkeypatch.setattr(repair.os.path, "exists", lambda p: True)
    monkeypatch.setattr(repair, "is_mounted", lambda p: False)
    monkeypatch.setattr(repair, "detect_fstype", lambda p: "ext4")
    monkeypatch.setattr(repair.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: _Proc(code, stdout="corrected"))
    ok, _ = repair.repair_partition("/dev/sdb1")
    assert ok


def test_fsck_hard_failure_is_reported(monkeypatch):
    monkeypatch.setattr(repair.os.path, "exists", lambda p: True)
    monkeypatch.setattr(repair, "is_mounted", lambda p: False)
    monkeypatch.setattr(repair, "detect_fstype", lambda p: "ext4")
    monkeypatch.setattr(repair.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: _Proc(8, stderr="operational error"))
    ok, message = repair.repair_partition("/dev/sdb1")
    assert not ok
    assert "operational error" in message


def test_repair_is_allowed_through_privileged_helper():
    from wdpassport.privileged import validate_args
    assert validate_args(["repair", "--partition", "/dev/sdb1"])
    assert validate_args(["repair", "--partition=/dev/sdb1"])


def test_privileged_helper_still_requires_a_dev_path():
    from wdpassport.privileged import validate_args
    with pytest.raises(ValueError):
        validate_args(["repair", "--partition", "/etc/passwd"])
    with pytest.raises(ValueError):
        validate_args(["repair"])


# --- dependency installation ------------------------------------------------

def test_package_for_ntfsfix_is_distro_specific(monkeypatch):
    monkeypatch.setattr(repair, "package_manager", lambda: "pacman")
    assert repair.package_for("ntfsfix") == "ntfsprogs"
    monkeypatch.setattr(repair, "package_manager", lambda: "apt")
    assert repair.package_for("ntfsfix") == "ntfs-3g"


def test_missing_packages_lists_only_absent_tools(monkeypatch):
    monkeypatch.setattr(repair, "package_manager", lambda: "pacman")
    # Only ntfsfix/ntfsinfo are absent; the rest resolve.
    monkeypatch.setattr(repair.shutil, "which",
                        lambda n: None if n.startswith("ntfs") else "/usr/bin/" + n)
    assert repair.missing_packages() == ["ntfsprogs"]


def test_missing_packages_empty_when_all_present(monkeypatch):
    monkeypatch.setattr(repair, "package_manager", lambda: "pacman")
    monkeypatch.setattr(repair.shutil, "which", lambda n: "/usr/bin/" + n)
    assert repair.missing_packages() == []


def test_install_command_elevates_when_not_root(monkeypatch):
    monkeypatch.setattr(repair, "package_manager", lambda: "pacman")
    monkeypatch.setattr(repair, "_is_root", lambda: False)
    argv = repair.install_command(["ntfsprogs"])
    assert argv[0] == "pkexec"
    assert "ntfsprogs" in argv


def test_install_command_skips_pkexec_as_root(monkeypatch):
    monkeypatch.setattr(repair, "package_manager", lambda: "pacman")
    monkeypatch.setattr(repair, "_is_root", lambda: True)
    argv = repair.install_command(["ntfsprogs"])
    assert argv[0] == "pacman"


def test_install_command_empty_without_package_manager(monkeypatch):
    monkeypatch.setattr(repair, "package_manager", lambda: "")
    assert repair.install_command(["ntfsprogs"]) == []


def test_install_dependencies_noop_when_nothing_missing(monkeypatch):
    monkeypatch.setattr(repair, "missing_packages", lambda: [])
    ok, message = repair.install_dependencies()
    assert ok
    assert "already installed" in message


def test_install_dependencies_reports_cancelled_authorization(monkeypatch):
    monkeypatch.setattr(repair, "missing_packages", lambda: ["ntfsprogs"])
    monkeypatch.setattr(repair, "install_command", lambda p: ["pkexec", "pacman"])
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc(126))
    ok, message = repair.install_dependencies()
    assert not ok
    assert "Authorization" in message


def test_install_dependencies_without_package_manager(monkeypatch):
    monkeypatch.setattr(repair, "missing_packages", lambda: ["ntfsprogs"])
    monkeypatch.setattr(repair, "install_command", lambda p: [])
    ok, message = repair.install_dependencies()
    assert not ok
    assert "manually" in message


def test_privileged_helper_never_installs_packages(monkeypatch):
    """The pkexec helper must not let `repair` run the package manager as root."""
    from wdpassport import privileged
    seen = {}
    monkeypatch.setattr("wdpassport.cli.main", lambda args: seen.setdefault("args", args) or 0)
    privileged.main(["repair", "--partition", "/dev/sdb1", "--install-missing"])
    assert "--no-install-missing" in seen["args"]
    assert "--install-missing" not in seen["args"]


def test_privileged_helper_forces_flag_even_when_absent(monkeypatch):
    from wdpassport import privileged
    seen = {}
    monkeypatch.setattr("wdpassport.cli.main", lambda args: seen.setdefault("args", args) or 0)
    privileged.main(["repair", "--partition", "/dev/sdb1"])
    assert "--no-install-missing" in seen["args"]
