import pyvisa
import time
import numpy as np
import logging

class SPS30:
    def __init__(self, time_offset, resource_name):
        self.time_offset = time_offset
        self.rm = pyvisa.ResourceManager()
        try:
            self.instr = self.rm.open_resource(resource_name)
        except pyvisa.errors.VisaIOError as err:
            self.verification_string = str(err)
            self.instr = False
            return
        self.instr.parity = pyvisa.constants.Parity.none
        self.instr.data_bits = 8
        self.instr.baud_rate = 9600
        self.instr.term_char = '\n'
        self.instr.read_termination = '\r\n'
        self.instr.timeout = 1000

        # make the verification string
        try:
            self.verification_string = self.QueryIdentification()
        except pyvisa.errors.VisaIOError as err:
            self.verification_string = str(err)

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = 'f'
        self.shape = (10, )

        self.warnings = []

    def __enter__(self):
        return self
    
    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    def ReadValue(self):
        return [
                time.time() - self.time_offset,
                *self.ReadParticulates()
               ]

    def GetWarnings(self):
        warnings = self.warnings
        self.warnings = []
        return warnings

    #################################################################
    ##########           SERIAL COMMANDS                   ##########
    #################################################################

    def QueryIdentification(self):
        try:
            # wait for SPS30 to be initialized
            time.sleep(5)
            return self.instr.query("?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("SPS30 warning in QueryIdentification(): " + str(err))
            return str(err)

    def ReadParticulates(self):
        # read the particulates data from the Arduino
        try:
            resp = self.instr.query("r")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("SPS30 warning in ReadParticulates(): " + str(err))
            return 9*[np.nan]

        # convert the response to a number
        try:
            particulates = [float(x) for x in resp.split(",")]
        except ValueError as err:
            logging.warning("SPS30 warning in ReadParticulates(): " + str(err))
            return 9*[np.nan]

        return particulates
