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

# SCSI status byte values
GOOD = 0x00
CHECK_CONDITION = 0x02
DRIVER_OK = 0x00
DRIVER_SENSE = 0x08
DRIVER_STATUS_MASK = 0x0F


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

    # Interpret the result. A CHECK CONDITION (status 0x02) is NOT automatically
    # a failure: sense key NO SENSE (0x0) or RECOVERED ERROR (0x1) means the
    # command completed successfully. The driver's DRIVER_SENSE bit (0x08) just
    # signals that sense data is present, so it must not be treated as an error
    # on its own. Only a transport error, a fatal sense key, or a non-GOOD /
    # non-CHECK-CONDITION status is a real failure.
    sense_data = sense.raw[:hdr.sb_len_wr]
    response_code = sense_data[0] & 0x7F if sense_data else 0
    sense_valid = False
    if response_code in (0x72, 0x73) and len(sense_data) > 1:
        sk = sense_data[1] & 0x0F
        sense_valid = True
    elif response_code in (0x70, 0x71) and len(sense_data) > 2:
        sk = sense_data[2] & 0x0F
        sense_valid = True
    else:
        sk = 0
    check_condition = hdr.status == CHECK_CONDITION
    driver_result = hdr.driver_status & DRIVER_STATUS_MASK
    sense_required = check_condition or driver_result == DRIVER_SENSE
    fatal = (
        hdr.host_status != 0
        or driver_result not in (DRIVER_OK, DRIVER_SENSE)
        or (sense_required and not sense_valid)
        or (sense_required and sk not in (0x00, 0x01))
        or (not check_condition and hdr.status != GOOD)
    )
    if fatal:
        meaning = (
            _SENSE_KEY_MEANING.get(sk, f"sense key {sk:#x}")
            if sense_valid or not sense_required
            else "invalid or missing sense data"
        )
        raise SgioError(
            f"{meaning} (status={hdr.status:#x}, "
            f"host_status={hdr.host_status:#x}, driver_status={hdr.driver_status:#x}, "
            f"sense_key={sk:#x})"
        )
    if hdr.resid < 0 or hdr.resid > dxfer_len:
        raise SgioError(f"invalid residual byte count {hdr.resid} for transfer of {dxfer_len}")
    return hdr


_SENSE_KEY_MEANING = {
    0x2: "drive not ready",
    0x3: "medium error",
    0x4: "hardware error",
    0x5: "not supported by this drive model",
    0x6: "unit attention (drive state changed — retry)",
    0x7: "data protected / drive is locked",
    0xB: "command aborted",
}


def read(fileobj, cdb: bytes, size: int) -> bytes:
    """Send a data-in SCSI command and return the ``size`` bytes read."""
    buf = ctypes.create_string_buffer(size)
    hdr = _run(fileobj, cdb, SG_DXFER_FROM_DEV, buf, size)
    return buf.raw[:size - hdr.resid]


# Compatibility alias for the py3_sg call name used previously.
read_as_bin_str = read


def write(fileobj, cdb: bytes, data: bytes) -> None:
    """Send a data-out SCSI command carrying ``data`` (may be empty)."""
    if data:
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        hdr = _run(fileobj, cdb, SG_DXFER_TO_DEV, buf, len(data))
        if hdr.resid:
            raise SgioError(
                f"partial data-out transfer: {len(data) - hdr.resid} of {len(data)} bytes written")
    else:
        _run(fileobj, cdb, SG_DXFER_NONE, None, 0)
