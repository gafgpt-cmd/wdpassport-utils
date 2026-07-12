def fail(message: str) -> str:
    return "\033[91m[!]\033[0m " + message


def success(message: str) -> str:
    return "\033[92m[*]\033[0m " + message


def question(message: str) -> str:
    return "\033[94m[+]\033[0m " + message


def security_status_label(value: int) -> str:
    return {
        0x00: "No lock",
        0x01: "Locked",
        0x02: "Unlocked",
        0x06: "Locked, unlock blocked",
        0x07: "No keys",
    }.get(value, f"Unknown ({value:#x})")


def cipher_label(value: int) -> str:
    return {
        0x10: "AES_128_ECB",
        0x12: "AES_128_CBC",
        0x18: "AES_128_XTS",
        0x20: "AES_256_ECB",
        0x22: "AES_256_CBC",
        0x28: "AES_256_XTS",
        0x30: "Full Disk Encryption",
    }.get(value, f"Unknown ({value:#x})")
