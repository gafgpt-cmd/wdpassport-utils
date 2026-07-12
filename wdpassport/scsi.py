import struct

BLOCK_SIZE = 512


def pack_cdb(cdb):
    return struct.pack(f"{len(cdb)}B", *cdb)


def u32be(value: int) -> bytes:
    return struct.pack("!I", value)


def u16be(value: int) -> bytes:
    return struct.pack("!H", value)


class ScsiDevice:
    def __init__(self, fileobj):
        self.fileobj = fileobj

    def read(self, cdb, size):
        from . import sgio

        return sgio.read(self.fileobj, pack_cdb(cdb), size)

    def write(self, cdb, data):
        from . import sgio

        sgio.write(self.fileobj, pack_cdb(cdb), data)

    def mode_sense(self, page_code):
        data = self.read([0x5A, 0x00, page_code, 0x00, 0x00, 0x00, 0x00, 0x00, 64, 0x00], 64)
        return bytearray(data)

    def mode_select(self, data):
        payload = bytes(data)
        self.write([0x55, 0x10, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, len(payload), 0x00], payload)

    def send_diagnostic(self):
        self.write([0x1D, 0x04, 0x00, 0x00, 0x00, 0x00], b"")
        return "ok"
