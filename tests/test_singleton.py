import os
import subprocess
import sys

from wdpassport import singleton


def test_acquire_then_second_attempt_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    first = singleton.acquire("unit-test-app")
    assert first is not None
    # Same process re-locking would succeed (flock is per-fd/per-process), so
    # a real second holder has to come from another process.
    code = (
        "import os,sys;sys.path.insert(0,%r);"
        "os.environ['XDG_RUNTIME_DIR']=%r;"
        "from wdpassport import singleton;"
        "print('LOCKED' if singleton.acquire('unit-test-app') is None else 'FREE')"
        % (os.getcwd(), str(tmp_path))
    )
    out = subprocess.run([sys.executable, "-c", code],
                         capture_output=True, text=True, timeout=60)
    assert "LOCKED" in out.stdout


def test_pid_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    singleton.acquire("pid-test-app")
    assert singleton.running_pid("pid-test-app") == os.getpid()


def test_failed_acquire_does_not_truncate_the_pid(tmp_path, monkeypatch):
    """A refused second launch must not wipe the running instance's PID."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    path = singleton.lock_path("truncate-test")
    with open(path, "w") as fh:
        fh.write("4242\n")

    code = (
        "import os,sys;sys.path.insert(0,%r);"
        "os.environ['XDG_RUNTIME_DIR']=%r;"
        "from wdpassport import singleton;"
        "h=singleton.acquire('truncate-test');"
        "import time;time.sleep(3)"
        % (os.getcwd(), str(tmp_path))
    )
    holder = subprocess.Popen([sys.executable, "-c", code])
    try:
        import time
        time.sleep(1.5)
        # Another process tries and is refused; the PID must survive.
        assert singleton.acquire("truncate-test") is None
        assert singleton.running_pid("truncate-test") != 0
    finally:
        holder.kill()
        holder.wait(timeout=10)


def test_lock_released_when_holder_dies(tmp_path, monkeypatch):
    """The kernel drops flock on process death, so no stale lock survives."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    code = (
        "import os,sys,time;sys.path.insert(0,%r);"
        "os.environ['XDG_RUNTIME_DIR']=%r;"
        "from wdpassport import singleton;"
        "singleton.acquire('death-test');time.sleep(30)"
        % (os.getcwd(), str(tmp_path))
    )
    holder = subprocess.Popen([sys.executable, "-c", code])
    import time
    time.sleep(1.5)
    assert singleton.acquire("death-test") is None
    holder.kill()
    holder.wait(timeout=10)
    time.sleep(0.5)
    assert singleton.acquire("death-test") is not None


def test_unwritable_runtime_dir_does_not_block_startup(monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/proc/nonexistent-dir")
    monkeypatch.setattr(singleton, "runtime_dir", lambda: "/proc/nonexistent-dir")
    assert singleton.acquire("nowhere") is not None


def test_running_pid_zero_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert singleton.running_pid("never-created") == 0
