import time
import pyvisa
import logging
import functools
import numpy as np

def CheckResponse(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            if func(*args, **kwargs):
                ret = args[0].instr.read_bytes(4)
                if not b'\x01\x35\xff\xff' == ret:
                    warning_dict = {"message": "invalid response in {0}".format(func.__name__)}
                    args[0].warnings.append([time.time(), warning_dict])
                    logging.warning("SelfAlignFiberSwitch warning in {0}() : ".format(func.__name__) \
                                    +"invalid response")
        except pyvisa.errors.VisaIOError as err:
                warning_dict = {"message": "Err in {0} : ".format(func.__name__)+str(err)}
                args[0].warnings.append([time.time(), warning_dict])
                logging.warning('SelfAlignFiberSwitch warning in {0}() : '.format(func.__name__) \
                                +str(err))
    return wrapper

class SelfAlignFiberSwitch:
    def __init__(self, time_offset, COM_port):
        self.time_offset = time_offset
        self.rm = pyvisa.ResourceManager()

        if COM_port not in ['client', ' ']:
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

        # HDF attributes generated when constructor is run
        self.new_attributes = []

        # shape and type of the array of returned data
        self.dtype = 'f4'
        self.shape = (1, )

        self.warnings = []

        self.port = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.instr:
            self.instr.close()

    ##############################
    # CeNTREX DAQ Commands
    ##############################

    def ReadValue(self):
        if self.port:
            return [time.time()-self.time_offset, self.port]
        else:
            return np.nan

    def GetWarnings(self):
        warnings = self.warnings.copy()
        self.warnings = []
        return warnings

    ##############################
    # Device commands
    ##############################

    def write(self, cmd):
        self.instr.write_raw(cmd)
        self.instr.read_bytes(4)

    @CheckResponse
    def SetPort(self, port):
        try:
            port = int(port)
        except Exception as err:
            logging.warning("SelfAlignFiberSwitch warning in Setport : can't convert {0} to int".format(port))
            warning_dict = { "Setport; can't convert {0} to int".format(port)}
            self.warnings.append([time.time(), warning_dict])
        if self.port == port:
            return
        if (port > 16) or (port < 1):
            logging.warning("SelfAlignFiberSwitch warning in Setport({0}) : ".format(port)\
                            +"port out of range")
            return
        byte_value = bytes([port-1])
        cmd = b'\x01\x35\x00'+byte_value
        self.write(cmd)
        self.port = port
        return True

    def Home(self):
        cmd = b"\x01\x30\x00\x00"
        self.write(cmd)
