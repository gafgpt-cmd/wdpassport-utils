"""Pure-Python Linux SG_IO transport (replaces the compiled py3_sg C-extension).

Uses the SCSI generic (sg) SG_IO ioctl via ctypes + fcntl, so the package has
no compiled dependency and runs on any Python 3 / any Debian flavor. Exposes the
same two operations the rest of the code needs: read (data-in) and write
(data-out) given a raw CDB.
"""

import ctypes
import fcntl

SG_IO = 0x2285
SG_DXFER_NONE = -1
SG_DXFER_TO_DEV = -2
SG_DXFER_FROM_DEV = -3
_SENSE_LEN = 32
_DEFAULT_TIMEOUT_MS = 20000


class SgioError(OSError):
    """Raised when an SG_IO command fails at the SCSI/transport layer."""


class _SgIoHdr(ctypes.Structure):
    _fields_ = [
        ("interface_id", ctypes.c_int),
        ("dxfer_direction", ctypes.c_int),
        ("cmd_len", ctypes.c_ubyte),
        ("mx_sb_len", ctypes.c_ubyte),
        ("iovec_count", ctypes.c_ushort),
        ("dxfer_len", ctypes.c_uint),
        ("dxferp", ctypes.c_void_p),
        ("cmdp", ctypes.c_void_p),
        ("sbp", ctypes.c_void_p),
        ("timeout", ctypes.c_uint),
        ("flags", ctypes.c_uint),
        ("pack_id", ctypes.c_int),
        ("usr_ptr", ctypes.c_void_p),
        ("status", ctypes.c_ubyte),
        ("masked_status", ctypes.c_ubyte),
        ("msg_status", ctypes.c_ubyte),
        ("sb_len_wr", ctypes.c_ubyte),
        ("host_status", ctypes.c_ushort),
        ("driver_status", ctypes.c_ushort),
        ("resid", ctypes.c_int),
        ("duration", ctypes.c_uint),
        ("info", ctypes.c_uint),
    ]


def _fileno(fileobj):
    return fileobj.fileno() if hasattr(fileobj, "fileno") else int(fileobj)


def _run(fileobj, cdb: bytes, direction: int, dxferp, dxfer_len: int,
         timeout_ms: int = _DEFAULT_TIMEOUT_MS):
    cmd_buf = ctypes.create_string_buffer(bytes(cdb), len(cdb))
    sense = ctypes.create_string_buffer(_SENSE_LEN)
    hdr = _SgIoHdr()
    hdr.interface_id = ord("S")
    hdr.dxfer_direction = direction
    hdr.cmd_len = len(cdb)
    hdr.mx_sb_len = _SENSE_LEN
    hdr.iovec_count = 0
    hdr.dxfer_len = dxfer_len
    hdr.dxferp = ctypes.cast(dxferp, ctypes.c_void_p) if dxferp else None
    hdr.cmdp = ctypes.cast(cmd_buf, ctypes.c_void_p)
    hdr.sbp = ctypes.cast(sense, ctypes.c_void_p)
    hdr.timeout = timeout_ms
    hdr.flags = 0
    hdr.pack_id = 0

    fcntl.ioctl(_fileno(fileobj), SG_IO, hdr)

    if hdr.status != 0 or hdr.host_status != 0 or (hdr.driver_status & 0x0F) != 0:
        sk = sense.raw[2] & 0x0F if hdr.sb_len_wr > 2 else 0
        raise SgioError(
            f"SCSI command failed: status={hdr.status:#x} "
            f"host_status={hdr.host_status:#x} driver_status={hdr.driver_status:#x} "
            f"sense_key={sk:#x}"
        )
    return hdr


def read(fileobj, cdb: bytes, size: int) -> bytes:
    """Send a data-in SCSI command and return the ``size`` bytes read."""
    buf = ctypes.create_string_buffer(size)
    _run(fileobj, cdb, SG_DXFER_FROM_DEV, buf, size)
    return buf.raw[:size]


# Compatibility alias for the py3_sg call name used previously.
read_as_bin_str = read


def write(fileobj, cdb: bytes, data: bytes) -> None:
    """Send a data-out SCSI command carrying ``data`` (may be empty)."""
    if data:
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        _run(fileobj, cdb, SG_DXFER_TO_DEV, buf, len(data))
    else:
        _run(fileobj, cdb, SG_DXFER_NONE, None, 0)
