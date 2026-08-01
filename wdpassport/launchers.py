"""Resolve commands that cross from the desktop UI into privileged helpers."""

import os
import shutil


PRIVILEGED_HELPER = "/usr/lib/wdpassport/wd-priv"


def privileged_command(*args: str) -> list:
    """Build a PolicyKit command using an executable path visible to pkexec."""
    if os.path.exists(PRIVILEGED_HELPER):
        executable = PRIVILEGED_HELPER
    else:
        executable = os.environ.get("WDPASSPORT_BIN") or shutil.which("wdpassport")
        if not executable:
            raise FileNotFoundError(
                "wdpassport CLI was not found; reinstall with install-linux.sh"
            )
        executable = os.path.realpath(os.path.expanduser(executable))
    return ["pkexec", executable, *args]
