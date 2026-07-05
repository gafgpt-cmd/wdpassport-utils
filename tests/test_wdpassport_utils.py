import unittest

from wdpassport.devices import find_passport_devices
from wdpassport.passwords import BLOCK_SIZE, build_security_block_sector, checksum


class FakeDevice:
    def __init__(self, node, serial=None, parent=None):
        self.device_node = node
        self.parent = parent
        self.properties = {}
        if serial is not None:
            self.properties["ID_SERIAL"] = serial

    def __contains__(self, key):
        return key in self.properties


class FakeContext:
    def __init__(self, devices):
        self.devices = devices

    def list_devices(self, **kwargs):
        self.last_kwargs = kwargs
        return list(self.devices)


class UtilityTests(unittest.TestCase):
    def test_build_handy_store_block1_sector_returns_512_bytes_with_valid_checksum(self):
        sector = build_security_block_sector(
            1000,
            b"ABCDEFGH",
            "wdpassport-utils",
        )

        self.assertEqual(len(sector), BLOCK_SIZE)
        self.assertEqual(sector[:4], b"\x00\x01DW")
        self.assertEqual(sector[12:20], b"ABCDEFGH")
        self.assertEqual(checksum(sector), sector[511])

    def test_find_passport_devices_matches_wd_passport_parent_serial(self):
        passport_parent = FakeDevice(
            "/dev/parent",
            serial="Western_Digital_My_Passport_1234",
        )
        passport_disk = FakeDevice("/dev/sdb", parent=passport_parent)
        other_disk = FakeDevice(
            "/dev/sdc",
            parent=FakeDevice("/dev/other-parent", serial="Other_Drive_1234"),
        )
        context = FakeContext([passport_disk, other_disk])

        matches = find_passport_devices(context)

        self.assertEqual(matches, [passport_disk])
        self.assertEqual(
            context.last_kwargs,
            {"subsystem": "block", "DEVTYPE": "disk"},
        )

    def test_find_passport_devices_honors_forced_device_path(self):
        parent = FakeDevice("/dev/parent", serial="Western_Digital_My_Passport_1234")
        first = FakeDevice("/dev/sdb", parent=parent)
        second = FakeDevice("/dev/sdc", parent=parent)

        matches = find_passport_devices(FakeContext([first, second]), "/dev/sdc")

        self.assertEqual(matches, [second])


if __name__ == "__main__":
    unittest.main()
