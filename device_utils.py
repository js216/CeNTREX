import importlib
import inspect

from device import Device


def get_device_methods(device: str, devices: dict[str, Device]) -> list[str]:
    if devices[device].config["driver_class"].__name__ != "NetworkingClient":
        driver = devices[device].config["driver_class"]

    else:
        driver_name = devices[device].config["control_params"]["driver"]["value"]

        driver_spec = importlib.util.spec_from_file_location(
            driver_name,
            "drivers/" + driver_name + ".py",
        )

        driver_module = importlib.util.module_from_spec(driver_spec)
        driver_spec.loader.exec_module(driver_module)
        driver = getattr(driver_module, driver_name)

    methods = [m[0] for m in inspect.getmembers(driver, predicate=inspect.isfunction)]
    return methods
