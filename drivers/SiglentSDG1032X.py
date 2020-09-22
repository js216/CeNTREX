import time
import pyvisa
import numpy as np

class SiglentSDG1032X:
    def __init__(self, time_offset, resource_name):
        self.time_offset = time_offset
        self.rm = pyvisa.ResourceManager()
        try:
            self.instr = self.rm.open_resource(resource_name)
        except pyvisa.errors.VisaIOError:
            self.verification_string = "False"
            self.instr = False
            return
        self.instr.parity = pyvisa.constants.Parity.odd
        self.instr.data_bits = 7
        self.instr.baud_rate = 9600
        self.instr.term_char = '\r'

        # make the verification string
        self.verification_string = self.QueryIdentification()

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = 'f'
        self.shape = (9, )

    def __enter__(self):
        return self
    
    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    def ReadValue(self):
        return [time.time()-self.time_offset]

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

    def CLS(self):
        """
        Clear all event registers, the error queue and cancels an *opc command
        """
        self.instr.write('*CLS')

    def RST(self):
        """
        Reset the function generator to its factory default state.
        """
        self.instr.write('*RST')

    def OPC(self):
        self.instr.query('*OPC?')

    def GetOutput(self, ch):
        cmd = f'C{ch}:OUTP?'
        return self.instr.query(cmd)

    def Output(self, ch, output):
        cmd = f'C{CH}OUTP {output}'
        self.instr.write(cmd)

    def ClockSource(self, source):
        cmd = f'ROSCL {source}'
        self.instr.write(cmd)
    