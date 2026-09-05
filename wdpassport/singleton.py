"""Single-instance guard.

The GTK control panel gets uniqueness for free from GApplication's
application_id, but the tray applet is a plain GLib main loop with no such
mechanism -- so launching it twice (autostart plus a manual run, say) puts two
icons in the panel, each polling the same drive.

An advisory lock on a file in the runtime directory fixes that. The kernel
drops the lock when the process dies for any reason, so a crash or a SIGKILL
cannot leave a stale lock behind the way a bare PID file would.
"""

import atexit
import errno
import os

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None


_held = []


def runtime_dir() -> str:
    """Per-user directory for lock files, preferring the systemd one."""
    for path in (os.environ.get("XDG_RUNTIME_DIR"),
                 os.environ.get("TMPDIR"),
                 "/tmp"):
        if path and os.path.isdir(path):
            return path
    return "/tmp"


def lock_path(name: str) -> str:
    return os.path.join(runtime_dir(), "%s.lock" % name)


def acquire(name: str):
    """Take the named lock, or return None if another process holds it.

    The returned handle must stay referenced for the lifetime of the process;
    it is also registered with atexit so the file is tidied on a clean exit.
    """
    if fcntl is None:  # pragma: no cover - non-POSIX
        return object()

    path = lock_path(name)
    try:
        # Open read-write WITHOUT truncating: mode "w" would empty the file
        # before we know whether we own the lock, wiping the running
        # instance's PID every time a second copy is launched.
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
        handle = os.fdopen(fd, "r+")
    except OSError:
        # An unwritable runtime dir should not stop the app from starting.
        return object()

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        if exc.errno in (errno.EACCES, errno.EAGAIN):
            return None
        return object()

    # The lock is ours: only now is it safe to replace the file's contents.
    try:
        handle.seek(0)
        handle.truncate()
        handle.write("%d\n" % os.getpid())
        handle.flush()
    except OSError:
        pass

    _held.append(handle)
    atexit.register(_release, handle, path)
    return handle


def _release(handle, path):
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
    except Exception:
        pass
    try:
        os.unlink(path)
    except OSError:
        pass


def running_pid(name: str) -> int:
    """PID recorded in the lock file, or 0 if unknown."""
    try:
        with open(lock_path(name), "r") as fh:
            return int(fh.read().strip() or 0)
    except (OSError, ValueError):
        return 0
