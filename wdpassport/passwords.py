from dataclasses import dataclass
from hashlib import sha256
import struct

BLOCK_SIZE = 512
SIGNATURE = b"\x00\x01DW"
DEFAULT_ITERATION_COUNT = 1000
DEFAULT_SALT = "WDC.".encode("utf-16-le")
PASSWORD_LENGTH_BY_CIPHER = {
    0x10: 16,
    0x12: 16,
    0x18: 16,
    0x20: 32,
    0x22: 32,
    0x28: 32,
    0x30: 32,
}


@dataclass(frozen=True)
class SecurityBlock:
    iteration_count: int
    salt: bytes
    hint: str


def checksum(data: bytes) -> int:
    total = sum(data[:510]) + data[0]
    return (-total) & 0xFF


def build_security_block_sector(iteration_count: int, salt: bytes, hint: str) -> bytes:
    hint_bytes = hint.encode("utf-16-le")[:404]
    sector = bytearray()
    sector += SIGNATURE
    sector += bytes([0, 0, 0, 0])
    sector += struct.pack("<I", iteration_count)
    sector += salt[:8].ljust(8, b"\x00")
    sector += bytes([0, 0, 0, 0])
    sector += hint_bytes.ljust(404, b"\x00")
    sector += bytes([0] * 83)
    sector += bytes([checksum(sector)])
    if len(sector) != BLOCK_SIZE:
        raise ValueError(f"security block is {len(sector)} bytes, expected {BLOCK_SIZE}")
    return bytes(sector)


def decode_security_block(data: bytes) -> SecurityBlock:
    if len(data) != BLOCK_SIZE:
        raise ValueError("security block must be 512 bytes")
    if data[:4] != SIGNATURE:
        raise ValueError("invalid security block signature")
    if checksum(data) != data[511]:
        raise ValueError("invalid security block checksum")
    iteration_count = struct.unpack_from("<I", data, 8)[0]
    salt = data[12:20]
    hint_raw = data[24:428]
    terminator = hint_raw.find(b"\x00\x00")
    if terminator >= 0:
        terminator += terminator % 2
        hint_raw = hint_raw[:terminator]
    hint = hint_raw.decode("utf-16-le", errors="ignore").strip("\x00").strip()
    return SecurityBlock(iteration_count, salt, hint)


def password_length_for_cipher(cipher: int) -> int:
    try:
        return PASSWORD_LENGTH_BY_CIPHER[cipher]
    except KeyError as exc:
        raise ValueError(f"unsupported cipher {cipher:#x}") from exc


MAX_ITERATION_COUNT = 1_000_000  # WD uses 1000; guard against a corrupt block


def make_password_blob(password: str, cipher: int, salt: bytes, iteration_count: int) -> bytes:
    # iteration_count comes from the drive's security block. A corrupt/garbage
    # value (e.g. 2**32-1) would loop for hours; fail fast instead of hanging.
    if not 0 <= iteration_count <= MAX_ITERATION_COUNT:
        raise ValueError(
            f"implausible iteration count {iteration_count} (corrupt security block?)")
    blob = salt + password.encode("utf-16-le")
    for _ in range(iteration_count):
        blob = sha256(blob).digest()
    return blob[:password_length_for_cipher(cipher)]
