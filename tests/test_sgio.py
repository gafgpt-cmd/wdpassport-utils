import unittest
from unittest import mock

from wdpassport import sgio


class SgioTests(unittest.TestCase):
    def _ioctl(self, *, status=0, driver_status=0, resid=0, sense=b""):
        def fake(_fd, _request, hdr):
            hdr.status = status
            hdr.driver_status = driver_status
            hdr.resid = resid
            hdr.sb_len_wr = len(sense)
            if sense:
                import ctypes
                ctypes.memmove(hdr.sbp, sense, len(sense))
        return fake

    def test_descriptor_sense_failure_is_rejected(self):
        sense = bytes([0x72, 0x05, 0, 0])
        with mock.patch.object(sgio.fcntl, "ioctl", self._ioctl(status=2, sense=sense)):
            with self.assertRaisesRegex(sgio.SgioError, "not supported"):
                sgio.read(0, b"\0", 1)

    def test_non_sense_driver_failure_is_rejected(self):
        with mock.patch.object(sgio.fcntl, "ioctl", self._ioctl(driver_status=6)):
            with self.assertRaises(sgio.SgioError):
                sgio.write(0, b"\0", b"x")

    def test_check_condition_without_sense_is_rejected(self):
        with mock.patch.object(sgio.fcntl, "ioctl", self._ioctl(status=2)):
            with self.assertRaisesRegex(sgio.SgioError, "missing sense"):
                sgio.read(0, b"\0", 1)

    def test_driver_sense_with_malformed_sense_is_rejected(self):
        with mock.patch.object(
            sgio.fcntl,
            "ioctl",
            self._ioctl(driver_status=sgio.DRIVER_SENSE, sense=b"\x72"),
        ):
            with self.assertRaisesRegex(sgio.SgioError, "invalid.*sense"):
                sgio.write(0, b"\0", b"x")

    def test_short_read_returns_only_transferred_bytes(self):
        def fake(_fd, _request, hdr):
            hdr.resid = 3
            import ctypes
            ctypes.memmove(hdr.dxferp, b"AB", 2)
        with mock.patch.object(sgio.fcntl, "ioctl", fake):
            self.assertEqual(sgio.read(0, b"\0", 5), b"AB")

    def test_partial_write_is_rejected(self):
        with mock.patch.object(sgio.fcntl, "ioctl", self._ioctl(resid=1)):
            with self.assertRaisesRegex(sgio.SgioError, "partial"):
                sgio.write(0, b"\0", b"abc")


if __name__ == "__main__":
    unittest.main()
