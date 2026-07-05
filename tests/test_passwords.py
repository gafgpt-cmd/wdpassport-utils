import unittest

from wdpassport.passwords import (
    BLOCK_SIZE,
    build_security_block_sector,
    checksum,
    decode_security_block,
    make_password_blob,
)


class PasswordTests(unittest.TestCase):
    def test_build_security_block_sector_returns_512_bytes_with_valid_checksum(self):
        sector = build_security_block_sector(1000, b"ABCDEFGH", "wdpassport-utils")
        self.assertEqual(len(sector), BLOCK_SIZE)
        self.assertEqual(sector[:4], b"\x00\x01DW")
        self.assertEqual(sector[12:20], b"ABCDEFGH")
        self.assertEqual(checksum(sector), sector[511])

    def test_decode_security_block_round_trips_hint(self):
        sector = build_security_block_sector(1000, b"ABCDEFGH", "copy-drive")
        block = decode_security_block(sector)
        self.assertEqual(block.iteration_count, 1000)
        self.assertEqual(block.salt, b"ABCDEFGH")
        self.assertEqual(block.hint, "copy-drive")

    def test_make_password_blob_truncates_to_cipher_password_length(self):
        blob = make_password_blob("secret", 0x30, b"ABCDEFGH", 1000)
        self.assertEqual(len(blob), 32)


if __name__ == "__main__":
    unittest.main()
