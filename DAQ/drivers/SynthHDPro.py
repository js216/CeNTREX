import pyvisa
import time
import numpy as np
import logging

class SynthHDPro:
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
            self.verification_string = self.instr.query('-')[:-1]
        except pyvisa.errors.VisaIOError:
            self.verification_string = "False"

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
        return [
                time.time() - self.time_offset,
                self.DeviceTemp(),
               ]

    def GetWarnings(self):
        return None

    def DeviceTemp(self):
        try:
            return float(self.instr.query('z')[:-1])
        except ValueError as err:
            logging.warning("SynthHDPro warning in DeviceTemp(): " + str(err))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("SynthHDPro warning in DeviceTemp(): " + str(err))

    def SetReference(self, param):
        if param == "internal 27MHz":
            self.instr.write('x1')
        elif param == "internal 10MHz":
            self.instr.write('x2')
        elif param == "external":
            self.instr.write('x0')

    def SetExternalClockSpeed(self, param):
        try:
            freq = float(param)
        except ValueError as err:
            logging.warning("SynthHDPro warning in SetExternalClockSpeed(): " + str(err))
        else:
            self.instr.write('*' + str(freq))

    def ControlChannelA(self):
        self.instr.write('C0')

    def ControlChannelB(self):
        self.instr.write('C1')

    def SetRFFreq(self, param):
        try:
            freq = float(param)
        except ValueError as err:
            logging.warning("SynthHDPro warning in SetRFFreq(): " + str(err))
        else:
            self.instr.write('f' + str(freq))

    def SetRFPower(self, param):
        try:
            power = float(param)
        except ValueError as err:
            logging.warning("SynthHDPro warning in SetRFPower(): " + str(err))
        else:
            self.instr.write('W' + str(power))

    def RFon(self):
        self.instr.write('E1r1')

    def RFoff(self):
        self.instr.write('E0r0')

    ############################################
    # Convenience functions that work on one channel only
    ############################################

    def SetRFFreqA(self, param):
        self.ControlChannelA
        self.SetRFFreq(param)

    def SetRFPowerA(self, param):
        self.ControlChannelA
        self.SetRFPower(param)

    def RFonA(self):
        self.ControlChannelA
        self.RFon()

    def RFoffA(self):
        self.ControlChannelA
        self.RFoff()

    def SetRFFreqB(self, param):
        self.ControlChannelB
        self.SetRFFreq(param)

    def SetRFPowerB(self, param):
        self.ControlChannelB
        self.SetRFPower(param)

    def RFonB(self):
        self.ControlChannelB
        self.RFon()

    def RFoffB(self):
        self.ControlChannelB
        self.RFoff()
