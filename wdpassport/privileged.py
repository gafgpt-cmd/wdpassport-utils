"""Narrow command boundary for the PolicyKit helper."""

import os
import sys

ALLOWED_COMMANDS = {
    "erase", "health", "identify", "led", "password",
    "self-test", "sleep", "status", "unlock", "vcd",
}


def validate_args(args):
    args = list(args)
    if not args or args[0] not in ALLOWED_COMMANDS:
        raise ValueError("this command is not permitted through the privileged helper")
    device = None
    for index, value in enumerate(args):
        if value.startswith("--device="):
            device = value.split("=", 1)[1]
            break
        if value in ("--device", "-d"):
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
    return cli_main(args)
