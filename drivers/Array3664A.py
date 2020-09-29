import time
import pyvisa
import logging
import numpy as np

class Array3664A:
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
        self.instr.term_char = '\r\n'

        # make the verification string
        self.verification_string = self.QueryIdentification()

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = ('f', 'float', 'float')
        self.shape = (3, )
    
    def __enter__(self):
        return self
    
    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    def ReadValue(self):
        ret = [time.time()-self.time_offset, self.GetVoltage(), self.GetCurrent() ]
        return ret

    def GetWarnings(self):
        return None

    def QueryIdentification(self):
        """Identifies the instrument model and software level.
        
        Returns:
        <manufacturer>, <model number>, <serial number>, <firmware date>
        """
        try:
            return self.instr.query("*IDN?")
        except pyvisa.errors.VisaIOError:
            return np.nan

    #################################################################
    ##########           IEEE-488/SERIAL COMMANDS          ##########
    #################################################################

    def Output(self, state):
        self.instr.write(f'OUTPUT:STATE {int(state)}')

    def Apply(self, voltage, current):
        self.instr.write(f'APPL {voltage},{current}')

    def GetCurrent(self):
        return float(self.instr.query('MEAS:SCAL:CURR?'))

    def GetVoltage(self):
        return float(self.instr.query('MEAS:SCAL:VOLT?'))


if __name__ == '__main__':
    resource_name = input('specify resource name : ')
    psu = Array3664A(time.time(), resource_name)
    psu.Apply(5,2)
    psu.Output(1)
    time.sleep(2)
    print(psu.ReadValue())
    psu.Output(0)
    psu.__exit__()
    