import pyvisa
import time
import numpy as np
import logging

class HP6645A:
    def __init__(self, time_offset, resource_name):
        self.time_offset = time_offset
        self.rm = pyvisa.ResourceManager()
        try:
            self.instr = self.rm.open_resource(resource_name)
        except pyvisa.errors.VisaIOError:
            self.verification_string = "False"
            self.instr = False
            return

        # make the verification string
        try:
            self.verification_string = self.instr.query("*TST?")
        except pyvisa.errors.VisaIOError:
            self.verification_string = "False"

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = 'f'
        self.shape = (3, )

    def __enter__(self):
        return self
    
    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    def ReadValue(self):
        return [ time.time() - self.time_offset,
                 self.MeasureVoltage(),
                 self.MeasureCurrent()
               ]

    def GetWarnings(self):
        return None

    def SetVoltage(self, param):
        # parameter sanity check
        try:
            val = float(param)
        except ValueError:
            logging.warning("HP6645A warning in SetVoltage(): invalid parameter " + str(param))
            return np.nan
        if val > 130:
            logging.warning("HP6645A warning in SetVoltage(): requested voltage too high:" + str(val))
            return np.nan

        try:
            return self.instr.write('VOLT ' + str(val))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("HP6645A warning in SetVoltage(): " + str(err))
            return np.nan

    def SetCurrent(self, param):
        # parameter sanity check
        try:
            val = float(param)
        except ValueError:
            logging.warning("HP6645A warning in SetCurrent(): invalid parameter " + str(param))
            return np.nan
        if val > 1.5:
            logging.warning("HP6645A warning in SetCurrent(): requested current too high:" + str(val))
            return np.nan

        try:
            return self.instr.write('CURR ' + str(val))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("HP6645A warning in SetCurrent(): " + str(err))
            return np.nan

    def OutputEnable(self):
        try:
            return self.instr.write('OUTP ON')
        except pyvisa.errors.VisaIOError as err:
            logging.warning("HP6645A warning in OutputEnable(): " + str(err))
            return np.nan

    def OutputDisable(self):
        try:
            return self.instr.write('OUTP OFF')
        except pyvisa.errors.VisaIOError as err:
            logging.warning("HP6645A warning in OutputDisable(): " + str(err))
            return np.nan

    def MeasureVoltage(self):
        try:
            val = self.instr.query('MEAS:VOLT?')
        except pyvisa.errors.VisaIOError as err:
            logging.warning("HP6645A warning in MeasureVoltage(): " + str(err))
            return np.nan

        try:
            return float(val)
        except ValueError as err:
            logging.warning("HP6645A warning in MeasureVoltage(): " + str(err))
            return np.nan

    def MeasureCurrent(self):
        try:
            val = self.instr.query('MEAS:CURR?')
        except pyvisa.errors.VisaIOError as err:
            logging.warning("HP6645A warning in MeasureCurrent(): " + str(err))
            return np.nan

        try:
            return float(val)
        except ValueError as err:
            logging.warning("HP6645A warning in MeasureCurrent(): " + str(err))
            return np.nan
