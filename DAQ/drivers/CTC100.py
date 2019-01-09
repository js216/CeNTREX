import pyvisa
import time
import numpy as np

class CTC100:
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
        self.instr.term_char = '\n'
        self.instr.timeout = 1000

        # make the verification string
        try:
            self.instr.write("getLog.reset")
        except pyvisa.errors.VisaIOError:
            self.verification_string = "False"
        self.verification_string = self.description()

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = 'f'
        self.shape = (7, )

    def __enter__(self):
        return self
    
    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    def ReadValue(self):
        return [
                time.time() - self.time_offset,
                self.getLog("In 1"),
                self.getLog("In 2"),
                self.getLog("In 3"),
                self.getLog("In 4"),
                self.getLog("Out 1"),
                self.getLog("Out 2"),
               #self.getLog("AIO 1"),
               #self.getLog("AIO 2"),
               #self.getLog("AIO 3"),
               #self.getLog("AIO 4"),
               #self.getLog("V1"),
               #self.getLog("V2"),
               #self.getLog("V3"),
               #self.getLog("DIO"),
               #self.getLog("Relays"),
            ]

    def getLog(self, channel):
        try:
            res = self.instr.query('getLog "' + channel + '", last')
        except (pyvisa.errors.VisaIOError, UnicodeDecodeError):
            return np.nan

        try:
            return float(res)
        except ValueError:
            return np.nan

    def description(self):
        try:
            return self.instr.query("description")
        except pyvisa.errors.VisaIOError:
            return np.nan

    def outputEnable(self):
        try:
            return self.instr.write("outputEnable on")
        except pyvisa.errors.VisaIOError:
            return np.nan

    def outputDisable(self):
        try:
            return self.instr.write("outputEnable off")
        except pyvisa.errors.VisaIOError:
            return np.nan

    def setADrate(self, rate):
        if not rate in [ "16.7 ms", "33.3", "50 ms", "66.7 ms", "83.3 ms", "100 ms",
                 "150 ms", "200 ms", "250 ms", "350 ms", "400 ms", "500 ms",
                 "600 ms", "700 ms", "800 ms", "900 ms", "1000 ms"]:
            return np.nan
        else:
            try:
                return self.instr.write('"system.other.A/D rate" "' + rate + '"')
            except pyvisa.errors.VisaIOError:
                return np.nan

    def setLogRate(self, rate):
        if not rate in ["off", "0.1 s", "0.3 s", "1 s", "3 s", "10 s", "30 s",
                "1 min", "3 min", "10 min", "30 min", "1 hr"]:
            return np.nan
        else:
            try:
                return self.instr.write('"system.log.interval" "' + rate + '"')
            except pyvisa.errors.VisaIOError:
                return np.nan

    def SetOut1Setpoint(self, setpoint):
        try:
            return self.instr.write('"Out1.PID.Setpoint" "' + str(setpoint) + '"')
        except pyvisa.errors.VisaIOError:
            return np.nan

    def SetOut2Setpoint(self, setpoint):
        try:
            return self.instr.write('"Out2.PID.Setpoint" "' + str(setpoint) + '"')
        except pyvisa.errors.VisaIOError:
            return np.nan

    def SetOut1Src(self, src):
        try:
            return self.instr.write('"Out1.PID.Input" "' + src + '"')
        except pyvisa.errors.VisaIOError:
            return np.nan

    def SetOut2Src(self, src):
        try:
            return self.instr.write('"Out2.PID.Input" "' + src + '"')
        except pyvisa.errors.VisaIOError:
            return np.nan
