import time


def run_keep_awake(device, interval: int, stop_event, once: bool = False, fail_fast: bool = False):
    while not stop_event.is_set():
        try:
            device.encryption_status()
        except Exception:
            if fail_fast:
                raise
        if once:
            return
        stop_event.wait(max(1, interval))
