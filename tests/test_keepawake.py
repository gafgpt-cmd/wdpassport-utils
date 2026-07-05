import threading
import unittest

from wdpassport.keepawake import run_keep_awake


class FakeDevice:
    def __init__(self):
        self.calls = 0

    def encryption_status(self):
        self.calls += 1
        return object()


class KeepAwakeTests(unittest.TestCase):
    def test_run_keep_awake_once_touches_status_once(self):
        device = FakeDevice()
        run_keep_awake(device, interval=60, stop_event=threading.Event(), once=True)
        self.assertEqual(device.calls, 1)

    def test_run_keep_awake_stops_when_event_is_set(self):
        device = FakeDevice()
        stop_event = threading.Event()
        stop_event.set()
        run_keep_awake(device, interval=60, stop_event=stop_event)
        self.assertEqual(device.calls, 0)


if __name__ == "__main__":
    unittest.main()
