"""Resolve commands that cross from the desktop UI into privileged helpers."""

import os
import shutil
import sys


PRIVILEGED_HELPER = "/usr/lib/wdpassport/wd-priv"


def _sibling_of_current_interpreter(name: str) -> str:
    """Look for a console script next to the running interpreter.

    Entry points live in the same bin/ directory as the interpreter that runs
    them, so this finds the right wdpassport/wdpassport-gui when the package is
    installed somewhere off PATH -- a virtualenv, a --user install whose bin dir
    the desktop session never exported, or a checkout run in place. Without it
    the tray raises FileNotFoundError the moment it tries to launch anything.
    """
    candidate = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), name)
    return candidate if os.path.isfile(candidate) and os.access(candidate, os.X_OK) else ""


def find_executable(name: str, env_var: str = "") -> str:
    """Locate one of our console scripts, or "" if it cannot be found.

    Order: explicit env override, then next to the running interpreter, then
    PATH. The env override comes first so packagers and tests can pin an exact
    binary.
    """
    if env_var:
        override = os.environ.get(env_var)
        if override:
            return os.path.realpath(os.path.expanduser(override))
    sibling = _sibling_of_current_interpreter(name)
    if sibling:
        return os.path.realpath(sibling)
    found = shutil.which(name)
    return os.path.realpath(found) if found else ""


def gui_command() -> list:
    """Full argv to launch the GTK control panel.

    Falls back to running the module with the current interpreter, which works
    even when no console script was installed at all.
    """
    executable = find_executable("wdpassport-gui", "WDPASSPORT_GUI")
    if executable:
        return [executable]
    return [sys.executable, "-m", "wdpassport.gui"]


def privileged_command(*args: str) -> list:
    """Build a PolicyKit command using an executable path visible to pkexec."""
    if os.path.exists(PRIVILEGED_HELPER):
        executable = PRIVILEGED_HELPER
    else:
        executable = find_executable("wdpassport", "WDPASSPORT_BIN")
        if not executable:
            raise FileNotFoundError(
                "wdpassport CLI was not found; reinstall with install-linux.sh"
            )
    return ["pkexec", executable, *args]
