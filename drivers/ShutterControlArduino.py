import time
import pyvisa
import logging

class ShutterControlArduino:
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
        self.instr.read_termination = "\r\n"

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
                self.State()
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
    ##########           GUI COMMANDS                      ##########
    #################################################################

    def StateGUI(self):
        state = self.State()
        status = bool(state)
        if status:
            return 'open'
        else:
            return 'close'


    #################################################################
    ##########           SERIAL COMMANDS                   ##########
    #################################################################

    def QueryIdentification(self):
        try:
            return self.instr.query("*IDN?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("ShutterControl warning in QueryIdentification(): "
                            + str(err))
            return str(err)


    def Open(self):
        """
        Opening the shutter
        """
        cmd = "open"
        ret = self.instr.query(cmd)
        if ret != cmd:
            logging.warning("ShutterControl warning in Open(): "+ret)

    def Close(self):
        """
        CLosing the shutter
        """
        cmd = "close"
        ret = self.instr.query(cmd)
        if ret != cmd:
            logging.warning("ShutterControl warning in Close(): "+ret)

    def State(self):
        try:
            return int(self.instr.query("state"))
        except pyvisa.errors.VisaIOError as err:
            logging.warning("ShutterControlArduino warning in State(): " + str(err))
            return np.nan
        except Exception as err:
            logging.warning("ShutterControlArduino warning in State(): " + str(err))
            return np.nan

if __name__ == "__main__":
    resource_name = input('specify resource name : ')
    shutter = ShutterControlArduino(time.time(), resource_name)
    print(shutter.verification_string)
    for _ in range(4):
        print('='*23)
        shutter.Open()
        print(shutter.StateGUI())
        time.sleep(2)
        shutter.Close()
        print(shutter.StateGUI())
        time.sleep(2)
    shutter.__exit__()