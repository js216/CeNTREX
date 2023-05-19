import logging
import time
from enum import Enum

import numpy as np
import pyvisa as visa


class TECErrors(Enum):
    ENABLE_NOT_LOW = 0
    INTERNAL_TEMP_HIGH = 1
    THERMAL_LATCH = 2
    CYCLING_SMALL = 3
    NO_SENSOR = 4
    NO_TEC = 5
    TEC_MISPOLED = 6
    VALUE_OUT_OF_RANGE = 13
    INVALID_COMMAND = 14


def getSetBits(value):
    return [i for i in range(value.bit_length()) if (value >> i & 1)]


class CeNTREXTecDeviceInterface:
    """Python interface for the CeNTREX TEC Device, consisting of multiple
    Thorlabs MTD415T connected to a Teensy 4 serving as the main controller.
    See https://www.thorlabs.com/thorproduct.cfm?partnumber=MTD415T for more
    information on the MTD415T.
    """

    def __init__(self, resource_name, number_devices):
        self.rm = visa.ResourceManager()
        self.instr = self.rm.open_resource(resource_name)
        self.instr.baud_rate = 115200
        self.instr.read_termination = "\n"
        self.instr.write_termination = "\n"
        self.number_devices = number_devices

    def write_convert(self, values, factor=1):
        values = np.asarray(values, dtype=int)
        return (values * factor).astype(int)

    def return_convert(self, ret, conv=float, split=",", factor=1):
        if conv == bool:
            conv = lambda x: bool(int(x))
        return [conv(val) * factor for val in ret.split(split)]

    def write(self, cmd, values):
        self.instr.write(f"{cmd}{','.join(str(val) for val in values)}!")

    def getTemperature(self):
        """Get the current temperature of each device

        Returns:
            list: temperature per device in C
        """
        ret = self.instr.query("Te?")
        return self.return_convert(ret, factor=1e-3)

    def getTemperatureSetpoint(self):
        """Get the temperature setpoint of each device in C

        Returns:
            list: temperature setpoint per device in C
        """
        ret = self.instr.query("T?")
        return self.return_convert(ret, factor=1e-3)

    def setTemperatureSetpoint(self, temperature):
        """Write the temperature setpoint of each device in C

        Args:
            temperature (list): temperature setpoint per device in C
        """
        self.write("T", self.write_convert(temperature, 1e3))

    def getProportional(self):
        ret = self.instr.query("P?")
        return self.return_convert(ret, conv=int)

    def setProportional(self, proportional):
        self.write("P", proportional)

    def getIntegral(self):
        ret = self.instr.query("I?")
        return self.return_convert(ret, conv=int)

    def setIntegral(self, integral):
        self.write("I", integral)

    def getDerivative(self):
        ret = self.instr.query("D?")
        return self.return_convert(ret, conv=int)

    def setDerivative(self, derivative):
        self.write("D", derivative)

    def getTecCurrentLimit(self):
        ret = self.instr.query("L?")
        return self.return_convert(ret, factor=1e-3)

    def setTecCurrentLimit(self, limit):
        self.write("L", limit)

    def getTecCurrent(self):
        ret = self.instr.query("A?")
        return self.return_convert(ret, factor=1e-3)

    def getTecVoltage(self):
        ret = self.instr.query("U?")
        return self.return_convert(ret, factor=1e-3)

    def getState(self):
        ret = self.instr.query("S?")
        return self.return_convert(ret, conv=bool)

    def getUUID(self):
        ret = self.instr.query("u?")
        return ret.split(",")

    def getVersion(self):
        ret = self.instr.query("m?")
        return ret.split(",")

    def getError(self):
        ret = self.instr.query("E?")
        return self.return_convert(ret, conv=int)

    def resetError(self, device):
        self.instr.write(f"c{device}!")

    def getCriticalGain(self):
        ret = self.instr.query("G?")
        return self.return_convert(ret, conv=int)

    def setCriticalGain(self, critical_gain):
        self.write("G", critical_gain)

    def getCriticalPeriod(self):
        ret = self.instr.query("O?")
        return self.return_convert(ret, conv=int)

    def setCriticalPeriod(self, period):
        self.write("O", period)

    def getCyclingTime(self):
        ret = self.instr.query("C?")
        return self.return_convert(ret, factor=1e-3)

    def setCyclingTime(self, cycling_time):
        self.write("C", cycling_time)

    def getTemperatureWindow(self):
        ret = self.instr.query("W?")
        return self.return_convert(ret, conv=int)

    def setTemperatureWindow(self, window):
        self.write("W", window)

    def enableTEC(self, enable):
        self.write("e", enable)

    def getEnableState(self):
        ret = self.instr.query("S?")
        return self.return_convert(ret, conv=bool)

    def saveSetup(self, device):
        self.instr.write(f"M{device}!")


class CeNTREXTECControl(CeNTREXTecDeviceInterface):
    def __init__(self, time_offset, resource_name, number_devices: int):
        number_devices = int(number_devices)
        super(CeNTREXTECControl, self).__init__(resource_name, number_devices)
        self.time_offset = time_offset

        # make the verification string
        self.verification_string = self.QueryIdentification()

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.shape = (1 + 4 * number_devices,)
        self.dtype = ["f"]
        self.dtype.extend(["float", "float", "float", "float", "bool"] * number_devices)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    #########################################
    ### CeNTREX DAQ CONTROL COMMANDS
    #########################################

    def QueryIdentification(self):
        return "_".join(self.getUUID())

    def ReadValue(self):
        """Read some general values from the CeNTREX TEC device. Returns values
        per device in a list

        Returns:
            list: [time, setpoint, temperature, current, voltage, state
                      {, setpoint, temperature, current, voltage, state}, ...]
        """
        Tset = self.getTemperatureSetpoint()
        T = self.getTemperature()
        I = self.getTecCurrent()
        V = self.getTecVoltage()
        S = self.getState()
        ret = [time.time() - self.time_offset]
        for i in range(self.number_devices):
            ret.extend([Tset[i], T[i], I[i], V[i], S[i]])
        return ret

    def GetWarnings(self):
        return []

    def EnableDevice(self, device):
        """Enable the TEC device

        Args:
            device (int): device number, starting at 1
        """
        device -= 1
        s = self.getState()
        s[device] = 1
        self.enableTEC(s)

    def DisableDevice(self, device):
        """Disable the TEC device

        Args:
            device (int): device number, starting at 1
        """
        device -= 1
        vals = self.getState()
        vals[device] = 0
        self.enableTEC(vals)

    def _setValConvenienceFunction(self, attr, value, device):
        error = False
        device -= 1
        getter = getattr(self, attr.replace("set", "get"))
        setter = getattr(self, attr)
        if not getter:
            logging.warning(
                f"CeNTREXTECDevice warning in _setValConvenienceFunction for {attr} :"
                " no getter exists"
            )
            error = True
        if not setter:
            logging.warning(
                f"CeNTREXTECDevice warning in _setValConvenienceFunction for {attr} :"
                " no setter exists"
            )
            error = True
        if error:
            return
        vals = getter()
        vals[device] = value
        setter(vals)
        return

    def SetTemperatureSetpoint(self, temperature, device):
        """Set the temperature setpoint of a TEC device in the CeTREX Teensy
        TEC controller

        Args:
            temperature (float): temperature in C
            device (int): device number, starting at 1
        """
        self._setValConvenienceFunction("setTemperatureSetpoint", temperature, device)

    def SetProportional(self, proportional, device):
        """Set the proportional gain of the TEC controller

        Args:
            proportional (int): proportional gain
            device (int): device number, starting at 1
        """
        self._setValConvenienceFunction("setProportional", proportional, device)

    def SetIntegral(self, integral, device):
        """Set the integral gain of the TEC controller

        Args:
            integral (int): integral gain
            device (int): device number, starting at 1
        """
        self._setValConvenienceFunction("setIntegral", integral, device)

    def SetDerivative(self, derivative, device):
        """Set the derivative gain of the TEC controller

        Args:
            derivative (int): derivative gain
            device (int): device number, starting at 1
        """
        self._setValConvenienceFunction("setDerivative", derivative, device)

    def SetTecCurrentLimit(self, limit, device):
        """Set the TEC current limit in mA

        Args:
            limit (int): current limit in mA
            device (int): device number, starting at 1
        """
        self._setValConvenienceFunction("setTecCurrentLimit", limit, device)

    def SetTemperatureWindow(self, window, device):
        """Set the TEC temperature window in mK

        Args:
            window (int): temperature window in mK
            device (int): device number, starting at 1
        """
        self._setValConvenienceFunction("setTemperatureWindow", window, device)


if __name__ == "__main__":
    dev = CeNTREXTecDevice(time.time(), "COM5", 2)
    print(dev.verification_string)
    print(dev.ReadValue())
    dev.SetTemperatureSetpoint(25, 1)
    dev.SetProportional(3000, 2)
    print(dev.getProportional())
    dev.__exit__()
