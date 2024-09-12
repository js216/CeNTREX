<<<<<<< Updated upstream:drivers/nXDS.py
import logging
import time

import numpy as np
import pyvisa

import pyvisa


class nXDS:
=======
from __future__ import annotations

import datetime
import logging
import time
from dataclasses import dataclass
from enum import Enum, auto

import numpy as np
import pyvisa
from nxds import nXDS


class WarningLevel(Enum):
    WARNING = auto()
    ERROR = auto()


@dataclass
class nXDSPumpData:
    time: float
    current: float
    power: float
    link_voltage: float
    pump_temperature: float
    pump_controller_temperature: float


@dataclass
class nXDSPumpWarning:
    time: float
    message: str
    level: WarningLevel = WarningLevel.WARNING

    def to_text(self) -> str:
        ts_str = (
            datetime.datetime.fromtimestamp(self.time)
            .replace(microsecond=0)
            .isoformat()
        )
        return f"{ts_str} - {self.level.name} : {self.message}"


class nXDSPump(nXDS):
    def __init__(self, time_offset: float, ip_port: str):
        super().__init__(resource_name=ip_port, connection_type="TCPIP")
        self.time_offset = time_offset
        self.warnings = []

        # make the verification string
        self.verification_string = self.identification

        # HDF attributes generated when constructor is run
        self.new_attributes = []

    def __enter__(self) -> nXDSPump:
        return self

    def __exit__(self, *exc) -> None:
        if self.instrument:
            self.instrument.close()

    def ReadValue(self) -> nXDSPumpData:
        return nXDSPumpData(
            time=time.time() - self.time_offset,
            current=self.motor_current,
            power=self.motor_power,
            link_voltage=self.link_voltage,
            pump_temperature=self.pump_temperature,
            pump_controller_temperature=self.pump_controller_temperature,
        )

    def GetWarnings(self) -> list[nXDSPumpWarning]:
        # check if there are faults (7) present
        if self.system_status_register_2 == 7:
            fault_register = self.fault_register
            self.warnings.append(
                nXDSPumpWarning(
                    time=time.time(),
                    message=", ".join([fault.name for fault in fault_register]),
                    level=WarningLevel.ERROR,
                )
            )

        warnings = self.warnings
        self.warnings = []
        return warnings

    def StopPump(self) -> None:
        self.stop_pump()

    def StartPump(self) -> None:
        self.start_pump()


class nXDSOld:
>>>>>>> Stashed changes:drivers/nXDSPump.py
    registers = (
        "system_status_register1",
        "system_status_register2",
        "warning_register",
        "fault_register",
    )
    system_status_register1 = {
        0: "decelleration",
        1: "acceleration/running",
        2: "standby speed",
        3: "normal speed",
        4: "above ramp speed",
        5: "above overload speed",
        10: "serial enable active",
    }
    system_status_register2 = {
        0: "upper power regulator active",
        1: "lower power regulator active",
        2: "upper voltage regulator active",
        4: "service due",
        6: "warning",
        7: "alarm",
    }
    warning_register = {
        1: "low pump-controller temperature",
        6: "pump-controller temperature regulator active",
        10: "high pump-controller temperature",
        15: "self test warning",
    }
    fault_register = {
        1: "over voltage trip",
        2: "over current trip",
        3: "over temperature trip",
        4: "under temperature trip",
        5: "power stage fault",
        8: "H/W fault latch set",
        9: "EEPROM fault",
        11: "no parameter set",
        12: "self test fault",
        13: "serial control mode interlock",
        14: "overload time out",
        15: "acceleration time out",
    }

    def __init__(self, time_offset, resource_name, connection_type="TCP"):
        self.time_offset = time_offset
        self.rm = pyvisa.ResourceManager()
        try:
            if connection_type == "SERIAL":
                self.instr = self.rm.open_resource(resource_name)
            elif connection_type == "TCP":
                self.instr = self.rm.open_resource(f"TCPIP::{resource_name}::SOCKET")
            else:
                self.verification_string = "False"
                self.instr = False
                return
        except pyvisa.errors.VisaIOError as err:
            self.verification_string = "False"
            self.instr = False
            return
        self.instr.parity = pyvisa.constants.Parity.none
        self.instr.data_bits = 8
        self.instr.baud_rate = 9600
        self.instr.read_termination = "\r"
        self.instr.write_termination = "\r"

        # make the verification string
        self.verification_string = self.QueryIdentification()

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = "f"
        self.shape = (6,)

        self.warnings = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    def ReadValue(self):
        self.CheckWarningsFaults()
        return [
            time.time() - self.time_offset,
            self.MotorCurrent(),
            self.MotorPower(),
            self.LinkVoltage(),
            self.PumpTemperature(),
            self.PumpCtrlrTemperature(),
        ]

    def GetWarnings(self):
        warnings = self.warnings
        self.warnings = []
        return warnings

    def CheckWarningsFaults(self):
        registers = self.SystemStatus()
        if not registers:
            return
        if isinstance(registers, str):
            return
        else:
            for register_name, register in zip(self.registers[2:], registers[2:]):
                if isinstance(register, str):
                    logging.warning(
                        "nXDS warning in CheckWarningsFaults: register value is "
                        + register
                    )
                    continue
                # not adding system status registers to warnings
                idx = 0
                while register:
                    register_desc = eval("self." + register_name).get(idx)
                    if (register & 1) and register_desc:
                        warning_dict = {"message": register_desc}
                        self.warnings.append([time.time(), warning_dict])
                    idx += 1
                    register >>= 1

    def QueryIdentification(self):
        try:
            return self.instr.query("?S0")
        except pyvisa.errors.VisaIOError as err:
            return "nXDS warning in QueryIdentification(): " + str(err)

    def StopPump(self):
        try:
            val = self.instr.query("!C802 0")
        except pyvisa.errors.VisaIOError as err:
            return str(err)

        if "*C802 0" in val:
            return "*C802 0: No error"
        elif "*C802 1" in val:
            return "*C802 1: Invalid command for object ID"
        elif "*C802 2" in val:
            return "*C802 2: Invalid query/command"
        elif "*C802 3" in val:
            return "*C802 3: Missing parameter"
        elif "*C802 4" in val:
            return "*C802 4: Parameter out of range"
        elif "*C802 5" in val:
            return "*C802 5: Invalid command in current state, e.g., serial\
                command to start/stop when in parallel control mode."
        else:
            return val

    def StartPump(self):
        try:
            val = self.instr.query("!C802 1")
        except pyvisa.errors.VisaIOError as err:
            return str(err)

        if "*C802 0" in val:
            return "*C802 0: No error"
        elif "*C802 1" in val:
            return "*C802 1: Invalid command for object ID"
        elif "*C802 2" in val:
            return "*C802 2: Invalid query/command"
        elif "*C802 3" in val:
            return "*C802 3: Missing parameter"
        elif "*C802 4" in val:
            return "*C802 4: Parameter out of range"
        elif "*C802 5" in val:
            return "*C802 5: Invalid command in current state, e.g., serial\
                command to start/stop when in parallel control mode."
        else:
            return val

    def PumpCtrlrTemperature(self):
        try:
            val = self.instr.query("?V808")[6:].split(";")[-1]
        except pyvisa.errors.VisaIOError as err:
            logging.error(f"nXDS error in PumpCtrlrTemperature(): {str(err)}")
            return np.nan

        try:
            return float(val)
        except ValueError as err:
            logging.warning("nXDS warning in PumpCtrlrTemperature(): " + str(err))
            return np.nan

    def PumpTemperature(self):
        try:
            val = self.instr.query("?V808")[6:].split(";")[-2]
        except pyvisa.errors.VisaIOError as err:
            logging.error(f"nXDS error in PumpTemperature(): {str(err)}")
            return np.nan

        try:
            return float(val)
        except ValueError as err:
            logging.warning("nXDS warning in PumpTemperature(): " + str(err))
            return np.nan

    def LinkVoltage(self):
        try:
            val = self.instr.query("?V809")[6:]
        except pyvisa.errors.VisaIOError as err:
            logging.error(f"nXDS error in LinkVoltage(): {str(err)}")
            return np.nan

        try:
            return float(val.split(";")[-3]) / 10
        except ValueError as err:
            logging.warning("nXDS warning in LinkVoltage(): " + str(err))
            return np.nan

    def MotorPower(self):
        try:
            val = self.instr.query("?V809")
        except pyvisa.errors.VisaIOError as err:
            logging.error(f"nXDS error in MotorPower(): {str(err)}")
            return np.nan

        try:
            return float(val.split(";")[-1]) / 10
        except ValueError as err:
            logging.warning("nXDS warning in MotorPower(): " + str(err))
            return np.nan

    def PumpStatus(self):
        try:
            motor_power = self.MotorPower()
            if motor_power > 100:
                return "running"
            elif motor_power < 1:
                return "stopped"
            elif motor_power < 100:
                return "accelerating"
        except:
            return "invalid"

    def MotorCurrent(self):
        try:
            val = self.instr.query("?V809")
        except pyvisa.errors.VisaIOError as err:
            logging.error(f"nXDS error in MotorCurrent(): {str(err)}")
            return np.nan

        try:
            return float(val.split(";")[-2]) / 10
        except ValueError as err:
            logging.warning("nXDS warning in MotorCurrent(): " + str(err))
            return np.nan

    def RunHours(self):
        try:
            val = self.instr.query("?V810")[6:]
        except pyvisa.errors.VisaIOError as err:
            logging.error(f"nXDS error in RunHours(): {str(err)}")
            return np.nan

        try:
            return float(val)
        except ValueError as err:
            logging.warning("nXDS warning in RunHours(): " + str(err))
            return np.nan

    def PumpCycles(self):
        try:
            val = self.instr.query("?V811")[6:]
        except pyvisa.errors.VisaIOError as err:
            logging.error(f"nXDS error in PumpCycles(): {str(err)}")
            return np.nan

        try:
            return float(val)
        except ValueError as err:
            logging.warning("nXDS warning in PumpCycles(): " + str(err))
            return np.nan

    def TipSealService(self):
        """
        Number of pump running hours since last tip seal service;
        number of pump running hours left until tip seal service due.
        """
        try:
            return self.instr.query("?V814")[6:]
        except pyvisa.errors.VisaIOError as err:
            logging.error(f"nXDS error in TipSealService(): {str(err)}")
            return None

    def BearingService(self):
        """
        Number of pump running hours since last bearing service;
        number of pump running hours left until bearing service due.
        """
        try:
            return self.instr.query("?V815")[6:]
        except pyvisa.errors.VisaIOError as err:
            logging.error(f"nXDS error in BearingService(): {str(err)}")
            return None

    def SystemStatus(self):
        """
        Current system status:

        system status register 01;
        system status register 02;
        warning register 01 and fault register 01
        """
        ntries = 5
        attempt = 0
        while True:
            try:
                status = self.instr.query("?V802")
                words = status.split(";")[-4:]
                registers = []
                for word in words:
                    tmp = 0
                    for idx, char in zip(reversed(range(4)), word):
                        tmp += int(char, 16) << idx * 4
                    registers.append(tmp)
                return registers
            except pyvisa.errors.VisaIOError as err:
                logging.error(f"nXDS error in SystemStatus(): {str(err)}")
                return None
            except ValueError as e:
                attempt += 1
                if attempt == ntries:
                    logging.warning(f"nXDS warning in SystemStatus: {str(e)}")
                    return None

    def FaultHistory1(self):
        """
        Fault history at last trip:

        nXDS pump-controller powered time (hours)
        system status register 01;
        system status register 02;
        warning register 01 and fault register 01
        """
        try:
            return self.instr.query("?V816")[6:]
        except pyvisa.errors.VisaIOError as err:
            logging.error(f"nXDS error in FaultHistory1(): {str(err)}")
            return np.nan

    def FaultHistory2(self):
        """
        Fault history at 2nd last trip:

        nXDS pump-controller powered time (hours)
        system status register 01;
        system status register 02;
        warning register 01 and fault register 01
        """
        try:
            return self.instr.query("?V817")[6:]
        except pyvisa.errors.VisaIOError as err:
            logging.error(f"nXDS error in FaultHistory2(): {str(err)}")
            return np.nan

    def FaultHistory3(self):
        """
        Fault history at 3rd last trip:

        nXDS pump-controller powered time (hours)
        system status register 01;
        system status register 02;
        warning register 01 and fault register 01
        """
        try:
            return self.instr.query("?V818")[6:]
        except pyvisa.errors.VisaIOError as err:
            logging.error(f"nXDS error in FaultHistory3(): {str(err)}")
            return np.nan

    def FaultHistory4(self):
        """
        Fault history at 4th last trip:

        nXDS pump-controller powered time (hours)
        system status register 01;
        system status register 02;
        warning register 01 and fault register 01
        """
        try:
            return self.instr.query("?V819")[6:]
        except pyvisa.errors.VisaIOError as err:
            logging.error(f"nXDS error in FaultHistory4(): {str(err)}")
            return np.nan
