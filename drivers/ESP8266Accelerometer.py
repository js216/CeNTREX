import time
import pyvisa
import logging
import functools
import numpy as np

class ESP8266Accelerometer:
    def __init__(self, time_offset, COM_port):
        self.time_offset = time_offset
        self.rm = pyvisa.ResourceManager()

        try:
            self.instr = self.rm.open_resource(COM_port)
            self.instr.parity = pyvisa.constants.Parity.none
            self.instr.data_bits = 8
            self.instr.write_termination = '\r\n'
            self.instr.read_termination = '\r\n'
            self.instr.baud_rate = 9600
            self.verification_string = "True"
        except pyvisa.errors.VisaIOError:
            self.verification_string = "False"
            self.instr = False
            return

        # shape and type of the array of returned data
        self.dtype = 'f4'
        self.shape = (3, )

        self.warnings = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    def ReadValue(self):
        values = self.instr.query('m').split(',')
        t = time.time() - self.time_offset
        values = [int(val) for val in values]
        return [t]+values
