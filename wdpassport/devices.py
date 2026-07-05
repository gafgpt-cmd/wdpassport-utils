def is_passport_device(disk_device) -> bool:
    device = disk_device
    while device is not None:
        if "ID_SERIAL" in device:
            if device.properties["ID_SERIAL"].startswith("Western_Digital_My_"):
                return True
        device = device.parent
    return False


def find_passport_devices(context, forced_device=None) -> list:
    passport_devices = []
    for disk_device in context.list_devices(subsystem="block", DEVTYPE="disk"):
        if forced_device and disk_device.device_node != forced_device:
            continue
        if is_passport_device(disk_device):
            passport_devices.append(disk_device)
    return passport_devices
