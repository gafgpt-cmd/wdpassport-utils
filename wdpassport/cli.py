from pathlib import Path
import sys
from typing import Optional

import typer

from .actions import status_summary
from .keepawake import run_keep_awake
from .passwords import DEFAULT_ITERATION_COUNT, DEFAULT_SALT, make_password_blob
from .protocol import WdPassportDevice
from .scsi import ScsiDevice

app = typer.Typer(no_args_is_help=True)
password_app = typer.Typer(help="Set, change, or remove the drive password.")
sleep_app = typer.Typer(help="Read or change drive standby behavior.")
vcd_app = typer.Typer(help="Read or change WD virtual CD state.")
led_app = typer.Typer(help="Read or change LED brightness.")
blob_app = typer.Typer(help="Advanced password blob operations.")

app.add_typer(password_app, name="password")
app.add_typer(sleep_app, name="sleep")
app.add_typer(vcd_app, name="vcd")
app.add_typer(led_app, name="led")
app.add_typer(blob_app, name="blob")


def open_device(device_path: str) -> WdPassportDevice:
    fileobj = open(device_path, "r+b")
    return WdPassportDevice(ScsiDevice(fileobj))


def _device_option():
    return typer.Option(..., "--device", "-d", help="Block device path, for example /dev/sdb.")


def _print_summary(summary: dict):
    typer.echo(f"Device: {summary['device']}")
    typer.echo(f"Security status: {summary['security_status']}")
    typer.echo(f"Encryption type: {summary['cipher']}")
    typer.echo(f"Password blob length: {summary['password_length']}")
    if summary["supported_ciphers"]:
        typer.echo("Supported ciphers: " + ", ".join(summary["supported_ciphers"]))
    if summary["hint"]:
        typer.echo(f"Hint: {summary['hint']}")


def _require_advanced(allowed: bool):
    if not allowed:
        raise typer.BadParameter("This option requires --i-know-what-i-am-doing.")


@app.command()
def status(device: str = _device_option()):
    """Show drive status."""
    _print_summary(status_summary(open_device(device), device))


@app.command("list")
def list_drives_cmd():
    """List connected WD My Passport drives with identifying details."""
    from .devices import list_drives

    drives = list_drives()
    if not drives:
        typer.echo("No WD My Passport drive found.")
        raise typer.Exit(1)
    for d in drives:
        typer.echo(d.label())
        typer.echo(f"    node={d.node}  serial={d.serial}  mount={d.mountpoint or '-'}")


def _activity_blink(device: str, count: int, interval: float) -> None:
    """Generate read bursts so the drive's activity LED flickers.

    Works on models with no software-controllable LED. Read-only and safe on a
    mounted drive.
    """
    import os
    import time

    fd = os.open(device, os.O_RDONLY)
    try:
        try:
            total = os.lseek(fd, 0, os.SEEK_END)
        except OSError:
            total = 0
        chunk = 8 * 1024 * 1024
        span = max(total - chunk, 1)
        for i in range(count):
            os.lseek(fd, (i * 64 * 1024 * 1024) % span, os.SEEK_SET)
            os.read(fd, chunk)
            time.sleep(interval)
    finally:
        os.close(fd)


@app.command()
def identify(
    device: str = _device_option(),
    count: int = typer.Option(6, "--count", min=1, help="Number of blink cycles."),
    interval: float = typer.Option(0.4, "--interval", min=0.05, help="Seconds per half-cycle."),
):
    """Find the physical drive: blink its LED, or flicker its activity LED.

    Tries the WD LED-brightness command first; on models that don't support it
    (ILLEGAL REQUEST), falls back to read-activity so the activity LED blinks.
    """
    import time

    drive = open_device(device)
    original = None
    try:
        original = drive.led_brightness()
        for _ in range(count):
            drive.set_led_brightness(0)
            time.sleep(interval)
            drive.set_led_brightness(255)
            time.sleep(interval)
        if original is not None:
            drive.set_led_brightness(original)
        typer.echo("Identify: LED blink complete.")
        return
    except Exception:
        # LED not controllable on this model; fall back to activity flicker.
        if original is not None:
            try:
                drive.set_led_brightness(original)
            except Exception:
                pass

    _activity_blink(device, count, interval)
    typer.echo("Identify: no controllable LED on this model; used disk-activity flicker.")


@app.command()
def unlock(
    device: str = _device_option(),
    password_stdin: bool = typer.Option(
        False,
        "--password-stdin",
        help="Read the password from the first line of standard input instead of prompting. For GUI/pkexec use.",
    ),
):
    """Unlock the drive using a prompted password."""
    if password_stdin:
        password = sys.stdin.readline().rstrip("\n")
        if not password:
            raise typer.BadParameter("No password received on standard input.")
    else:
        import getpass

        password = getpass.getpass(f"[wdpassport] password for {device}: ")
    open_device(device).unlock(password)
    typer.echo("Device unlocked.")


def _read_stdin_lines(n: int) -> list:
    lines = [sys.stdin.readline().rstrip("\n") for _ in range(n)]
    if any(v == "" for v in lines):
        raise typer.BadParameter("Missing value(s) on standard input.")
    return lines


@password_app.command("set")
def password_set(
    device: str = _device_option(),
    hint: str = typer.Option("", "--hint"),
    stdin: bool = typer.Option(False, "--stdin", help="Read the new password from stdin (GUI/pkexec)."),
):
    """Set a password on a currently unlocked or unprotected drive."""
    if stdin:
        password = _read_stdin_lines(1)[0]
    else:
        import getpass

        password = getpass.getpass("New password: ")
        confirm = getpass.getpass("New password (again): ")
        if password != confirm:
            raise typer.BadParameter("Password confirmation did not match.")
    drive = open_device(device)
    status_value = drive.encryption_status()
    block = drive.read_security_block()
    blob = make_password_blob(password, status_value.current_cipher, block.salt, block.iteration_count)
    drive.change_passphrase(status_value.current_cipher, None, blob)
    typer.echo("Password set.")


@password_app.command("change")
def password_change(
    device: str = _device_option(),
    hint: str = typer.Option("", "--hint"),
    stdin: bool = typer.Option(False, "--stdin", help="Read current then new password from stdin (GUI/pkexec)."),
):
    """Change the current password."""
    if stdin:
        current, new = _read_stdin_lines(2)
    else:
        import getpass

        current = getpass.getpass("Current password: ")
        new = getpass.getpass("New password: ")
        confirm = getpass.getpass("New password (again): ")
        if new != confirm:
            raise typer.BadParameter("Password confirmation did not match.")
    drive = open_device(device)
    status_value = drive.encryption_status()
    block = drive.read_security_block()
    old_blob = make_password_blob(current, status_value.current_cipher, block.salt, block.iteration_count)
    new_blob = make_password_blob(new, status_value.current_cipher, block.salt, block.iteration_count)
    drive.change_passphrase(status_value.current_cipher, old_blob, new_blob)
    typer.echo("Password changed.")


@password_app.command("remove")
def password_remove(
    device: str = _device_option(),
    stdin: bool = typer.Option(False, "--stdin", help="Read current password from stdin (GUI/pkexec)."),
):
    """Remove password protection from an unlocked drive."""
    if stdin:
        current = _read_stdin_lines(1)[0]
    else:
        import getpass

        current = getpass.getpass("Current password: ")
    drive = open_device(device)
    status_value = drive.encryption_status()
    block = drive.read_security_block()
    old_blob = make_password_blob(current, status_value.current_cipher, block.salt, block.iteration_count)
    drive.change_passphrase(status_value.current_cipher, old_blob, None)
    typer.echo("Password removed.")


@app.command()
def erase(
    device: str = _device_option(),
    cipher: Optional[int] = typer.Option(None, "--cipher", help="Advanced cipher id, for example 0x30."),
    i_know_what_i_am_doing: bool = typer.Option(False, "--i-know-what-i-am-doing"),
    force: bool = typer.Option(False, "--force", help="Skip the typed confirmation (caller already confirmed, e.g. GUI)."),
):
    """Reset the data encryption key. This makes existing data unrecoverable."""
    if cipher is not None:
        _require_advanced(i_know_what_i_am_doing)
    if not force:
        confirmation = typer.prompt(f"Type {device} to erase all data")
        if confirmation != device:
            raise typer.Abort()
    drive = open_device(device)
    status_value = drive.encryption_status()
    drive.reset_data_encryption_key(cipher or status_value.current_cipher, status_value.key_reset_enabler)
    typer.echo("Device erased.")


@sleep_app.command("status")
def sleep_status(device: str = _device_option()):
    """Show the current standby timer in seconds."""
    typer.echo(f"Sleep timer: {open_device(device).sleep_timer()} seconds")


@sleep_app.command("set")
def sleep_set(seconds: int, device: str = _device_option()):
    """Set the standby timer in seconds."""
    open_device(device).set_sleep_timer(seconds)
    typer.echo(f"Sleep timer set to {seconds} seconds.")


@sleep_app.command("off")
def sleep_off(device: str = _device_option()):
    """Disable the drive standby timer."""
    open_device(device).set_sleep_timer(0)
    typer.echo("Sleep timer disabled.")


@vcd_app.command("status")
def vcd_status(device: str = _device_option()):
    """Show WD virtual CD state."""
    typer.echo(f"Virtual CD: {'on' if open_device(device).virtual_cd_enabled() else 'off'}")


@vcd_app.command("on")
def vcd_on(device: str = _device_option()):
    """Enable WD virtual CD."""
    open_device(device).set_virtual_cd_enabled(True)
    typer.echo("Virtual CD enabled.")


@vcd_app.command("off")
def vcd_off(device: str = _device_option()):
    """Disable WD virtual CD."""
    open_device(device).set_virtual_cd_enabled(False)
    typer.echo("Virtual CD disabled.")


@led_app.command("status")
def led_status(device: str = _device_option()):
    """Show LED brightness."""
    typer.echo(f"LED brightness: {open_device(device).led_brightness()}")


@led_app.command("set")
def led_set(value: int, device: str = _device_option()):
    """Set LED brightness from 0 to 255."""
    open_device(device).set_led_brightness(value)
    typer.echo(f"LED brightness set to {value}.")


@led_app.command("on")
def led_on(device: str = _device_option()):
    """Turn LED on."""
    open_device(device).set_led_brightness(255)
    typer.echo("LED enabled.")


@led_app.command("off")
def led_off(device: str = _device_option()):
    """Turn LED off."""
    open_device(device).set_led_brightness(0)
    typer.echo("LED disabled.")


@app.command("self-test")
def self_test(device: str = _device_option()):
    """Run a minimal device diagnostic."""
    typer.echo(f"Self-test: {open_device(device).self_test()}")


@app.command("keep-awake")
def keep_awake(
    device: str = _device_option(),
    interval: int = typer.Option(60, "--interval", min=1, help="Seconds between harmless status touches."),
    once_for_test: bool = typer.Option(False, "--once-for-test", help="Run one touch and exit."),
):
    """Prevent standby during long copies by periodically touching drive status."""
    import threading

    run_keep_awake(open_device(device), interval=interval, stop_event=threading.Event(), once=once_for_test)
    if once_for_test:
        typer.echo("Keep-awake touch complete.")


@blob_app.command("generate")
def blob_generate(
    cipher: int = typer.Option(0x30, "--cipher"),
    salt: Optional[str] = typer.Option(None, "--salt"),
    iteration_count: int = typer.Option(DEFAULT_ITERATION_COUNT, "--iteration-count"),
    output: Optional[Path] = typer.Option(None, "--output"),
    i_know_what_i_am_doing: bool = typer.Option(False, "--i-know-what-i-am-doing"),
):
    """Generate password blob unlock material."""
    import getpass

    password = getpass.getpass("Password for blob: ")
    if salt is not None:
        _require_advanced(i_know_what_i_am_doing)
        salt_bytes = salt.encode("utf-16-le")[:8].ljust(8, b"\x00")
    else:
        salt_bytes = DEFAULT_SALT
    blob = make_password_blob(password, cipher, salt_bytes, iteration_count)
    if output:
        output.write_bytes(blob)
        typer.echo(f"Wrote password blob to {output}. Treat this file like a password.")
    else:
        sys.stdout.buffer.write(blob)


@blob_app.command("unlock")
def blob_unlock(path: Path, device: str = _device_option()):
    """Unlock using a password blob file."""
    open_device(device).unlock_with_blob(path.read_bytes())
    typer.echo("Device unlocked.")


def main(argv=None) -> int:
    try:
        app(args=argv, prog_name="wdpassport", standalone_mode=False)
    except typer.Exit as exc:
        return int(exc.exit_code or 0)
    return 0
