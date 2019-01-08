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
