from device import Device


def get_device_methods(device: str, devices: dict[str, Device]) -> list[str]:
    methods = [
        method
        for method in devices[device].config.driver_class.__dict__
        if method[:2] != "__"
    ]
    return methods
