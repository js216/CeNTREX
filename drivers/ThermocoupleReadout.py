import pyvisa
import time
import numpy as np
import logging

class ThermocoupleReadout:
    def __init__(self, time_offset, resource_name, channels, units = 'K'):
        self.channels = [str(ch) for enable, ch in zip(channels['enable'], channels['channel']) if enable == '1']
        self.time_offset = time_offset
        self.rm = pyvisa.ResourceManager()
        try:
            self.instr = self.rm.open_resource(resource_name)

        except pyvisa.errors.VisaIOError as err:
            logging.warning("ThermocoupleReadout connection error: "+str(err))
            self.verification_string = str(False)
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
            self.instr.query("t1")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("ThermocoupleReadout connection error: "+str(err))
            self.verification_string = str(err)
        self.verification_string = str(True)

        self.units = units

        # HDF attributes generated when constructor is run
        self.new_attributes = [
                    ('column_names',", "+", ".join(self.channels)),
                    ("units", "s, "+", ".join([units]*len(self.channels)))
                    ]
        # shape and type of the array of returned data
        self.dtype = tuple(['f'] * (len(self.channels)+1))
        self.shape = (len(self.channels)+1, )

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    def GetWarnings(self):
        return None

    def ReadValue(self):
        values = [time.time() - self.time_offset]
        for ch in self.channels:
            values.append(self.GetTemperature(ch))
        return values

    def GetTemperature(self, ch):
        temperature = float(self.instr.query(ch))
        if self.units == 'K':
            return temperature + 273.15
        else:
            return temperature
