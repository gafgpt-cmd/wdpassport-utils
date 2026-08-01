from dataclasses import dataclass
import os
from typing import Optional, Tuple

from .passwords import BLOCK_SIZE, decode_security_block, make_password_blob, password_length_for_cipher
from .scsi import u16be, u32be


@dataclass(frozen=True)
class EncryptionStatus:
    security_status: int
    current_cipher: int
    password_length: int
    key_reset_enabler: bytes
    supported_ciphers: Tuple[int, ...] = ()


class WdPassportDevice:
    def __init__(self, transport):
        self.transport = transport

    def _read(self, cdb, size=BLOCK_SIZE):
        return self.transport.read(cdb, size)

    def _write(self, cdb, data):
        self.transport.write(cdb, data)

    def encryption_status(self) -> EncryptionStatus:
        data = self._read([0xC0, 0x45, 0, 0, 0, 0, 0, 0, 0x30, 0], BLOCK_SIZE)
        if not data or data[0] != 0x45:
            raise ValueError("invalid encryption status signature")
        count = data[15] if len(data) > 15 else 0
        supported = tuple(data[16 : 16 + count])
        return EncryptionStatus(
            security_status=data[3],
            current_cipher=data[4],
            password_length=int.from_bytes(data[6:8], "big"),
            key_reset_enabler=data[8:12],
            supported_ciphers=supported,
        )

    def read_handy_store(self, page: int) -> bytes:
        cdb = [0xD8, 0x00, *u32be(page), 0x00, 0x00, 0x01, 0x00]
        return self._read(cdb, BLOCK_SIZE)

    def write_handy_store(self, page: int, data: bytes):
        if len(data) != BLOCK_SIZE:
            raise ValueError("handy store blocks must be 512 bytes")
        cdb = [0xDA, 0x00, *u32be(page), 0x00, 0x00, 0x01, 0x00]
        self._write(cdb, data)

    def read_security_block(self):
        return decode_security_block(self.read_handy_store(1))

    def unlock_with_blob(self, password_blob: bytes):
        if len(password_blob) > 32:
            raise ValueError("password blob is too long")
        payload = bytearray([0x45, 0, 0, 0, 0, 0])
        payload.extend(u16be(len(password_blob)))
        payload.extend(password_blob)
        cdb = [0xC1, 0xE1, 0, 0, 0, 0, 0, 0, len(payload), 0]
        self._write(cdb, bytes(payload))

    def unlock(self, password: str):
        status = self.encryption_status()
        block = self.read_security_block()
        blob = make_password_blob(password, status.current_cipher, block.salt, block.iteration_count)
        self.unlock_with_blob(blob)

    def change_passphrase(self, cipher: int, old_blob: Optional[bytes], new_blob: Optional[bytes]):
        password_length = password_length_for_cipher(cipher)
        if old_blob is not None and len(old_blob) != password_length:
            raise ValueError("old password blob has the wrong length")
        if new_blob is not None and len(new_blob) != password_length:
            raise ValueError("new password blob has the wrong length")
        if old_blob is None and new_blob is None:
            raise ValueError("old and new password blobs cannot both be empty")

        flags = 0
        old_payload = old_blob if old_blob is not None else bytes(password_length)
        new_payload = new_blob if new_blob is not None else bytes(password_length)
        if old_blob is None:
            flags |= 0x01
        if new_blob is None:
            flags |= 0x10

        payload = bytearray([0x45, 0, 0, flags, 0, 0])
        payload.extend(u16be(password_length))
        payload.extend(old_payload)
        payload.extend(new_payload)
        cdb = [0xC1, 0xE2, 0, 0, 0, 0, 0, 0, len(payload), 0]
        self._write(cdb, bytes(payload))

    def reset_data_encryption_key(self, cipher: int, key_reset_enabler: bytes,
                                  key_length: Optional[int] = None):
        key_length = key_length if key_length is not None else password_length_for_cipher(cipher)
        if key_length not in (16, 32):
            raise ValueError(f"unsupported key reset length {key_length}")
        cdb = [0xC1, 0xE3, *key_reset_enabler[:4], 0, 0, 8 + key_length, 0]
        payload = bytearray([0x45, 0, 0, 0, cipher, 0])
        payload.extend(u16be(key_length * 8))
        payload.extend(os.urandom(key_length))
        self._write(cdb, bytes(payload))

    def sleep_timer(self) -> int:
        data = self.transport.mode_sense(0x1A)
        return int.from_bytes(data[18:22], "big") // 10

    def set_sleep_timer(self, seconds: int):
        enabled = seconds != 0
        seconds = 0 if seconds == 0 else max(60, min(seconds, 28800))
        data = bytearray(48)
        data[8] = 0x1A
        data[9] = 0x26
        data[11] = 1 if enabled else 0
        data[18:22] = (seconds * 10).to_bytes(4, "big")
        self.transport.mode_select(data)

    def led_brightness(self) -> int:
        data = self.transport.mode_sense(0x21)
        return data[18]

    def set_led_brightness(self, value: int):
        if value < 0 or value > 255:
            raise ValueError("LED brightness must be between 0 and 255")
        data = self.transport.mode_sense(0x21)
        data[0:8] = bytes(8)
        data[8] = 0x21
        data[18] = value
        self.transport.mode_select(data)

    def virtual_cd_enabled(self) -> bool:
        data = self.transport.mode_sense(0x20)
        return (data[12] & 0x02) == 0

    def set_virtual_cd_enabled(self, enabled: bool):
        data = self.transport.mode_sense(0x20)
        data[0:8] = bytes(8)
        data[8] = 0x20
        if enabled:
            data[12] &= ~0x02
        else:
            data[12] |= 0x02
        self.transport.mode_select(data)

    def self_test(self):
        return self.transport.send_diagnostic()
