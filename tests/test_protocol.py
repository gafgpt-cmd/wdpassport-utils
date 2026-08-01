import unittest

from wdpassport.passwords import build_security_block_sector
from wdpassport.protocol import EncryptionStatus, WdPassportDevice


class FakeTransport:
    def __init__(self):
        self.reads = []
        self.writes = []
        self.mode_sense_pages = {}
        self.mode_selects = []
        self.self_test_result = "ok"

    def read(self, cdb, size):
        self.reads.append((bytes(cdb), size))
        if cdb[0:2] == [0xC0, 0x45]:
            data = bytearray(512)
            data[0] = 0x45
            data[3] = 0x01
            data[4] = 0x30
            data[6:8] = (32).to_bytes(2, "big")
            data[8:12] = (0x01020304).to_bytes(4, "big")
            data[15] = 2
            data[16] = 0x30
            data[17] = 0x28
            return bytes(data)
        if cdb[0] == 0xD8:
            return build_security_block_sector(1000, b"ABCDEFGH", "hint")
        return bytes(size)

    def write(self, cdb, data):
        self.writes.append((bytes(cdb), bytes(data)))

    def mode_sense(self, page_code):
        return bytearray(self.mode_sense_pages.get(page_code, bytes(64)))

    def mode_select(self, data):
        self.mode_selects.append(bytes(data))

    def send_diagnostic(self):
        return self.self_test_result


class ProtocolTests(unittest.TestCase):
    def test_encryption_status_parses_supported_ciphers(self):
        device = WdPassportDevice(FakeTransport())
        status = device.encryption_status()
        self.assertEqual(
            status,
            EncryptionStatus(
                security_status=0x01,
                current_cipher=0x30,
                password_length=32,
                key_reset_enabler=b"\x01\x02\x03\x04",
                supported_ciphers=(0x30, 0x28),
            ),
        )

    def test_read_and_write_handy_store_use_vendor_cdbs(self):
        transport = FakeTransport()
        device = WdPassportDevice(transport)
        device.read_handy_store(1)
        device.write_handy_store(2, bytes([7]) * 512)
        self.assertEqual(transport.reads[-1][0], b"\xD8\x00\x00\x00\x00\x01\x00\x00\x01\x00")
        self.assertEqual(transport.writes[-1][0], b"\xDA\x00\x00\x00\x00\x02\x00\x00\x01\x00")
        self.assertEqual(len(transport.writes[-1][1]), 512)

    def test_unlock_with_blob_writes_unlock_command(self):
        transport = FakeTransport()
        device = WdPassportDevice(transport)
        device.unlock_with_blob(bytes([1]) * 32)
        cdb, payload = transport.writes[-1]
        self.assertEqual(cdb, b"\xC1\xE1\x00\x00\x00\x00\x00\x00\x28\x00")
        self.assertEqual(payload[:8], b"\x45\x00\x00\x00\x00\x00\x00\x20")
        self.assertEqual(payload[8:], bytes([1]) * 32)

    def test_change_passphrase_writes_old_and_new_blobs(self):
        transport = FakeTransport()
        device = WdPassportDevice(transport)
        device.change_passphrase(0x30, bytes([1]) * 32, bytes([2]) * 32)
        cdb, payload = transport.writes[-1]
        self.assertEqual(cdb, b"\xC1\xE2\x00\x00\x00\x00\x00\x00\x48\x00")
        self.assertEqual(payload[:8], b"\x45\x00\x00\x00\x00\x00\x00\x20")
        self.assertEqual(payload[8:40], bytes([1]) * 32)
        self.assertEqual(payload[40:72], bytes([2]) * 32)

    def test_secure_erase_writes_key_reset_command(self):
        transport = FakeTransport()
        device = WdPassportDevice(transport)
        device.reset_data_encryption_key(0x30, b"\x01\x02\x03\x04")
        cdb, payload = transport.writes[-1]
        self.assertEqual(cdb[:6], b"\xC1\xE3\x01\x02\x03\x04")
        self.assertEqual(cdb[8], 40)
        self.assertEqual(payload[:8], b"\x45\x00\x00\x00\x30\x00\x01\x00")
        self.assertEqual(len(payload[8:]), 32)

    def test_sleep_timer_uses_mode_page_1a(self):
        transport = FakeTransport()
        transport.mode_sense_pages[0x1A] = bytes([0] * 18 + list((600).to_bytes(4, "big")) + [0] * 32)
        device = WdPassportDevice(transport)
        self.assertEqual(device.sleep_timer(), 60)
        device.set_sleep_timer(0)
        self.assertEqual(transport.mode_selects[-1][8], 0x1A)

    def test_led_and_virtual_cd_mode_pages_are_updated(self):
        transport = FakeTransport()
        transport.mode_sense_pages[0x21] = bytes([0] * 18 + [99] + [0] * 16)
        transport.mode_sense_pages[0x20] = bytes([0] * 12 + [0] + [0] * 16)
        device = WdPassportDevice(transport)
        self.assertEqual(device.led_brightness(), 99)
        device.set_led_brightness(255)
        self.assertEqual(transport.mode_selects[-1][8], 0x21)
        device.set_virtual_cd_enabled(False)
        self.assertEqual(transport.mode_selects[-1][8], 0x20)

    def test_self_test_delegates_to_transport(self):
        self.assertEqual(WdPassportDevice(FakeTransport()).self_test(), "ok")


if __name__ == "__main__":
    unittest.main()
