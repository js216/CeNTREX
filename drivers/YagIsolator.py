import time
import pyvisa
import logging

class YagIsolator:
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
        self.shape = (1, )

        self.warnings = []

        # convenience attributes to cut down on serial communication for
        # monitoring commands
        self.qswitch_status = bool(self.instr.query("status D"))
        self.nr_qswitches = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    def ReadValue(self):
        return [ 
                time.time()-self.time_offset
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
    def DisableQswitchGUI(self):
        self.Disable('D')
        self.qswitch_status = bool(self.instr.query("status D"))

    def EnableQswitchGUI(self):
        self.Enable('D')
        self.qswitch_status = bool(self.instr.query("status D"))

    def QswitchStatusGUI(self):
        if self.qswitch_status:
            return 'enabled'
        else:
            return 'disabled'

    def SetNrQswitchesGUI(self, nr_qswitches):
        self.NrQswitches(nr_qswitches)
        self.nr_qswitches = nr_qswitches
    
    def GetNrQswitchesGUI(self, nr_qswitches):
        return self.nr_qswitches


    #################################################################
    ##########           SERIAL COMMANDS                   ##########
    #################################################################

    def QueryIdentification(self):
        try:
            return self.instr.query("*IDN?")
        except pyvisa.errors.VisaIOError as err:
            logging.warning("YagIsolator warning in QueryIdentification(): "
                            + str(err))
            return str(err)

    def NrQswitches(self, nr_qswitches):
        """
        Let the qswitch through the isolator 'nr_qswitches' times
        """
        cmd = f'qswitch {int(nr_qswitches)}'
        ret = self.instr.query(cmd)
        if ret != cmd:
            logging.warning("YagIsolator warning in QswitchCounter(): "+ret)
    
    def Enable(self, channel):
        assert channel in ['C', 'D'], f'invalid channel : {channel}'
        cmd = f'enable {channel}'
        ret = self.instr.query(cmd)
        if ret != cmd:
            logging.warning("YagIsolator warning in Enable(): "+ret)

    def Disable(self, channel):
        assert channel in ['C', 'D'], f'invalid channel : {channel}'
        cmd = f'disable {channel}'
        ret = self.instr.query(cmd)
        if ret != cmd:
            logging.warning("YagIsolator warning in Disable(): "+ret)


if __name__ == "__main__":
    resource_name = input('specify resource name : ')
    yag = YagIsolator(time.time(), resource_name)
    print(yag.verification_string)
    for _ in range(9):
        yag.NrQswitches(4)
        print(yag.QswitchStatusGUI())
        time.sleep(0.085)
        print(yag.QswitchStatusGUI())
    yag.__exit__()