import time
from typing import Sequence, Tuple

import pyvisa


class _SPD3303X:
    def __init__(self, resource: str):
        self.rm = pyvisa.ResourceManager()
        self.dev = self.rm.open_resource(resource_name=resource)
        self.dev.read_termination = "\n"

    def _query(self, command: str) -> str:
        return self.dev.query(command)

    def _write(self, command: str):
        self.dev.write(command)

    @property
    def idn(self):
        return self._query("*IDN?")

    def save(self, memory: int):
        self._write(f"*SAV{memory}")

    def voltage_setpoint(self, voltage: float, channel: int):
        self._write(f"CH{channel}:VOLT {voltage}")

    def current_setpoint(self, current: float, channel: int):
        self._write(f"CH{channel}:CURR {current}")

    def power(self, channel: int) -> float:
        return float(self._query(f"MEAS:POWE? CH{channel}"))

    def output(self, on: bool, channel: int):
        if on:
            state = "ON"
        else:
            state = "OFF"
        self._write(f"OUTP CH{channel},{state}")

    @property
    def ch1_power(self) -> float:
        return self.power(1)

    @property
    def ch1_voltage(self) -> float:
        return float(self._query("MEAS:VOLT? CH1"))

    @property
    def ch1_current(self) -> float:
        return float(self._query("MEAS:CURR? CH1"))

    @property
    def ch1_voltage_setpoint(self) -> float:
        return float(self._query("CH1:VOLT?"))

    @ch1_voltage_setpoint.setter
    def ch1_voltage_setpoint(self, voltage: float):
        self.voltage_setpoint(voltage, 1)

    @property
    def ch1_current_setpoint(self) -> float:
        return float(self._query("CH1:CURR?"))

    @ch1_current_setpoint.setter
    def ch1_current_setpoint(self, current: float):
        self.current_setpoint(current, 1)

    @property
    def ch2_power(self) -> float:
        return self.power(2)

    @property
    def ch2_voltage(self) -> float:
        return float(self._query("MEAS:VOLT? CH2"))

    @property
    def ch2_current(self) -> float:
        return float(self._query("MEAS:CURR? CH2"))

    @property
    def ch2_voltage_setpoint(self) -> float:
        return float(self._query("CH2:VOLT?"))

    @ch2_voltage_setpoint.setter
    def ch2_voltage_setpoint(self, voltage: float):
        self.voltage_setpoint(voltage, 2)

    @property
    def ch2_current_setpoint(self) -> float:
        return float(self._query("CH2:CURR?"))

    @ch2_current_setpoint.setter
    def ch2_current_setpoint(self, current: float):
        self.current_setpoint(current, 2)


class SPD3303X(_SPD3303X):
    def __init__(self, time_offset: float, resource: str):
        super(SPD3303X, self).__init__(resource=resource)

        self.time_offset = time_offset

        # make the verification string
        try:
            self.verification_string = self.idn
        except pyvisa.errors.VisaIOError as err:
            self.verification_string = str(err)

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = "f"
        self.shape = (5,)

        self.warnings = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.dev.close()

    def ReadValue(self) -> Tuple[float, float, float, float, float]:
        return [
            time.time() - self.time_offset,
            self.ch1_voltage,
            self.ch2_voltage,
            self.ch1_current,
            self.ch2_current,
        ]

    def GetWarnings(self) -> Sequence[Tuple[float, str]]:
        warnings = self.warnings
        self.warnings = []
        return warnings

    def set_ch1_voltage(self, voltage: float):
        self.ch1_voltage_setpoint = voltage

    def set_ch2_voltage(self, voltage: float):
        self.ch2_voltage_setpoint = voltage

    def set_ch1_current(self, current: float):
        self.ch1_current_setpoint = current

    def set_ch2_current(self, current: float):
        self.ch2_current_setpoint = current
