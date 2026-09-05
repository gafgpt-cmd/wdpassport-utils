"""Narrow command boundary for the PolicyKit helper."""

import os
import sys

ALLOWED_COMMANDS = {
    "erase", "health", "identify", "led", "password", "repair",
    "self-test", "sleep", "status", "unlock", "vcd",
}

# Flags that name the block device a command will act on. Any one of these
# satisfies the "must target something under /dev" rule below.
_DEVICE_FLAGS = ("--device", "-d", "--partition", "-p")


def validate_args(args):
    args = list(args)
    if not args or args[0] not in ALLOWED_COMMANDS:
        raise ValueError("this command is not permitted through the privileged helper")
    device = None
    for index, value in enumerate(args):
        matched = [f for f in _DEVICE_FLAGS if value.startswith(f + "=")]
        if matched:
            device = value.split("=", 1)[1]
            break
        if value in _DEVICE_FLAGS:
            if index + 1 >= len(args):
                break
            device = args[index + 1]
            break
    if device is None or not os.path.realpath(device).startswith("/dev/"):
        raise ValueError("privileged commands require a device path under /dev")
    return args


def main(argv=None):
    from .cli import main as cli_main
    try:
        args = validate_args(sys.argv[1:] if argv is None else argv)
    except ValueError as exc:
        print(f"wdpassport privileged helper: {exc}", file=sys.stderr)
        return 2

    # This helper exists to run a narrow set of disk commands as root. Package
    # installation must never ride in on that: `repair` installs missing tools
    # by default, and here that would run the package manager as root on behalf
    # of anyone allowed to call the helper. Force it off -- the unprivileged
    # caller elevates separately for installs (see repair.install_dependencies).
    if args and args[0] == "repair":
        args = [a for a in args if a != "--install-missing"]
        args.append("--no-install-missing")

    return cli_main(args)
