from .formatting import cipher_label, security_status_label


class DeviceSelectionError(RuntimeError):
    pass


def choose_single_device(devices):
    if len(devices) == 0:
        raise DeviceSelectionError("No Western Digital Passport device found.")
    if len(devices) > 1:
        raise DeviceSelectionError("Multiple Western Digital Passport devices found. Use --device to choose.")
    return devices[0]


def status_summary(device, device_path: str) -> dict:
    status = device.encryption_status()
    try:
        hint = device.read_security_block().hint
    except Exception:
        hint = ""
    return {
        "device": device_path,
        "security_status": security_status_label(status.security_status),
        "cipher": cipher_label(status.current_cipher),
        "password_length": status.password_length,
        "supported_ciphers": [cipher_label(cipher) for cipher in status.supported_ciphers],
        "hint": hint,
    }
