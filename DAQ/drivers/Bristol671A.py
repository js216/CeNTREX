import pyvisa
import time
import numpy as np
import logging

class Bristol671A:
    def __init__(self, time_offset, resource_name):
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
        self.instr.stop_bits = pyvisa.constants.StopBits.one
        self.instr.term_char = '\r\n'
        self.instr.read_termination = '\r\n'
        self.instr.timeout = 5000

        # make the verification string
        try:
           self.verification_string = self.ReadIDN()
        except pyvisa.errors.VisaIOError:
           self.verification_string = "False"

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data from ReadValue
        self.dtype = 'f'
        self.shape = (2, )

        self.ESE_register = {0: "Operation Complete (OPC)",
                             1: "Not Used",
                             2: "Query Error (QYE)",
                             3: "Device Dependent Error (DDE)",
                             4: "Execution Error (EXE)",
                             5: "Command Error (CME)"
                             6: "Not Used"
                             7: "Power On (PON)"}

        self.ESR_register = {0: "Operation Complete (OPC)",
                             1: "Not Used",
                             2: "Query Error (QYE)",
                             3: "Device Dependent Error (DDE)",
                             4: "Execution Error (EXE)",
                             5: "Command Error (CME)"
                             6: "Not Used"
                             7: "Power On (PON)"}

        self.STB_register = {2: "A bit is set in the event status register.",
                             3: "Errors are in the error queue.",
                             5: "A bit is set in the questionable register."}

        self.QSR_register = {0: "The wavelenght has already ben read for the current scan.",
                             1: "NA",
                             2: "The previously requested calibration has failed.",
                             3: "The power value is outside the valid range of the instrument.",
                             4: "The temprature value is outside the valid range of the instrument.",
                             5: "The wavelength value is outside the valid range of the instrument."
                             6: "NA"
                             7: "NA",
                             8: "NA"
                             9: "The pressure value is outside the valid range of the instrument."
                             10: "Indicates that at least one bit is set in the Questionable Hardware Condition register."}

        self.QHC_register = {0: "Reference laser has not stabilized.",
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
                             13: "NA",}

        self.SCPI_errors = {0: "No Error",
                            -101: "Invalid character",
                            -102: "Syntax error",
                            -103: "Invalid separator",
                            -104: "Data type error",
                            -220: "Parameter error",
                            -221: "Settings conflict",
                            -222: "Data out of range",
                            -230: "Data corrupt or stale"}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    def ReadValue(self):
        return [ time.time() - self.time_offset,
                 self.ReadFrequency(),
               ]

    #######################################################
    #   Common Commands
    #######################################################

    def CLS(self):
        try:
            self.instr.write("*CLS")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in CLS()" + str(err))

    def ReadESE(self):
        try:
            resp = self.instr.query("*ESE?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in ReadESE()" + str(err))
        try:
            return int(resp)
        except Exception as e:
            logging.warning("Bristol671A warning in ReadESE()" + str(err))
            return np.nan

    def MaskESE(self, mask):
        if not isinstance(mask, int):
            logging.warning("Bristol671A warning in MaskESE() mask not int")
        try:
            self.instr.write("*ESE {0}".format(mask))
        except Exception as e:
            logging.warning("Bristol671A warning in MaskESE()" + str(err))

    def ReadESR(self):
        try:
            resp = self.instr.query("*ESR?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in ReadESR()" + str(err))
        try:
            return int(resp)
        except Exception as e:
            logging.warning("Bristol671A warning in ReadESR()" + str(err))
            return np.nan

    def ReadIDN(self):
        try:
            resp = self.instr.query("*IDN?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in ReadIDN()" + str(err))
        return resp

    def QueryOPC(self):
        try:
            resp = self.instr.query("*OPC?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in QueryOPC()" + str(err))
            return np.nan
        return resp

    def RCL(self):
        try:
            self.instr.write("*RCL")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in RCL()" + str(err))

    def RST(self):
        try:
            self.instr.write("*RST")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in RST()" + str(err))

    def SAV(self):
        try:
            self.instr.write("*SAV")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in SAV()" + str(err))

    def ReadSTB(self):
        try:
            resp = self.instr.query("*STB?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in ReadSTB()" + str(err))
            return np.nan
        return resp

    #######################################################
    # Measurement Commands
    #######################################################

    def Fetch(self, Q="ALL"):
        if Q not in ["POW", "ENV", "FREQ", "WAV", "WNUM", "ALL"]:
            logging.warning("Bristol671A warning in Fetch() {0} not a valid \
                             query".format(Q))
            return np.nan
        # obtain value
        try:
            resp = self.instr.query(":FETCH:{0}".format(Q))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in Fetch()" + str(err))
            return np.nan

        return resp

    def Read(self, Q="ALL"):
        if Q not in ["POW", "ENV", "FREQ", "WAV", "WNUM", "ALL"]:
            logging.warning("Bristol671A warning in Read() {0} not a valid \
                             query".format(Q))
            return np.nan
        # obtain value
        try:
            resp = self.instr.query(":READ:{0}".format(Q))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in Read()" + str(err))
            return np.nan

        return resp

    def Measure(self, Q = "ALL"):
        if Q not in ["POW", "ENV", "FREQ", "WAV", "WNUM", "ALL"]:
            logging.warning("Bristol671A warning in Measure() {0} not a valid \
                             query".format(Q))
            return np.nan
        # obtain value
        try:
            resp = self.instr.query(":MEAS:{0}".format(Q))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in Measure()" + str(err))
            return np.nan
        return resp

    def FetchPower(self):
        resp = self.Fetch(Q="POW")
        return float(resp)

    def FetchEnvironment(self):
        resp = self.Fetch(Q="ENV").split(",")
        return float(resp[0], resp[1])

    def FetchFrequency(self):
        resp = self.Fetch(Q="FREQ")
        return float(resp)

    def FetchWavelenght(self):
        resp = self.Fetch(Q="WAV")
        return float(resp)

    def FetchWavenumber(self):
        resp = self.Fetch(Q="WNUM")
        return float(resp)

    def FetchAll(self):
        resp = self.Fetch(Q="ALL").split(",")
        return int(resp[0]), int(resp[1]), float(resp[2]), float(resp[3])

    def ReadPower(self):
        resp = self.Read(Q="POW")
        return float(resp)

    def ReadEnvironment(self):
        resp = self.Read(Q="ENV").split(",")
        return float(resp[0], resp[1])

    def ReadFrequency(self):
        resp = self.Read(Q="FREQ")
        return float(resp)

    def ReadWavelenght(self):
        resp = self.Read(Q="WAV")
        return float(resp)

    def ReadWavenumber(self):
        resp = self.Read(Q="WNUM")
        return float(resp)

    def ReadAll(self):
        resp = self.Read(Q="ALL").split(",")
        return int(resp[0]), int(resp[1]), float(resp[2]), float(resp[3])

    def MeasurePower(self):
        resp = self.Measure(Q="POW")
        return float(resp)

    def MeasureEnvironment(self):
        resp = self.Measure(Q="ENV").split(",")
        return float(resp[0], resp[1])

    def MeasureFrequency(self):
        resp = self.Measure(Q="FREQ")
        return float(resp)

    def MeasureWavelenght(self):
        resp = self.Measure(Q="WAV")
        return float(resp)

    def MeasureWavenumber(self):
        resp = self.Measure(Q="WNUM")
        return float(resp)

    def MeasureAll(self):
        resp = self.Measure(Q="ALL").split(",")
        return int(resp[0]), int(resp[1]), float(resp[2]), float(resp[3])

    #######################################################
    # Calculate Commands
    #######################################################

    def CalculateData(self, Q="FREQ"):
        if Q not in ["POW", "FREQ", "WAV", "WNUM"]:
            logging.warning("Bristol671A warning in CalculateData() {0} not a\
                             valid query".format(Q))
            return np.nan
        try:
            resp = self.instr.query(":CALC:DATA? {0}".format(Q))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in CalculateData()" + str(err))
            return np.nan
        return float(resp)

    def ReadCalculateDeltaMethod(self):
        try:
            resp = self.instr.query(":CALC:DELT:METH?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in ReadCalculateDeltaMethod()"\
                            + str(err))
            return np.nan
        return resp

    def SetCalculateDeltaMethod(self, method = "START"):
        if method not in ["START", "MAXMIN"]:
            logging.warning("Bristol671A warning in SetCalculateDeltaMethod() \
                             {0} not a valid method".format(method))
        try:
            self.instr.write(":CALC:DELT:METH {0}".format(method))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in SetCalculateDeltaMethod()" \
                            + str(err))

    def CalculateReset(self):
        try:
            self.instr.write(":CALC:RES")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in CalculateReset()" \
                            + str(err))

    def CalculateTimeElapsed(self):
        try:
            resp = self.instr.query(":CALC:TIME:ELAP?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in ReadCalculateTimeElapsed()"\
                            + str(err))
            return np.nan
        return resp

    #######################################################
    # Sense Commands
    #######################################################

    def ReadAverageState(self):
        try:
            resp = self.instr.query(":SENS:AVER:STAT?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in ReadAverageState()" + str(err))
            return np.nan
        return resp

    def SetAverageState(self, state = "ON"):
        if state not in ["ON", "OFF"]:
            logging.warning("Bristol671A warning in SetAverageState() {0} not\
                             a valdi state".format(state))
            return
        try:
            self.instr.write(":SENS:AVER:STAT {0}".format(state))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in SetAverageState()" + str(err))

    def ReadAverageCount(self):
        try:
            resp = self.instr.query(":SENS:AVER:COUN?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in ReadAverageCount()" + str(err))
            return np.nan
        return int(resp)

    def SetAverageCount(self, count = 1):
        if not isinstance(count, int):
            logging.warning("Bristol671A warning in SetAverageCount() count requires int")
            return
        if (count < 1) & (count > 128):
            logging.warning("Bristol671A warning in SetAverageCount() 0 < count < 129")
            return
        try:
            if count == 0:
                self.instr.write(":SENS:AVER:COUN {0}".format("OFF"))
            else:
                self.instr.write(":SENS:AVER:COUN {0}".format(count))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in SetAverageCount()" + str(err))

    def ReadAverageData(self, Q="FREQ"):
        if Q not in ["POW", "FREQ", "WAV", "WNUM"]:
            logging.warning("Bristol671A warning in ReadAverageData() {0} not a\
                             valid query".format(Q))
            return np.nan
        # obtain value
        try:
            resp = self.instr.query(":SENS:AVER:DATA? {0}".format(Q))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in ReadAverageData()" + str(err))
            return np.nan
        return resp

    def ReadPowerOffset(self):
        try:
            resp = self.instr.query(":SENS:POW:OFFS?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in ReadPowerOffset()" + str(err))
            return np.nan
        return resp

    def SetPowerOffset(self, offset = 0):
        if not isinstance(offset, int):
            logging.warning("Bristol671A warning in SetPowerOffset() count requires int")
            return
        if (count < 0) & (count > 20):
            logging.warning("Bristol671A warning in SetPowerOffset() -1 < count < 21")
            return
        try:
            if offset == 0:
                self.instr.write(":SENS:POW:OFFS {0}".format("OFF"))
            else:
                self.instr.write(":SENS:POW:OFFS {0}".format(offset))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in ReadPowerOffset()" + str(err))

    #######################################################
    # Status Subsystem
    #######################################################

    def ReadQuestionableCondition(self):
        try:
            resp = self.instr.query(":STAT:QUES:COND?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in ReadQuestionableCondition()" + str(err))
            return np.nan
        return int(resp)

    def ReadQuestionableEnable(self):
        try:
            resp = self.instr.query(":STAT:QUES:ENAB?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in ReadQuestionableEnable()" + str(err))
            return np.nan
        return int(resp)

    def SetQuestionableEnable(self, value):
        if not isinstance(value, int):
            logging.warning("Bristol671A warning in SetQuestionableEnable() \
                             count requires int")
            return
        if (value < 1) & (value > 2048):
            logging.warning("Bristol671A warning in SetQuestionableEnable() 0 \
                             < value < 2049")
            return
        try:
            self.instr.write(":STAT:QUES:ENAB {0}".format(value))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in SetQuestionableEnable()" + str(err))

    def ReadQuestionableHardwareCondition(self):
        try:
            resp = self.instr.query(":STAT:QUES:HARD:COND?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in \
                             ReadQuestionableHardwareCondition()" + str(err))
            return np.nan
        return int(resp)

    #######################################################
    # System Subsystem
    #######################################################

    def ReadError(self):
        try:
            resp = self.instr.query(":SYST:ERR?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in ReadError()" + str(err))
            return np.nan
        try:
            resp = resp.split(",")
            return int(resp[0]), resp[1]
        except Exception as e:
            logging.warning("Bristol671A warning in ReadError()" + str(err))
            return np.nan

    def Help(self):
        try:
            resp = self.instr.query(":SYST:HELP:HEAD?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in Help()" + str(err))
            return np.nan
        return resp

    #######################################################
    # Unit Subsystem
    #######################################################

    def ReadUnitPower(self):
        try:
            resp = self.instr.queary(":UNIT:POW?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in SetUnitPower()" + str(err))
        return resp

    def SetUnitPower(self, unit = "MW"):
        if not unit in ["MW", "DBM"]:
            logging.warning("Bristol671A warning in SetUnitPower() unit not \
                             valid")
        try:
            self.instr.write(":UNIT:POW:{0}".format(unit))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Bristol671A warning in SetUnitPower()" + str(err))


    def GetWarnings(self):
        return None
