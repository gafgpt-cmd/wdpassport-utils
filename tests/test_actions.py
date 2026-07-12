import unittest

from wdpassport.actions import DeviceSelectionError, choose_single_device, status_summary
from wdpassport.protocol import EncryptionStatus


class FakeProtocolDevice:
    def encryption_status(self):
        return EncryptionStatus(
            security_status=0x02,
            current_cipher=0x30,
            password_length=32,
            key_reset_enabler=b"abcd",
            supported_ciphers=(0x30, 0x28),
        )

    def read_security_block(self):
        return type("Block", (), {"hint": "backup"})()


class ActionTests(unittest.TestCase):
    def test_choose_single_device_returns_only_device(self):
        self.assertEqual(choose_single_device(["/dev/sdb"]), "/dev/sdb")

    def test_choose_single_device_rejects_empty_and_ambiguous_lists(self):
        with self.assertRaises(DeviceSelectionError):
            choose_single_device([])
        with self.assertRaises(DeviceSelectionError):
            choose_single_device(["/dev/sdb", "/dev/sdc"])

    def test_status_summary_returns_labels_and_hint(self):
        summary = status_summary(FakeProtocolDevice(), "/dev/sdb")
        self.assertEqual(summary["device"], "/dev/sdb")
        self.assertEqual(summary["security_status"], "Unlocked")
        self.assertEqual(summary["cipher"], "Full Disk Encryption")
        self.assertEqual(summary["supported_ciphers"], ["Full Disk Encryption", "AES_256_XTS"])
        self.assertEqual(summary["hint"], "backup")


if __name__ == "__main__":
    unittest.main()
