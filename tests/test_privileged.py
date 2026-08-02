import unittest

from wdpassport.privileged import validate_args


class PrivilegedHelperTests(unittest.TestCase):
    def test_rejects_local_file_blob_commands(self):
        with self.assertRaisesRegex(ValueError, "not permitted"):
            validate_args(["blob", "generate", "--output", "/etc/passwd"])

    def test_allows_device_management_command(self):
        args = ["unlock", "--device", "/dev/sdb", "--password-stdin"]
        self.assertEqual(validate_args(args), args)

    def test_rejects_non_device_target(self):
        with self.assertRaisesRegex(ValueError, "/dev"):
            validate_args(["status", "--device", "/tmp/fake"])
