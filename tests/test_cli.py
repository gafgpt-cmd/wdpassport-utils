import unittest
from unittest import mock
from wdpassport.passwords import SecurityBlock

from typer.testing import CliRunner

from wdpassport import cli
from wdpassport.protocol import EncryptionStatus


class FakeDevice:
    def __init__(self):
        self.calls = []
        self._sleep = 0

    def encryption_status(self):
        return EncryptionStatus(
            security_status=0x02,
            current_cipher=0x30,
            password_length=32,
            key_reset_enabler=b"abcd",
            supported_ciphers=(0x30,),
        )

    def read_security_block(self):
        return SecurityBlock(1000, b"ABCDEFGH", "backup")

    def change_passphrase(self, cipher, old, new):
        self.calls.append(("change_passphrase", cipher, old, new))

    def write_handy_store(self, page, data):
        self.calls.append(("write_handy_store", page, data))

    def set_sleep_timer(self, seconds):
        self.calls.append(("set_sleep_timer", seconds))
        self._sleep = seconds

    def sleep_timer(self):
        return self._sleep

    def self_test(self):
        return "ok"


class CliTests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.fake = FakeDevice()

    def invoke(self, args, **kwargs):
        with mock.patch.object(cli, "open_device", return_value=self.fake):
            return self.runner.invoke(cli.app, args, **kwargs)

    def test_status_prints_summary(self):
        result = self.invoke(["status", "--device", "/dev/sdb"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Device: /dev/sdb", result.output)
        self.assertIn("Security status: Unlocked", result.output)
        self.assertIn("Hint: backup", result.output)

    def test_sleep_off_sets_timer_to_zero(self):
        result = self.invoke(["sleep", "off", "--device", "/dev/sdb"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.fake.calls, [("set_sleep_timer", 0)])

    def test_sleep_set_sets_seconds(self):
        result = self.invoke(["sleep", "set", "3600", "--device", "/dev/sdb"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.fake.calls, [("set_sleep_timer", 3600)])

    def test_self_test_prints_result(self):
        result = self.invoke(["self-test", "--device", "/dev/sdb"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Self-test: ok", result.output)

    def test_keep_awake_once_touches_status(self):
        result = self.invoke(["keep-awake", "--device", "/dev/sdb", "--interval", "60", "--once-for-test"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Keep-awake touch complete.", result.output)

    def test_advanced_salt_requires_confirmation_flag(self):
        with mock.patch("getpass.getpass", return_value="secret"):
            result = self.invoke(["blob", "generate", "--salt", "ABCD"])
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("--i-know-what-i-am-doing", result.output)

    def test_password_set_persists_hint(self):
        result = self.invoke(["password", "set", "--device", "/dev/sdb", "--hint", "remember", "--stdin"], input="secret\n")
        self.assertEqual(result.exit_code, 0, result.output)
        write = [call for call in self.fake.calls if call[0] == "write_handy_store"]
        self.assertEqual(len(write), 1)
        from wdpassport.passwords import decode_security_block
        self.assertEqual(decode_security_block(write[0][2]).hint, "remember")

    def test_password_set_initializes_missing_security_block(self):
        self.fake.read_security_block = mock.Mock(side_effect=ValueError("invalid security block signature"))
        self.fake.encryption_status = mock.Mock(return_value=EncryptionStatus(0x00, 0x30, 32, b"abcd", (0x30,)))
        result = self.invoke(["password", "set", "--device", "/dev/sdb", "--hint", "new", "--stdin"], input="secret\n")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertTrue(any(call[0] == "write_handy_store" for call in self.fake.calls))

    def test_password_set_does_not_replace_corrupt_metadata_on_protected_drive(self):
        self.fake.read_security_block = mock.Mock(side_effect=ValueError("invalid security block signature"))
        result = self.invoke(["password", "set", "--device", "/dev/sdb", "--stdin"], input="secret\n")
        self.assertNotEqual(result.exit_code, 0)
        self.assertFalse(any(call[0] == "write_handy_store" for call in self.fake.calls))


if __name__ == "__main__":
    unittest.main()
