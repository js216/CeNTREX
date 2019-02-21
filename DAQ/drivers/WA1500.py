import pyvisa
import time
import numpy as np
import logging

class WA1500:
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

        ## make the verification string
        #try:
        #    self.instr.write("getLog.reset")
        #except pyvisa.errors.VisaIOError:
        #    self.verification_string = "False"
        self.verification_string = "todo"

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = 'f'
        self.shape = (2, )

    def __enter__(self):
        return self
    
    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    def ReadValue(self):
        return [ time.time() - self.time_offset,
                 self.Measure(),
               ]

    def Measure(self):
        # obtain value
        try:
            resp = self.instr.read()
            self.instr.clear()
        except pyvisa.errors.VisaIOError as err:
            logging.warning("WA1500 warning in ReadValue()" + str(err))
            resp = ""
            return np.nan

        # extract measurement
        try:
            if resp[0] != "+":
                return np.nan
        except IndexError:
            return np.nan
        try:
            return float(resp[1:11])
        except ValueError as err:
            logging.warning("WA1500 warning in ReadValue()" + str(err))
            return np.nan

    def Units(self):
        self.instr.write("@\x27")

    def GetWarnings(self):
        return None
