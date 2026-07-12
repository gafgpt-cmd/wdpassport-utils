import unittest

from wdpassport.devices import find_passport_devices, is_passport_device


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
        self.last_kwargs = None

    def list_devices(self, **kwargs):
        self.last_kwargs = kwargs
        return list(self.devices)


class DeviceDiscoveryTests(unittest.TestCase):
    def test_is_passport_device_matches_parent_serial(self):
        parent = FakeDevice("/dev/parent", serial="Western_Digital_My_Passport_1234")
        self.assertTrue(is_passport_device(FakeDevice("/dev/sdb", parent=parent)))

    def test_find_passport_devices_matches_wd_passport_parent_serial(self):
        passport_parent = FakeDevice("/dev/parent", serial="Western_Digital_My_Passport_1234")
        passport_disk = FakeDevice("/dev/sdb", parent=passport_parent)
        other_disk = FakeDevice("/dev/sdc", parent=FakeDevice("/dev/other", serial="Other"))
        context = FakeContext([passport_disk, other_disk])

        matches = find_passport_devices(context)

        self.assertEqual(matches, [passport_disk])
        self.assertEqual(context.last_kwargs, {"subsystem": "block", "DEVTYPE": "disk"})

    def test_find_passport_devices_honors_forced_device_path(self):
        parent = FakeDevice("/dev/parent", serial="Western_Digital_My_Passport_1234")
        first = FakeDevice("/dev/sdb", parent=parent)
        second = FakeDevice("/dev/sdc", parent=parent)

        matches = find_passport_devices(FakeContext([first, second]), "/dev/sdc")

        self.assertEqual(matches, [second])


if __name__ == "__main__":
    unittest.main()
