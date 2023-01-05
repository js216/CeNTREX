import asyncio
import logging
import time

import numpy as np
from toptica.lasersdk.dlcpro.v2_6_0 import (
    DecopError,
    DeviceNotFoundError,
    DLCpro,
    NetworkConnection,
    SerialConnection,
)


class DLCPro:
    def __init__(
        self, time_offset: float, resource_name: str, connection_type: str = "SERIAL"
    ):
        self.time_offset = time_offset

        self.resource_name = resource_name
        self.connection_type = connection_type

        # need to generate an event loop; only the main thread has an event loop
        self.loop = asyncio.set_event_loop(asyncio.new_event_loop())

        if connection_type == "SERIAL":
            self.con = SerialConnection(resource_name, baudrate=9600)
        elif connection_type == "TCP":
            self.con = NetworkConnection(resource_name)
        else:
            self.verification_string = "False"
            return

        try:
            with DLCpro(self.con) as dlc:
                self.verification_string = dlc.laser1.product_name.get()
        except DeviceNotFoundError:
            self.verification_string = "False"
            return

        measured_values = 6
        self.dtype = tuple(["f8"] * (1 + measured_values))
        self.shape = ((1 + measured_values),)
        self.new_attributes = []
        self.warnings = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return

    def GetWarnings(self):
        warnings = self.warnings
        self.warnings = []
        return warnings

    def ReadValue(self):
        try:
            with DLCpro(self.con) as dlc:
                emission = dlc.laser1.emission.get()
                dl_temperature_act = dlc.laser1.dl.tc.temp_act.get()
                dl_temperature_set = dlc.laser1.dl.tc.temp_set.get()
                piezo_voltage = dlc.laser1.dl.pc.voltage_act.get()
                diode_current = dlc.laser1.dl.cc.current_act.get()
                pressure = dlc.laser1.dl.pressure_compensation.air_pressure.get()
            return [
                time.time() - self.time_offset,
                emission,
                piezo_voltage,
                diode_current,
                dl_temperature_act,
                dl_temperature_set,
                pressure,
            ]
        except Exception as e:
            logging.warning("DLCPro warning in ReadValue(): " + str(e))
            return np.nan
