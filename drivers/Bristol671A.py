import logging
import telnetlib
import time
from typing import List, Tuple, Union

import numpy as np


class Bristol671Error(Exception):
    pass


def decompose_powers_two(number: int):
    powers = []
    i = 1
    p = 0
    while i <= number:
        if i & number:
            powers.append(p)
        i <<= 1
        p += 1
    return powers


class Bristol671A:
    def __init__(self, time_offset, connection):
        self.time_offset = time_offset
        self.telnet_address = connection["telnet_address"]
        self.telnet_port = connection["telnet_port"]
        self.timeout = 2

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data from ReadValue
        self.dtype = ("f", "f8", "f8", "f8", "f8")
        self.shape = (5,)

        self.ESE_register = {
            0: "Operation Complete (OPC)",
            1: "Not Used",
            2: "Query Error (QYE)",
            3: "Device Dependent Error (DDE)",
            4: "Execution Error (EXE)",
            5: "Command Error (CME)",
            6: "Not Used",
            7: "Power On (PON)",
        }

        self.ESR_register = {
            0: "Operation Complete (OPC)",
            1: "Not Used",
            2: "Query Error (QYE)",
            3: "Device Dependent Error (DDE)",
            4: "Execution Error (EXE)",
            5: "Command Error (CME)",
            6: "Not Used",
            7: "Power On (PON)",
        }

        self.STB_register = {
            2: "A bit is set in the event status register.",
            3: "Errors are in the error queue.",
            5: "A bit is set in the questionable register.",
        }

        self.QSR_register = {
            0: "The wavelenght has already ben read for the current scan.",
            1: "NA",
            2: "The previously requested calibration has failed.",
            3: "The power value is outside the valid range of the instrument.",
            4: "The temprature value is outside the valid range of the instrument.",
            5: "The wavelength value is outside the valid range of the instrument.",
            6: "NA",
            7: "NA",
            8: "NA",
            9: "The pressure value is outside the valid range of the instrument.",
            10: (
                "Indicates that at least one bit is set in the Questionable Hardware"
                " Condition register."
            ),
        }

        self.QHC_register = {
            0: "Reference laser has not stabilized.",
            1: "NA",
            2: "NA",
            3: "NA",
            4: "NA",
            5: "NA",
            6: "NA",
            7: "NA",
            8: "NA",
            9: "NA",
            10: "NA",
            11: "NA",
            12: "NA",
            13: "NA",
        }

        self.SCPI_errors = {
            0: "No Error",
            -101: "Invalid character",
            -102: "Syntax error",
            -103: "Invalid separator",
            -104: "Data type error",
            -220: "Parameter error",
            -221: "Settings conflict",
            -222: "Data out of range",
            -230: "Data corrupt or stale",
        }

        if self.telnet_port != "":
            try:
                self.instr = telnetlib.Telnet(
                    self.telnet_address, int(self.telnet_port)
                )
                # need to flush the first replies about the telnet connection
                for _ in range(3):
                    resp = (
                        self.instr.read_until(b"\n\n", 1)
                        .decode("ASCII")
                        .strip("\r\n\n")
                        .replace("\r\n", "")
                    )
                    if resp == "Sorry, no connections available, already in use?":
                        raise Bristol671Error("" + str(resp))
            except Exception as err:
                logging.warning(
                    "Error in initial connection to Bristal 671A : " + str(err)
                )
                self.verification_string = "False"
                self.instr = False
                self.__exit__()
                return

        # make the verification string
        try:
            self.verification_string = self.QueryIDN()
        except Bristol671Error as err:
            logging.warning("Verification error : " + str(err))
            self.verification_string = "False"

        self.SetUnitPower()

        self.warnings = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    def GetWarnings(self):
        warnings = self.warnings.copy()
        self.warnings = []
        return warnings

    def ReadValue(self) -> List[float]:
        return [
            time.time() - self.time_offset,
            self.MeasureFrequency(),
            self.FetchPower(),
            *self.FetchEnvironment(),
        ]

    #######################################################
    # Write/Query Commands
    #######################################################

    def write(self, msg: str):
        """
        Write an SCPI query over a telnet connection to the Bristol 617A.
        """
        if msg[-2:] != "\r\n":
            msg += "\r\n"
        self.instr.write(msg.encode())
        if (
            self.instr.read_until(b"\r\n", self.timeout).decode("ASCII").strip("\r\n")
            == "invalid command"
        ):
            raise Bristol671Error("{0}".format(msg.encode()))

    def query(self, msg: str) -> str:
        """
        SCPI query over a telnet connection to the Bristol 617A.
        """
        if msg[-2:] != "\r\n":
            if msg[-1] != "?":
                msg += "?"
            msg += "\r\n"
        self.instr.write(msg.encode())
        reply = (
            self.instr.read_until(b"\r\n", self.timeout).decode("ASCII").strip("\r\n")
        )
        if reply == "invalid command":
            raise Bristol671Error("Invalid command : {0}".format(msg.encode()))
        elif reply == "":
            raise Bristol671Error("No value returned : {0}".format(msg.encode()))
        else:
            return reply

    #######################################################
    #   Common Commands
    #######################################################

    def CLS(self):
        """
        Clear all event registers and the error queue.
        """
        try:
            self.write("*CLS")
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in CLS()" + str(err))

    def QueryESE(self) -> List[int]:
        """
        Queries the bits int he standard event status enable register.
        Returns an integer which is the sum of all the bit values for those bits
        that are set. See the Event Status Register Enable table below.
        """
        try:
            resp = self.query("*ESE?")
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in QueryESE()" + str(err))
        try:
            powers_two = decompose_powers_two(int(resp))
            resp = [self.ESE_register[val] for val in powers_two]
            return resp
        except Exception as err:
            logging.warning("Bristol671A warning in QueryESR()" + str(err))
            return np.nan

    def MaskESE(self, mask: int):
        """
        The *ESE (event status enable) command sets the bits in the event
        status enable register and enables the corresponding events in the
        event status register. For each bit that is set (equal to 1), the
        corresponding bit is enabled in the event status register (ESR).
        <integer> is an integer value which is the sum of all of the bit values
        for those bits that are set.
        """
        if not isinstance(mask, int):
            logging.warning("Bristol671A warning in MaskESE() mask not int")
        try:
            self.write("*ESE {0}".format(mask))
        except Exception as err:
            logging.warning("Bristol671A warning in MaskESE()" + str(err))

    def QueryESR(self) -> List[int]:
        """
        The *ESR (event status register) query returns a value which encodes
        the bits in the event status register. If any bits are set in the ESR,
        then the ESR summary bit will be set in the STB.
        Returns an integer which is the sum of all the bit values for those bits
        that are set. See Event Status Register table below.
        """
        try:
            resp = self.query("*ESR?")
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in QueryESR()" + str(err))
        try:
            powers_two = decompose_powers_two(int(resp))
            resp = [self.ESR_register[val] for val in powers_two]
            return resp
        except Exception as err:
            logging.warning("Bristol671A warning in QueryESR()" + str(err))
            return np.nan

    def QueryIDN(self) -> str:
        """
        The *IDN (identification number) query returns a string value which
        contains the instrument type, serial number, and firmware version. The
        third value is the instrument serial number. The last value is the
        imbedded software version.
        """
        try:
            resp = self.query("*IDN?")
            return resp
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in QueryIDN()" + str(err))

    def QueryOPC(self) -> str:
        """
        The *OPC (operation complete) query returns OFF when all pending
        device operations are complete, ON if an operation is pending.
        Returns OFF or ON.
        """
        try:
            resp = self.query("*OPC?")
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in QueryOPC()" + str(err))
            return np.nan
        return resp

    def RCL(self):
        """
        The *RCL (recall) command restores instrument settings.
        """
        try:
            self.write("*RCL")
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in RCL()" + str(err))

    def RST(self):
        """
        The *RST (reset) command returns the instrument’s settings to a
        known state.
        """
        try:
            self.write("*RST")
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in RST()" + str(err))

    def SAV(self):
        """
        The *SAV command saves instrument settings.
        """
        try:
            self.write("*SAV")
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in SAV()" + str(err))

    def QuerySTB(self) -> Union[int, float]:
        """
        The *STB (status byte) query returns the current value of the
        instrument’s status byte.
        Returns an integer that is the sum of all the bit values for those bits
        that are set. See the instrument Status Byte table.
        """
        try:
            resp = self.query("*STB?")
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in QuerySTB()" + str(err))
            return np.nan
        try:
            powers_two = decompose_powers_two(int(resp))
            resp = [self.STB_register[val] for val in powers_two]
            return resp
        except Exception as err:
            logging.warning("Bristol671A warning in QueryESR()" + str(err))
            return np.nan

    #######################################################
    # Measurement Commands
    #######################################################

    def Fetch(self, Q="ALL") -> Union[str, float]:
        """
        The :FETCh command will return a reading of the instrument’s current
        measurement. If :FETCh queries are made faster than the instrument’s
        update rate, it is possible to get the same reading twice. Duplicate
        readings are indicated by a bit in the questionable status register.
        """
        if Q not in ["POW", "ENV", "FREQ", "WAV", "WNUM", "ALL"]:
            logging.warning(
                "Bristol671A warning in Fetch() {0} not a valid                        "
                "      query".format(Q)
            )
            return np.nan
        # obtain value
        try:
            resp = self.query(":FETCH:{0}?".format(Q))
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in Fetch()" + str(err))
            return np.nan

        return resp

    def Read(self, Q="ALL") -> Union[str, float]:
        """
        The :READ command will return the instrument’s next measurement. The
        :MEASure command will return the following measurement. The :MEASure and
        :READ commands guarantee that each reading returned is a new one. To get
        multiple measurement types from an update (i.e., WAVelength, POWer, etc.)
        , use the :ALL query. Using separate consecutive :WAVEelength and :POWer
        queries does not guarantee that they will be from the same measurement.
        """
        if Q not in ["POW", "ENV", "FREQ", "WAV", "WNUM", "ALL"]:
            logging.warning(
                "Bristol671A warning in Read() {0} not a valid                         "
                "     query".format(Q)
            )
            return np.nan
        # obtain value
        try:
            resp = self.query(":READ:{0}?".format(Q))
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in Read() : " + str(err))
            return np.nan

        return resp

    def Measure(self, Q="ALL") -> Union[str, float]:
        """
        The :MEASure command can be considered a macro that executes multiple
        SCPI commands and is equivalent to:

            :ABORt
            :INITiate
            :FETCh[ : <function> ]?

        """
        if Q not in ["POW", "ENV", "FREQ", "WAV", "WNUM", "ALL"]:
            logging.warning(
                "Bristol671A warning in Measure() {0} not a valid                      "
                "        query".format(Q)
            )
            return np.nan
        # obtain value
        try:
            resp = self.query(":MEAS:{0}?".format(Q))
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in Measure() : " + str(err))
            return np.nan
        return resp

    def FetchPower(self) -> float:
        """
        Fetch a power reading in mW or dB, depending on the setting of :UNIT:POW.
        For clarification on fetching values see Fetch().
        """
        resp = self.Fetch(Q="POW")
        return float(resp)

    def FetchEnvironment(self) -> Tuple[float, float]:
        """
        Fetch an environment reading, returns temperature (C) and pressure
        (mm Hg) separated by a comma.
        For clarification on fetching values see Fetch().
        """
        resp = self.Fetch(Q="ENV").split(",")
        return float(resp[0].strip("C")), float(resp[1].strip("MMHG"))

    def FetchFrequency(self) -> float:
        """
        Fetch a frequency reading in THz.
        For clarification on fetching values see Fetch().
        """
        resp = self.Fetch(Q="FREQ")
        return float(resp)

    def FetchWavelenght(self) -> float:
        """
        Fetch a wavelength reading in nm.
        For clarification on fetching values see Fetch().
        """
        resp = self.Fetch(Q="WAV")
        return float(resp)

    def FetchWavenumber(self) -> float:
        """
        Fetch a wavenumber reading in 1/cm.
        For clarification on fetching values see Fetch().
        """
        resp = self.Fetch(Q="WNUM")
        return float(resp)

    def FetchAll(self) -> Tuple[int, int, float, float]:
        """
        Fetch scan index, instrument status, laser reading in display units  and
        power reading in display units.
        For clarification on fetching values see Fetch().
        """
        resp = self.Fetch(Q="ALL").split(",")
        return int(resp[0]), int(resp[1]), float(resp[2]), float(resp[3])

    def ReadPower(self) -> float:
        """
        Read a power reading in mW or dB, depending on the setting of :UNIT:POW.
        For clarification on reading values see Read().
        """
        resp = self.Read(Q="POW")
        return float(resp)

    def ReadEnvironment(self) -> Tuple[float, float]:
        """
        Read an environment reading, returns temperature (C) and pressure
        (mm Hg) separated by a comma.
        For clarification on reading values see Read().
        """
        resp = self.Read(Q="ENV").split(",")
        return float(resp[0].strip("C")), float(resp[1].strip("MMHG"))

    def ReadFrequency(self) -> float:
        """
        Read a frequency reading in THz.
        For clarification on reading values see Read().
        """
        resp = self.Read(Q="FREQ")
        return float(resp)

    def ReadWavelenght(self) -> float:
        """
        Read a wavelength reading in nm.
        For clarification on reading values see Read().
        """
        resp = self.Read(Q="WAV")
        return float(resp)

    def ReadWavenumber(self) -> float:
        """
        Read a wavenumber reading in 1/cm.
        For clarification on reading values see Read().
        """
        resp = self.Read(Q="WNUM")
        return float(resp)

    def ReadAll(self) -> Tuple[int, int, float, float]:
        """
        Read scan index, instrument status, laser reading in display units and
        power reading in display units.
        For clarification on reading values see Read().
        """
        resp = self.Read(Q="ALL").split(",")
        return int(resp[0]), int(resp[1]), float(resp[2]), float(resp[3])

    def MeasurePower(self) -> float:
        """
        Measure a power reading in mW or dB, depending on the setting of
        :UNIT:POW.
        For clarification on measuring values see Measure().
        """
        resp = self.Measure(Q="POW")
        return float(resp)

    def MeasureEnvironment(self) -> Tuple[float, float]:
        """
        Measure an environment reading, returns temperature (C) and pressure
        (mm Hg) separated by a comma.
        For clarification on measuring values see Measure().
        """
        resp = self.Measure(Q="ENV").split(",")
        return float(resp[0], resp[1])

    def MeasureFrequency(self) -> float:
        """
        Measure a frequency reading in THz.
        For clarification on measuring values see Measure().
        """
        resp = self.Measure(Q="FREQ")
        return float(resp)

    def MeasureWavelenght(self) -> float:
        """
        Measure a wavelength reading in nm.
        For clarification on measuring values see Measure().
        """
        resp = self.Measure(Q="WAV")
        return float(resp)

    def MeasureWavenumber(self) -> float:
        """
        Measure a wavenumber reading in 1/cm.
        For clarification on measuring values see Measure().
        """
        resp = self.Measure(Q="WNUM")
        return float(resp)

    def MeasureAll(self) -> Tuple[int, int, float, float]:
        """
        Measure scan index, instrument status, laser reading in display units
        and power reading in display units.
        For clarification on measuring values see Measure().
        """
        resp = self.Measure(Q="ALL").split(",")
        return int(resp[0]), int(resp[1]), float(resp[2]), float(resp[3])

    #######################################################
    # Calculate Commands
    #######################################################

    def CalculateData(self, Q="FREQ") -> float:
        """
        Returns a calculated value based on the based on the
        :DELTa:METHod setting.
        Returns a numerical value in fixed or scientific notation, depending on
        the units(see measurement of power, above). The model 671 returns 9
        significant digits for the FREQuency, WAVelength, or WNUMber
        readings, and the model 671B returns 8.
        """
        if Q not in ["POW", "FREQ", "WAV", "WNUM"]:
            logging.warning(
                "Bristol671A warning in CalculateData() {0} not a                      "
                "       valid query".format(Q)
            )
            return np.nan
        try:
            resp = self.query(":CALC:DATA? {0}".format(Q))
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in CalculateData()" + str(err))
            return np.nan
        return float(resp)

    def QueryCalculateDeltaMethod(self) -> Union[str, float]:
        """
        Query the state of the :DELTa:METHod function employed in CalculateData.
        Returns START for current-start or MAXMIN for max-min.
        """
        try:
            resp = self.query(":CALC:DELT:METH?")
        except Bristol671Error as err:
            logging.warning(
                "Bristol671A warning in QueryCalculateDeltaMethod()" + str(err)
            )
            return np.nan
        return resp

    def SetCalculateDeltaMethod(self, method="START"):
        """
        Set the state of the :DELTa:METHod function employed in CalculateData.
        Methods are START for current-start or MAXMIN for max-min.
        """
        if method not in ["START", "MAXMIN"]:
            logging.warning(
                "Bristol671A warning in SetCalculateDeltaMethod()                      "
                "        {0} not a valid method".format(method)
            )
        try:
            self.write(":CALC:DELT:METH {0}".format(method))
        except Bristol671Error as err:
            logging.warning(
                "Bristol671A warning in SetCalculateDeltaMethod()" + str(err)
            )

    def CalculateReset(self):
        """
        Resets the CALCulate subsystem. This command resets the Elapsed
        Time counter and sets the Min, Max and Start values to the Current
        Value.
        """
        try:
            self.write(":CALC:RES")
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in CalculateReset()" + str(err))

    def CalculateTimeElapsed(self) -> Union[str, float]:
        """
        Queries the elapsed time since the instrument was turned on or was
        reset.
        """
        try:
            resp = self.query(":CALC:TIME:ELAP?")
        except Bristol671Error as err:
            logging.warning(
                "Bristol671A warning in QueryCalculateTimeElapsed()" + str(err)
            )
            return np.nan
        return resp

    #######################################################
    # Sense Commands
    #######################################################

    def QueryAverageState(self) -> Union[str, float]:
        """
        Queries the state of the averaging status.
        Return OFF or ON.
        """
        try:
            resp = self.query(":SENS:AVER:STAT?")
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in QueryAverageState()" + str(err))
            return np.nan
        return resp

    def SetAverageState(self, state="ON"):
        """
        Sets the state of the averaging status.
        Valid states are OFF or ON.
        """
        if state not in ["ON", "OFF"]:
            logging.warning(
                "Bristol671A warning in SetAverageState() {0} not                      "
                "       a valdi state".format(state)
            )
            return
        try:
            self.write(":SENS:AVER:STAT {0}".format(state))
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in SetAverageState()" + str(err))

    def QueryAverageCount(self) -> Union[int, float]:
        """
        Queries the number of readings being averaged for wavelength and
        power values.
        Returns OFF, 2, 3, 4, ..., 128.
        """
        try:
            resp = self.query(":SENS:AVER:COUN?")
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in QueryAverageCount()" + str(err))
            return np.nan
        return int(resp)

    def SetAverageCount(self, count=1):
        """
        Set the number of readings being averaged for the wavelength and power
        values.
        Valid counts are OFF, 2, 3, 4, ..., 128.
        """
        if not isinstance(count, int):
            logging.warning(
                "Bristol671A warning in SetAverageCount() count requires int"
            )
            return
        if (count < 1) & (count > 128):
            logging.warning("Bristol671A warning in SetAverageCount() 0 < count < 129")
            return
        try:
            if count == 0:
                self.write(":SENS:AVER:COUN {0}".format("OFF"))
            else:
                self.write(":SENS:AVER:COUN {0}".format(count))
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in SetAverageCount()" + str(err))

    def QueryAverageData(self, Q="FREQ") -> Union[float, float]:
        """
        Returns averaged wavelength or power data for the last N number of
        measurements. The value of N is set by :AVERage: COUNt command.
        If averaging is not turned on then the most recent data is returned.
        """
        if Q not in ["POW", "FREQ", "WAV", "WNUM"]:
            logging.warning(
                "Bristol671A warning in QueryAverageData() {0} not a                   "
                "          valid query".format(Q)
            )
            return np.nan
        # obtain value
        try:
            resp = self.query(":SENS:AVER:DATA? {0}".format(Q))
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in QueryAverageData()" + str(err))
            return np.nan
        return float(resp)

    def QueryPowerOffset(self) -> Union[str, float]:
        """
        Queries the power offset being added to power values. The power
        offset is in units of dB.
        Returns OFF, 1, 2, 3, 4, ..., 20.
        """
        try:
            resp = self.query(":SENS:POW:OFFS?")
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in QueryPowerOffset()" + str(err))
            return np.nan
        return resp

    def SetPowerOffset(self, offset: int = 0):
        """
        Queries the power offset being added to power values. The power
        offset is in units of dB.
        Valid offsets are 0, 1, 2, 3, 4, ..., 20.
        """
        if not isinstance(offset, int):
            logging.warning(
                "Bristol671A warning in SetPowerOffset() count requires int"
            )
            return
        if (offset < 0) & (offset > 20):
            logging.warning("Bristol671A warning in SetPowerOffset() -1 < count < 21")
            return
        try:
            if offset == 0:
                self.write(":SENS:POW:OFFS {0}".format("OFF"))
            else:
                self.write(":SENS:POW:OFFS {0}".format(offset))
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in SetPowerOffset()" + str(err))

    #######################################################
    # Status Subsystem
    #######################################################

    def QueryQuestionableCondition(self) -> Union[List[int], float]:
        """
        Queries the SCPI Questionable Status Register which contains bits
        that indicate that one or more measurement types are of questionable
        accuracy. The bits in the register are described in the table below.
        Returns an integer which is the sum of the bit values for all bits in
        the register that are set.
        """
        try:
            resp = self.query(":STAT:QUES:COND?")
        except Bristol671Error as err:
            logging.warning(
                "Bristol671A warning in QueryQuestionableCondition()" + str(err)
            )
            return np.nan
        try:
            powers_two = decompose_powers_two(int(resp))
            resp = [self.QSR_register[val] for val in powers_two]
            return resp
        except Exception as err:
            logging.warning("Bristol671A warning in QueryESR()" + str(err))
            return np.nan

    def QueryQuestionableEnable(self) -> Union[int, float]:
        """
        Queries the SCPI Questionable Enable Register.
        Returns an integer which is the sum of the bit values for all bits in
        the register that are set.
        """
        try:
            resp = self.query(":STAT:QUES:ENAB?")
        except Bristol671Error as err:
            logging.warning(
                "Bristol671A warning in QueryQuestionableEnable()" + str(err)
            )
            return np.nan
        return int(resp)

    def SetQuestionableEnable(self, value: int):
        """
        Used to set and clear bits in the SCPI Questionable Enable Register.
        This register contains bits that are used to mask one or more
        conditions indicated in the Questionable Status Register. Setting a bit
        causes that condition to be masked so that, even if the condition is
        true, its associated bit will not get set in the Questionable Status
        Register. The Questionable Enable Register has the same format as
        the Questionable Status Register.
        """
        if not isinstance(value, int):
            logging.warning(
                "Bristol671A warning in SetQuestionableEnable()                        "
                "      count requires int"
            )
            return
        if (value < 1) & (value > 2048):
            logging.warning(
                "Bristol671A warning in SetQuestionableEnable() 0                      "
                "        < value < 2049"
            )
            return
        try:
            self.write(":STAT:QUES:ENAB {0}".format(value))
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in SetQuestionableEnable()" + str(err))

    def QueryQuestionableHardwareCondition(self) -> Union[List[int], float]:
        """
        Queries the SCPI Questionable Hardware Condition Register which
        contains bits that indicate that one or more hardware problems exist.
        These problems may contribute to invalid or erred measurements.
        Returns an integer which is the sum of the bit values for all bits in
        the register that are set.
        """
        try:
            resp = self.query(":STAT:QUES:HARD:COND?")
        except Bristol671Error as err:
            logging.warning(
                "Bristol671A warning in                             "
                " QueryQuestionableHardwareCondition()" + str(err)
            )
            return np.nan
        try:
            powers_two = decompose_powers_two(int(resp))
            resp = [self.QHR_register[val] for val in powers_two]
            return resp
        except Exception as err:
            logging.warning("Bristol671A warning in QueryESR()" + str(err))
            return np.nan

    #######################################################
    # System Subsystem
    #######################################################

    def QueryError(self) -> Union[Tuple[int, str], float]:
        """
        Reads error strings from the SCPI Error Queue. If the Error Queue has
        any entries, the Error Queue bit is set in the Status Byte. The
        instrument has a 30 entry, first-in, first-out queue. Repeatedly sending
        the query :SYST:ERr? returns the error numbers and descriptions in
        the order in which they occurred until the queue is empty. Any further
        queries return "No error" until another error occurs.
        Returns errors in format <integer>, <string> (e.g., –104, “Data type error”)
        """
        try:
            resp = self.query(":SYST:ERR?")
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in QueryError()" + str(err))
            return np.nan
        try:
            resp = resp.split(",")
            return int(resp[0]), resp[1]
        except Exception as err:
            logging.warning("Bristol671A warning in QueryError()" + str(err))
            return np.nan

    def Help(self) -> Union[str, float]:
        """
        Reads a list of all commands and queries supported by the instrument.
        Each line of the response is terminated by a linefeed. The first line
        indicates the number of bytes of help data that follow. The remaining
        lines are strings of help data. All lines of data must be read before
        continuing normal operations.
        """
        try:
            resp = self.query(":SYST:HELP:HEAD?")
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in Help()" + str(err))
            return np.nan
        return resp

    #######################################################
    # Unit Subsystem
    #######################################################

    def QueryUnitPower(self) -> str:
        """
        Queries the state of the power units that will be used when the SCPI
        interface returns power values.
        Returns DBM or MW.
        """
        try:
            resp = self.instr.queary(":UNIT:POW?")
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in SetUnitPower()" + str(err))
        return resp

    def SetUnitPower(self, unit: str = "MW"):
        """
        Sets the state of the power units that will be used when the SCPI
        interface returns power values. This setting does not affect the display.
        Valid units are DBM or MW.
        """
        if unit not in ["MW", "DBM"]:
            logging.warning(
                "Bristol671A warning in SetUnitPower() unit not                        "
                "      valid"
            )
        try:
            self.write(":UNIT:POW {0}".format(unit))
        except Bristol671Error as err:
            logging.warning("Bristol671A warning in SetUnitPower()" + str(err))
