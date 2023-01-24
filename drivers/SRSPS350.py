import functools
import logging
import time
from typing import List, Union

import numpy as np
import pyvisa


def get_set_bits(value: int):
    value = int(value)
    # # calculate which bits are set
    # bits = [val >> i & 1 for i in range(val.bit_length()) if (i & 1 == 1)]
    # # get the location of the set bit
    # return [i for i in range(len(bits)) if bits[-(i+1)]]
    return [i for i in range(value.bit_length()) if (value >> i & 1)]


def CheckCommandExecution(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        func(*args, **kwargs)
        args[0]._CheckCommandExecution(func.__name__)

    return wrapper


class SRSPS350:
    def __init__(self, time_offset: float, resource_name: str):
        self.time_offset = time_offset
        self.rm = pyvisa.ResourceManager()

        try:
            self.instr = self.rm.open_resource(resource_name)
        except pyvisa.errors.VisaIOError:
            self.verification_string = "False"
            self.instr = False
            return
        self.instr.parity = pyvisa.constants.Parity.none
        self.instr.data_bits = 8
        self.instr.baud_rate = 9600
        self.instr.term_char = "\r\n"
        self.instr.read_termination = "\n"

        # make the verification string
        self.verification_string = self.QueryIdentification()

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = ("f", "float", "float")
        self.shape = (3,)

        self.warnings = []

        self.serial_poll_status_byte = {
            0: "stable",
            1: "v trip",
            2: "i trip",
            3: "i lim",
            4: "MAV",
            5: "ESB",
            6: "RQS",
            7: "hv on",
        }

        self.standard_event_status_byte = {
            2: "Query Error",
            3: "Recall Error",
            4: "Execution Error",
            5: "Command Error",
            6: "URQ",
            7: "PON",
        }

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    def ReadValue(self) -> List[float]:
        ret = [time.time() - self.time_offset, self.GetVoltage(), self.GetCurrent()]
        return ret

    def GetWarnings(self):
        warnings = self.warnings[:]
        self.warnings = []

        stb = get_set_bits(self.GetSerialStatusRegister())
        for val in stb:
            if val in [1, 2, 3, 5]:
                logging.warning(
                    f"SRS PS350 warning : {self.serial_poll_status_byte[val]}"
                )
                warning_dict = {"message": f"{self.serial_poll_status_byte[val]}"}
                warnings.append([time.time(), warning_dict])

        self.warnings = []
        return warnings

    def QueryIdentification(self) -> Union[str, np.nan]:
        """Identifies the instrument model and software level.

        Returns:
        <manufacturer>, <model number>, <serial number>, <firmware date>
        """
        try:
            return self.instr.query("*IDN?")
        except pyvisa.errors.VisaIOError:
            return np.nan

    def TurnHVOn(self):
        self.SetHV(True)

    def TurnHVOff(self):
        self.SetHV(False)

    def GetHVState(self) -> str:
        hv_status = self.GetSerialStatusRegister() >> 7
        if hv_status:
            return "HV On"
        else:
            return "HV Off"

    def _CheckCommandExecution(self, cmd: str):
        esr = get_set_bits(self.GetStandardStatusRegister())
        for val in esr:
            if val in [2, 3, 4, 5, 6, 7]:
                logging.warning(
                    f"SRS PS350 warning in {cmd} :"
                    f" {self.standard_event_status_byte[val]}"
                )

    def GetVoltage(self) -> float:
        return float(self.instr.query("VOUT?"))

    def GetCurrent(self) -> float:
        return float(self.instr.query("IOUT?"))

    @CheckCommandExecution
    def SetHV(self, state: bool):
        if state in [True, False]:
            state = "HVON" if state else "HVOF"
            self.instr.write(f"{state}")
        else:
            logging.warning(
                "SRS PS350 warning in SetHV(): set state True (On) or False (Off) !="
                f" {state}"
            )

    def GetILim(self) -> float:
        return float(self.instr.query("ILIM?"))

    @CheckCommandExecution
    def SetILim(self, current: float):
        self.instr.write(f"ILIM{current}")

    @CheckCommandExecution
    def SetVoltage(self, voltage: float):
        self.instr.write(f"VSET{voltage}")

    def GetSetVoltage(self) -> float:
        return float(self.instr.query("VSET?"))

    def GetVLim(self) -> float:
        return float(self.instr.query("VLIM?"))

    @CheckCommandExecution
    def SetVLim(self, voltage: float):
        self.instr.write(f"VLIM{voltage}")

    def GetSerialStatusRegister(self) -> int:
        serial_status_register = self.instr.query("*STB?")
        return int(serial_status_register)

    def GetStandardStatusRegister(self) -> int:
        return int(self.instr.query("*ESR?"))
