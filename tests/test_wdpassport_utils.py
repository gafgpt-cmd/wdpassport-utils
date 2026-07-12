import importlib.util
import sys
import types
import unittest
from pathlib import Path


def load_module():
    sys.modules.setdefault("pyudev", types.SimpleNamespace(Context=object))
    sys.modules.setdefault(
        "py3_sg",
        types.SimpleNamespace(
            read_as_bin_str=lambda *args, **kwargs: b"",
            write=lambda *args, **kwargs: None,
        ),
    )
    module_path = Path(__file__).resolve().parents[1] / "wdpassport-utils.py"
    spec = importlib.util.spec_from_file_location("wdpassport_utils_script", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    def setUp(self):
        self.module = load_module()

    def test_build_handy_store_block1_sector_returns_512_bytes_with_valid_checksum(self):
        sector = self.module.build_handy_store_block1_sector(
            1000,
            b"ABCDEFGH",
            b"wdpassport-utils",
        )

        self.assertEqual(len(sector), self.module.BLOCK_SIZE)
        self.assertEqual(sector[:4], b"\x00\x01DW")
        self.assertEqual(sector[12:20], b"ABCDEFGH")
        self.assertEqual(self.module.hsb_checksum(sector), sector[511])

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

        matches = self.module.find_passport_devices(context)

        self.assertEqual(matches, [passport_disk])
        self.assertEqual(
            context.last_kwargs,
            {"subsystem": "block", "DEVTYPE": "disk"},
        )

    def test_find_passport_devices_honors_forced_device_path(self):
        parent = FakeDevice("/dev/parent", serial="Western_Digital_My_Passport_1234")
        first = FakeDevice("/dev/sdb", parent=parent)
        second = FakeDevice("/dev/sdc", parent=parent)

        matches = self.module.find_passport_devices(FakeContext([first, second]), "/dev/sdc")

        self.assertEqual(matches, [second])


if __name__ == "__main__":
    unittest.main()
