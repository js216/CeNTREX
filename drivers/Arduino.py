import pyvisa
import numpy as np
import time
import logging

class Arduino:
    def __init__(self, time_offset, resource_name):
        self.time_offset = time_offset
        self.rm = pyvisa.ResourceManager()
        try:
            self.instr = self.rm.open_resource(resource_name)
        except pyvisa.errors.VisaIOError as err:
            self.verification_string = str(err)
            self.instr = False
            return
        self.instr.baud_rate = 9600
        self.instr.data_bits = 8
        self.instr.parity = pyvisa.constants.Parity.none
        self.instr.stop_bits = pyvisa.constants.StopBits.one
        self.instr.read_termination = "\n"

        # make the verification string
        self.ClearBuffer()
        self.verification_string = self.QueryIdentification()

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = 'f'
        self.shape = (2, )

        self.warnings = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    def ReadValue(self):
        return [ 
                time.time()-self.time_offset,
                self.ReadTemp(),
               ]

    def GetWarnings(self):
        warnings = self.warnings
        self.warnings = []
        return warnings

    def ClearBuffer(self):
        try:
            self.instr.read()
        except:
            pass

    #################################################################
    ##########           SERIAL COMMANDS                   ##########
    #################################################################

    def QueryIdentification(self):
        try:
            return self.instr.query("i")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Arduino warning in QueryIdentification(): " + str(err))
            return str(err)

    def ReadTemp(self):
        # measure the temperature
        try:
            resp = self.instr.query("t")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("Arduino warning in ReadTemp(): " + str(err))
            return np.nan

        # convert the response to a number
        try:
            temp = float(resp)
        except ValueError as err:
            logging.warning("Arduino warning in ReadTemp(): " + str(err))
            return np.nan

        return temp

    def ValveOpen(self):
        try:
            return self.instr.query("o")
        except pyvisa.errors.VisaIOError:
            return np.nan

    def ValveClose(self):
        try:
            return self.instr.query("c")
        except pyvisa.errors.VisaIOError:
            return np.nan

    def ValveStatus(self):
        try:
            ret_val = self.instr.query("s")
        except pyvisa.errors.VisaIOError:
            return "invalid"

        if ret_val == "Valve opened.":
            return "opened"
        elif ret_val == "Valve closed.":
            return "closed"
        else:
            return "invalid"
