from SelfAlignFiberSwitch import *
from Bristol671A import *

class Wavelengthmeter:
    def __init__(self, time_offset, connection):
        bristol_addr = connection['bristol_telnet_address']
        bristol_port = connection['bristol_telnet_port']
        switch_port = connection['switch_port']

        self.time_offset = time_offset

        self.bristol = Bristol671A(time_offset, {'telnet_address': bristol_addr,\
                                                 'telnet_port': bristol_port})
        self.switch = SelfAlignFiberSwitch(time_offset, switch_port)

        if self.bristol.verification_string != "BRISTOL WAVELENGTH METER, 671A-VIS, 6894, 1.2.0":
            self.verification_string = "False"
        elif self.switch.verification_string != "True":
            self.verification_string = "False"
        else:
            self.verification_string = "True"

        self.new_attributes = []

        # shape and type of the array of returned data from ReadValue
        self.dtype = 'f8'
        self.shape = (7, )

        self.warnings = []

        self.switch.Home()
        time.sleep(0.5)
        self.switch.SetChannel(2)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.bristol.instr:
            self.bristol.instr.close()
        if self.switch.instr:
            self.switch.instr.close()
        return

    def ReadValue(self):
        bristol_values = self.bristol.ReadValue()
        switch_values = self.switch.ReadValue()
        if (not isinstance(switch_values, list)) and np.isnan(switch_values):
            logging.warning("Wavelengthmeter warning in ReadValue() : switch port undetermined")
            return np.nan
        values = [np.nan]*self.shape[0]
        values[0] = bristol_values[0]
        if switch_values[1] == 16:
            values[5:7] = bristol_values
            return values
        elif switch_values[1] == 1:
            values[1:3] = bristol_values
            return values
        elif switch_values[1] == 2:
            values[3:5] = bristol_values
            return values
        else:
            return np.nan

    def SetPort(self, channel):
        self.switch.SetPort(channel)

    def GetPort(self):
        return self.switch.port
